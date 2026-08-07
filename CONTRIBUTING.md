# Contributing

This file is the org-wide default. GitHub only serves it on a repository that
keeps no `CONTRIBUTING.md` of its own — every active repository here does, so
you are more likely reading this from a repository that doesn't exist yet
than from one that does. Read the local guide first if one exists; it has the
setup, the test loop, and the constraints specific to that package.

## Releasing

Every package in this org ships under one shared lifecycle — conventional
commit → towncrier fragment → PR CI → an automated release PR → a human
folding the release notes and approving → an immutable tag → a Trusted
Publishing (OIDC) release to PyPI / crates.io / the Go module proxy. Read
[`RELEASING.md`](RELEASING.md) before opening a release-shaped PR anywhere in
this org.

## Commits

Conventional Commits: `feat:` / `fix:` / `perf:` / `refactor:` / `deps:`
appear in the changelog; `docs:` / `test:` / `build:` / `ci:` / `chore:` /
`style:` stay out of it but still describe the commit honestly. A change that
matters to someone installing the package gets a towncrier fragment in the
same PR — see the repository's own `changelog.d/README.md`.

The type also picks the version: a `!` or `BREAKING CHANGE:` takes the major,
`feat` takes the minor, everything else takes the patch. [What Picks the
Number](RELEASING.md#what-picks-the-number) has the pre-1.0 variant and the
`Release-As:` override.

## Licensing

Apache-2.0 across every public repository in this org, unless that
repository's own `LICENSE` says otherwise. Opening a pull request licenses
your change under it.
