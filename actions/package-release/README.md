---
doc_radar:
  sentinels:
    - file: actions/package-release/action.yml
      contains: ['version: "0.12.17"', 'version: 0.16.0', 'steps.prepare.outputs.zig']
    - file: actions/package-release/requirements.txt
      contains: ['towncrier==26.9.0', 'click==8.5.0', 'jinja2==3.1.6', 'markupsafe==3.0.3']
    - file: actions/package-release/_run.py
      contains: ['shlex.split', '"--require-hashes"', '"SOURCE_DATE_EPOCH"']
    - file: actions/package-release/validate.py
      contains: ['import tomllib']
---

# package-release

We use one release contract across our OSS repositories. Pin the action to a full commit SHA whose CI passed, and declare the package's authority and changelog in `release.toml`.

```yaml
- uses: The-Billy-Company/.github/actions/package-release@FULL_COMMIT_SHA
  with:
    command: version
    args: --root . --tag ${{ github.ref_name }}

- uses: The-Billy-Company/.github/actions/package-release@FULL_COMMIT_SHA
  with:
    command: ci-status
    args: ${{ github.repository }} ${{ github.sha }}
```

## Arguments and results

`command` names one of the seven commands below. `args` uses POSIX quoting: `--root 'a directory with spaces'`. Quotes group arguments; dollar signs, backticks, wildcards and shell operators stay literal.

The action preserves the command's stdout, stderr and exit status. `result` is its last stdout line, including on failure; `version` returns a JSON object containing `version`, `registry-probe` returns a state, and other successful commands normally return `ok`. With `--json`, a multiline report's last line remains `}`.

## Setup

We install tools only after the command's own argument parser accepts the input. Cargo version authorities use Python's TOML parser; Zig authorities use Zig's ZON parser and its native field locations. The action installs Zig 0.16.0 only for a Zig authority or `selftest`.

The entry point needs Python 3.11 or newer, as supplied by current GitHub-hosted runners. A self-hosted runner must provide it before calling the action.

`changelog` and `selftest` get a private Python 3.12 environment through pinned uv 0.12.17. Its complete Towncrier closure comes from `requirements.txt`, with hashes, wheels only and a two-day release floor. Every invocation owns its temporary files and removes them after printing its outputs.

Towncrier 26.9.0 supports reproducible dates. For a changelog draft, we preserve an explicit `SOURCE_DATE_EPOCH`; otherwise we derive it from the package's HEAD commit when Git is available. Dates default to UTC; an explicit `TZ` stays yours.

## The manifest

```toml
[package]
name = "irregex"                 # human-readable
version_source = "build.zig.zon" # the authoritative file
version_kind = "zig-zon"         # zig-zon | cargo-workspace | cargo-package

[changelog]
directory = "changelog.d"
file = "CHANGELOG.md"
ignore = [".gitkeep", "README.md"]
types = ["added", "changed", "deprecated", "removed", "fixed", "security"]
stem_pattern = '^\+[a-z0-9]+(-[a-z0-9]+)*$'
min_body_chars = 40

[ci]
required_check = "release-ready"
default_branch = "main"

[registries] # optional publication inventory
pypi = "irregex"
crates = "irgx"
go_module = "github.com/The-Billy-Company/irregex/bindings/go/v2"
```

`zig-zon` reads the root `.version` field. `cargo-workspace` reads `[workspace.package].version`; `cargo-package` reads `[package].version`. The authoritative version must carry its `x-release-please-version` marker on the same line, so release-please can actually rewrite it.

## The seven commands

```bash
python3 validate.py version --root REPO [--tag vX.Y.Z] [--json]
python3 validate.py changelog --root REPO [--version X.Y.Z] [--require-fragments-empty] [--json]
python3 validate.py notes --root REPO --version X.Y.Z --out FILE [--repo owner/name]
python3 validate.py ci-status OWNER/REPO SHA [--check-name release-ready] [--token TOKEN]
python3 validate.py tag-ancestor OWNER/REPO SHA [--branch main] [--token TOKEN]
python3 validate.py registry-probe pypi|crates NAME VERSION
python3 validate.py selftest
```

**`version`** checks every marked mirror, release-please's `extra-files` when configured, and the tag when supplied. Native parsers reject malformed declarations, duplicate keys and a version hidden in a comment, string or nested dependency.

**`changelog`** checks fragment names, types and bodies, then runs a real Towncrier draft. A typo Towncrier silently drops cannot turn the gate green. The tag-time `--require-fragments-empty` form requires both an empty fragment directory and the exact folded heading.

**`notes`** writes the folded section as the release body, accepting a bare version or a leading `v`. release-please's `skip-changelog` controls its file, not its release body; without this command, real fragment notes get replaced with filtered commit subjects. Over GitHub's 125,000-character limit, we cut at a whole bullet and link the rest instead of failing after the tag is immutable.

**`ci-status`** polls for the named check's successful conclusion on the exact commit. An absent, failed or timed-out check cannot publish.

**`tag-ancestor`** requires the commit to be reachable from the protected branch. A detached or unmerged tag cannot publish.

**`registry-probe`** reports `absent`, `present` or `error`. A registry outage stays an error; a completed prior upload makes a retry idempotent.

**`selftest`** proves the rejection contracts offline. A direct local run needs Zig for ZON fixtures and Towncrier for rendering; missing optional render tooling is reported as a skip, never counted as a pass. The composite action installs both and runs the full suite.

## Local checks and CI

The actual workflow lives in [`.github/workflows/docs.yml`](../../.github/workflows/docs.yml). It runs the composite action on Linux, macOS and Windows, checks literal quoted paths, negative calls, concurrent entry points and exact outputs, and runs actionlint, zizmor, Markdown structure and relative-link checks.

Run `python3 _actiontest.py -v` here for process-boundary checks. Run `python3 validate.py selftest` with the pinned tools on PATH for parser and release-contract checks. These call the real engine against temporary files; they do not publish anything.
