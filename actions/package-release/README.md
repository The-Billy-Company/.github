# package-release

The release contract every publishable Billy-Company OSS repository (`irregex`,
`gist`, `relate`, `blast`, `zoning`, `sheng`, `brigade`) runs — one stdlib-only
Python engine (`validate.py` + `_version.py` / `_changelog.py` / `_github.py` /
`_registry.py`), wrapped as a composite action so `ci.yml` and `release.yml`
in every repo call the *same* code instead of six similar copies of the same
bash.

## Why a shared action instead of six copies

Each repo used to hand-roll its own "does the tag name the declared version"
check and its own ad hoc changelog-draft guard. They were nearly identical and
drifted anyway — `irregex`/`gist` checked more than `relate`/`blast`, and none
of them checked fragment filenames or bodies at all. A rejection message is
part of the contract too: an author who gets a different error shape from
`sheng` than from `gist` for the same mistake has learned nothing reusable.
One engine, one message shape, adopted identically everywhere.

## The manifest: `release.toml`

Each repo declares a small `release.toml` at its root. Every field below is
required unless marked optional.

```toml
[package]
name = "irregex"                 # human-readable, for messages only
version_source = "build.zig.zon" # the ONE file whose version is authoritative
version_kind = "zig-zon"         # zig-zon | cargo-workspace | cargo-package

[changelog]
directory = "changelog.d"
file = "CHANGELOG.md"
ignore = [".gitkeep", "README.md"]
types = ["added", "changed", "deprecated", "removed", "fixed", "security"]
stem_pattern = '^\+[a-z0-9]+(-[a-z0-9]+)*$'
min_body_chars = 40

[ci]
required_check = "release-ready"  # the aggregate job release.yml polls for
default_branch = "main"           # a tag must be reachable from here

[registries]                      # optional — omit a key the repo doesn't publish to
pypi = "irregex"
crates = "irgx"
go_module = "github.com/The-Billy-Company/irregex/bindings/go"
```

`version_kind`:

- `zig-zon` — a `.version = "X.Y.Z"` field in a Zig `build.zig.zon`.
- `cargo-workspace` — a `version` under `[workspace.package]` (one authority
  for every member, e.g. `zoning`).
- `cargo-package` — a `version` under a single crate's `[package]` (`sheng`,
  `brigade`).

## The six commands

```bash
python3 validate.py version    --root <repo> [--tag vX.Y.Z] [--json]
python3 validate.py changelog  --root <repo> [--version X.Y.Z] [--require-fragments-empty] [--json]
python3 validate.py ci-status  <owner/repo> <sha> [--check-name release-ready] [--token …]
python3 validate.py tag-ancestor <owner/repo> <sha> [--branch main] [--token …]
python3 validate.py registry-probe pypi|crates <name> <version>
python3 validate.py selftest
```

- **`version`** — the version `version_source` declares must match every
  other file in the tree carrying an `x-release-please-version` marker
  comment (the same marker release-please itself edits), must appear in
  `release-please-config.json`'s `extra-files` if that file exists, and —
  with `--tag` — must equal the tag being released.
- **`changelog`** — every fragment's *filename* must match
  `<stem_pattern>.<one of types>.md`, and its *body* must clear
  `min_body_chars`, not open with a bare `- `/`* ` (towncrier already renders
  the bullet), and not be a placeholder (`TODO`, `TBD`, …). Then towncrier
  itself runs `build --draft`, so a filename `_changelog.py` didn't reject but
  towncrier's own parser still can't read is still caught — and if fragments
  exist on disk but the draft renders nothing, that is treated as a *wiring*
  fault, not a clean tree. `--require-fragments-empty` is the tag-time form:
  it asserts folding actually happened (no fragment left un-folded), rather
  than checking the draft again.
- **`ci-status`** — polls `GET .../commits/{sha}/check-runs` for
  `required_check` and requires `conclusion == success` on that *exact* sha —
  not "the branch is green somewhere," but this commit, this check.
- **`tag-ancestor`** — `GET .../compare/{sha}...{branch}`; rejects unless
  `sha` is `identical` to or an ancestor of (`ahead` from) the branch tip, so
  a tag cut from a detached or unmerged commit cannot publish.
- **`registry-probe`** — `absent` (safe to publish), `present` (a prior
  attempt already got there — treat a retry as success), or `error` (the
  registry didn't answer — never treated as `absent`).
- **`selftest`** — offline, no network, no token: proves every command above
  actually rejects the fixture it claims to reject. Run it after touching any
  of the five modules (`uv run --no-project --python 3.12 --with
  towncrier==25.8.0 python3 validate.py selftest` from this directory).

Every command prints `::error::`-prefixed lines on stderr (so GitHub Actions
surfaces them as annotations on the failing step) and is silent-success on
stdout (`ok`) unless `--json` is given, which reports the same facts as one
JSON object instead.

## Using it from a workflow

```yaml
- uses: The-Billy-Company/.github/actions/package-release@main
  with:
    command: version
    args: --root . --tag ${{ github.ref_name }}

- uses: The-Billy-Company/.github/actions/package-release@main
  with:
    command: ci-status
    args: ${{ github.repository }} ${{ github.sha }}
```

Pin `@main` to a commit SHA once this action has its first real commit —
every third-party action referenced elsewhere in these repos is SHA-pinned,
and a self-owned action should hold to the same bar as soon as there is a SHA
to pin to.
