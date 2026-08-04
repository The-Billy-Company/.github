# GitHub Apps in The Billy Company

We have built exactly one GitHub App so far: `billy-company-release`. This
document audits what it actually does (from code every repository already
carries), lists what only its owner can answer, and works through whether a
second, webhook-backed App is worth building on top of it.

## The Existing App

Every repository on the shared release lifecycle (see
[`../RELEASING.md`](../RELEASING.md)) authenticates two workflow steps with
an installation token from `billy-company-release` instead of the default
`GITHUB_TOKEN`: opening or updating the automated release pull request, and
— where a package's registry has no tag-push notion of its own (a Go module
resolved by a subdirectory-prefixed tag) — creating that tag through the API
rather than through a credentialed `git push`.

### Why an App, Not Actions

Two independent walls make the default `GITHUB_TOKEN` unusable for this, and
either one alone would be enough:

1. This org's branch protection blocks the Actions identity from opening
   pull requests at all.
2. Even where that were allowed, a tag pushed with `GITHUB_TOKEN` does not
   trigger another workflow run — GitHub's own recursive-workflow guard. A
   release PR merged by the Actions identity would tag a version and nothing
   would ever publish it.

An installation token is a distinct actor from `github-actions[bot]`, so it
clears both walls: it can open the PR, and the tag it (indirectly, via a
human's merge) produces still fires `release.yml`.

### What the Code Shows

The code-visible behavior audits cleanly into four properties:

- **Identity, not a long-lived secret.** The signing key never appears in a
  workflow — every consumer exchanges it for an installation token through
  `actions/create-github-app-token`, reading the App's identifier from the
  org variable `RELEASE_APP_CLIENT_ID` and its private key from the org
  secret `RELEASE_APP_PRIVATE_KEY`. One pair, shared by every repository on
  the lifecycle, is one thing to ever rotate.
- **Minted tokens are narrowed and short-lived.** Each call to
  `create-github-app-token` passes only the `permission-*` inputs that step
  actually uses (`contents`, `pull-requests`, `issues` for the release PR;
  `contents` alone for a Go module tag) rather than inheriting everything the
  installation holds, and the resulting token expires within the hour. A
  permission granted to the App later does not silently widen an already-
  narrowed token.
- **Installation scope is the ecosystem, not everything.** The App is
  installed only on this org's public repositories. A token minted from it
  is therefore structurally unable to reach the private monorepo — there is
  no repository list to misconfigure into over-scope, because the
  installation itself doesn't extend there.
- **What it is never asked to do.** Nowhere in any consumer's workflow does
  this App's token touch a registry (PyPI/crates.io publish credentials are
  separate, short-lived OIDC exchanges — see `RELEASING.md`), read or write
  repository settings, or handle a webhook. Its code-visible surface is
  exactly "open/update one PR, optionally create one tag."

## What Only the App's Owner Can Answer

None of this is visible from source, and none of it belongs in a repository
regardless — record it in whatever the org's actual credential/secrets
inventory is, never in a markdown file:

- [ ] Who is the registered owner of the App (the GitHub account/org role
      that can edit its manifest, reinstall it, or delete it)?
- [ ] The exact list of repositories it's currently installed on, read from
      the App's own installation settings — not inferred from which
      workflows happen to reference it.
- [ ] The permissions actually granted at the installation, versus the
      narrower set any one token requests — an App can be over-permissioned
      at the installation even when every consumer narrows correctly.
- [ ] The signing key's age and fingerprint, and whether more than one key is
      currently active (GitHub allows multiple; an old one left active after
      a rotation is a live credential nobody is tracking).
- [ ] A written, rehearsed zero-downtime rotation procedure: generate the new
      key, roll `RELEASE_APP_PRIVATE_KEY` in the org secret store, confirm a
      release PR opens successfully, then revoke the old key — in that
      order, so there's never a window with zero valid keys.
- [ ] Whether the App subscribes to any webhook events at all today (the
      code-visible behavior above suggests no, since every consumer polls
      via Actions rather than reacting to a push), and if it does, where that
      webhook payload is received and by what.
- [ ] Who owns the App's audit log (installation changes, permission grants,
      key generations) and how often it's reviewed.
- [ ] The recovery path if the signing key is compromised: revoke, rotate,
      and — because a compromised installation token can open pull requests
      across every installed repository within its one-hour lifetime — what
      the incident-response playbook checks across those repositories
      afterward.

## Should We Build a Second, Webhook-Backed App?

Three options, compared on what each can actually express:

- **GitHub Actions / reusable workflows** — runs on a trigger and exits,
  holding no state across repositories beyond what one run's job graph
  passes between its own steps. It costs nothing beyond compute already
  budgeted per repo, fails by simply failing a run (retried by re-dispatch or
  a new push), and already fits today's release lifecycle: every step in
  `RELEASING.md`, including cross-repository dependency ordering, is
  expressed this way.
- **The existing App as an auth identity** — is a credential
  `create-github-app-token` exchanges for inside a workflow step, not a
  process, so it holds no state of its own and costs nothing beyond reusing
  the existing installation. Its failure mode is whatever the workflow step
  that used it does, and it already fits today's lifecycle — it's what
  makes the PR/tag steps possible at all.
- **A new webhook-backed "ecosystem steward"** — would be a persistent
  service reacting to installed webhooks, able to hold state across events
  and repositories, but needing its own hosting, monitoring, and patching.
  An outage would silently drop webhook events unless queued and retried
  explicitly, and it fits today's lifecycle only if something below
  actually needs a runtime.

### The Dependency-Aware Release Case

The candidate worth taking seriously, tested against the strongest argument
for building one, was: coordinate releases across the search family (a
downstream face shouldn't publish against a dependency version that hasn't
landed), surface one cross-repo readiness check, and open narrowly scoped
dependency-bump PRs when an upstream package ships. Every piece of that is
now live, and it is expressed entirely in Actions, with no new App and no
webhook:

- Dependency ordering is enforced by the shared release preflight itself: a
  downstream package's floor-install check resolves its dependency from the
  public registry index, not from a path override, so it cannot pass against
  a version that hasn't actually published yet. There is no "wait for the
  upstream release" step to coordinate — an unpublished dependency simply
  fails the check that would have needed coordinating around.
- The "one cross-repo readiness check" that motivated a steward is each
  repository's own `release-ready` aggregate check, read by the preflight on
  the exact tagged commit — a poll from the consumer's own workflow run, not
  a service watching for it.
- Narrowly scoped dependency-bump PRs remain the one piece a persistent
  service could add over what exists — but nothing in the current pipeline
  is blocked without it, since a version-range floor (`>=1.0.0,<2`) already
  tolerates an upstream patch or minor release without any PR at all, and a
  major bump crossing that ceiling is exactly the kind of change a human
  should be reviewing rather than an automated PR quietly opening across
  several repositories at once.

### Recommendation

Reuse the existing identity; do not build a new App. `billy-company-release`
stays scoped to what it already does — the release PR and, where needed, a
tag.

The dependency-ordering and cross-repo verification problem that used to be
the strongest case for a webhook-backed runtime is solved, in production, by
Actions alone. Revisit this only if a genuinely new requirement appears that
Actions structurally cannot express — rich Checks API annotations rendered
incrementally as a long-running job progresses, or a workflow that needs to
react to an event happening outside any repository's own CI (an external
registry's status page, a security advisory feed).

If that happens, re-run this comparison against that specific requirement
rather than against the case examined here, which Actions already closes.
