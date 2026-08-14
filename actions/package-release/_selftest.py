"""Offline proof that every gate actually rejects what it claims to reject.

No network, no GitHub token, and towncrier is optional: the filename/body
rules are pure functions and always run; the two checks that shell out to a
real `towncrier` binary report SKIP rather than a false PASS when it is not
on PATH, so this stays honest about what it proved on this machine.
"""

from __future__ import annotations

import pathlib
import shutil
import tempfile

import _changelog
import _github
import _registry
import _version

_PASS, _FAIL, _SKIP = "PASS", "FAIL", "SKIP"


def _report(results: list[tuple[str, str, str]]) -> int:
    width = max(len(name) for name, _, _ in results)
    for name, verdict, detail in results:
        print(f"[{verdict:>4}] {name:<{width}}  {detail}")
    failed = [r for r in results if r[1] == _FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed, {len(failed)} failed")
    return 1 if failed else 0


def _expect(results: list, name: str, condition: bool, detail: str) -> None:
    results.append((name, _PASS if condition else _FAIL, detail))


def _version_cases(results: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "build.zig.zon").write_text(
            '.{ .version = "1.2.3", // x-release-please-version\n}\n'
        )
        (root / "pyproject.toml").write_text('version = "1.2.3" # x-release-please-version\n')
        faults, want = _version.check(
            root, {"version_source": "build.zig.zon", "version_kind": "zig-zon"}, tag="v1.2.3"
        )
        _expect(results, "version/happy-zig-zon", not faults and want == "1.2.3", str(faults))

        (root / "pyproject.toml").write_text('version = "9.9.9" # x-release-please-version\n')
        faults, _ = _version.check(
            root, {"version_source": "build.zig.zon", "version_kind": "zig-zon"}, tag=None
        )
        _expect(results, "version/drifted-mirror-rejected", bool(faults), str(faults))

        faults, _ = _version.check(
            root, {"version_source": "build.zig.zon", "version_kind": "zig-zon"}, tag="v0.0.1"
        )
        _expect(results, "version/tag-mismatch-rejected", bool(faults), str(faults))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "Cargo.toml").write_text(
            '[workspace.package]\nversion = "0.4.0" # x-release-please-version\n'
        )
        faults, want = _version.check(
            root, {"version_source": "Cargo.toml", "version_kind": "cargo-workspace"}, tag="v0.4.0"
        )
        _expect(results, "version/happy-cargo-workspace", not faults and want == "0.4.0", str(faults))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "Cargo.toml").write_text('[package]\nversion = "2.0.0"\n')
        faults, _ = _version.check(
            root, {"version_source": "Cargo.toml", "version_kind": "cargo-package"}, tag=None
        )
        _expect(
            results, "version/missing-marker-rejected",
            any("carries no" in f for f in faults), str(faults),
        )


_CHANGELOG_MANIFEST = {
    "directory": "changelog.d",
    "file": "CHANGELOG.md",
    "ignore": [".gitkeep", "README.md"],
    "types": ["added", "changed", "fixed"],
    "stem_pattern": r"^\+[a-z0-9]+(-[a-z0-9]+)*$",
    "min_body_chars": 20,
}


_TOWNCRIER_TOML = """\
[tool.towncrier]
directory = "changelog.d"
filename = "CHANGELOG.md"
title_format = "## [{version}]"

[[tool.towncrier.type]]
directory = "added"
name = "Added"
showcontent = true

[[tool.towncrier.type]]
directory = "changed"
name = "Changed"
showcontent = true

[[tool.towncrier.type]]
directory = "fixed"
name = "Fixed"
showcontent = true
"""


def _changelog_cases(results: list) -> None:
    have_towncrier = shutil.which("towncrier") is not None

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        frags = root / "changelog.d"
        frags.mkdir()
        (root / "CHANGELOG.md").write_text("<!-- towncrier release notes start -->\n")
        (root / "towncrier.toml").write_text(_TOWNCRIER_TOML)

        (frags / "+bad name.added.md").write_text("x" * 40)
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
        _expect(results, "changelog/bad-stem-rejected", any("stem" in f for f in faults), str(faults))

        for stray in frags.iterdir():
            stray.unlink()
        (frags / "+ok.unknowntype.md").write_text("x" * 40)
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
        _expect(results, "changelog/bad-type-rejected", any("type" in f for f in faults), str(faults))

        for stray in frags.iterdir():
            stray.unlink()
        (frags / "+ok.added.md").write_text("x")
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
        _expect(results, "changelog/short-body-rejected", any("floor" in f for f in faults), str(faults))

        for stray in frags.iterdir():
            stray.unlink()
        (frags / "+ok.added.md").write_text("TODO")
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
        _expect(results, "changelog/placeholder-rejected", any("placeholder" in f for f in faults), str(faults))

        for stray in frags.iterdir():
            stray.unlink()
        (frags / "+ok.added.md").write_text("- bulleted body of plenty of length to pass the floor")
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
        _expect(results, "changelog/leading-bullet-rejected", any("bullet" in f for f in faults), str(faults))

        for stray in frags.iterdir():
            stray.unlink()
        (frags / "+leftover.added.md").write_text("x" * 40)
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version="1.0.0", require_fragments_empty=True)
        _expect(
            results, "changelog/unfolded-fragment-rejected",
            any("still on disk" in f for f in faults), str(faults),
        )

        # Empty changelog.d/ alone is not "done" — a tag whose fold never
        # landed a `## [X.Y.Z]` section must still be rejected even though
        # there is nothing left to unfold. This is the exact gap a
        # `require_fragments_empty` short-circuit would reopen.
        for stray in frags.iterdir():
            stray.unlink()
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version="1.0.0", require_fragments_empty=True)
        _expect(
            results, "changelog/missing-heading-rejected-even-when-folded",
            any("no '## [1.0.0]' entry" in f for f in faults), str(faults),
        )

        (root / "CHANGELOG.md").write_text(
            "<!-- towncrier release notes start -->\n\n## [1.0.0] - 2026-01-01\n\nNotes.\n"
        )
        faults = _changelog.check(root, _CHANGELOG_MANIFEST, version="1.0.0", require_fragments_empty=True)
        _expect(results, "changelog/folded-empty-and-headed-accepted", not faults, str(faults))

        if have_towncrier:
            (frags / "+real-fragment.added.md").write_text(
                "A real, sufficiently long note describing an actual user-visible change."
            )
            faults = _changelog.check(root, _CHANGELOG_MANIFEST, version=None, require_fragments_empty=False)
            _expect(results, "changelog/towncrier-draft-nonvacuous", not faults, str(faults))
        else:
            results.append(("changelog/towncrier-draft-nonvacuous", _SKIP, "towncrier not on PATH"))


def _notes_cases(results: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "changelog.d").mkdir()

        faults, _ = _changelog.notes(root, _CHANGELOG_MANIFEST, "1.0.0", "o/r")
        _expect(results, "notes/missing-file-rejected", bool(faults), str(faults))

        (root / "CHANGELOG.md").write_text(
            "<!-- towncrier release notes start -->\n\n"
            "## [2.0.0] - 2026-02-02\n\n### Added\n\n- the newer one\n\n"
            "## [1.0.0] - 2026-01-01\n\n### Added\n\n- the older one\n"
        )
        faults, _ = _changelog.notes(root, _CHANGELOG_MANIFEST, "3.0.0", "o/r")
        _expect(results, "notes/absent-version-rejected", bool(faults), str(faults))

        # The section must stop at the next release, not run to end of file:
        # the failure mode is a release page that republishes its ancestors.
        faults, body = _changelog.notes(root, _CHANGELOG_MANIFEST, "2.0.0", "o/r")
        _expect(
            results, "notes/section-stops-at-next-release",
            not faults and "the newer one" in body and "the older one" not in body, body,
        )

        # And the last section in the file has no next heading to stop at.
        faults, body = _changelog.notes(root, _CHANGELOG_MANIFEST, "1.0.0", "o/r")
        _expect(
            results, "notes/last-section-reaches-eof",
            not faults and "the older one" in body, body,
        )

        # Every caller passes `github.ref_name`, which is tag-shaped.
        faults, tagged = _changelog.notes(root, _CHANGELOG_MANIFEST, "v1.0.0", "o/r")
        _expect(
            results, "notes/tag-shaped-version-accepted",
            not faults and tagged == body, str(faults),
        )

        # `### ` is a subsection, not a boundary — a naive `line.startswith("##")`
        # would truncate every release at its own first category heading.
        _expect(
            results, "notes/subsection-heading-kept",
            "### Added" in body, body,
        )

        (root / "CHANGELOG.md").write_text("## [1.0.0] - 2026-01-01\n\n")
        faults, _ = _changelog.notes(root, _CHANGELOG_MANIFEST, "1.0.0", "o/r")
        _expect(results, "notes/empty-section-rejected", bool(faults), str(faults))

        # Over GitHub's ceiling the body must still post: truncated at a whole
        # bullet and linked, never rejected with the tag already immutable.
        bullet = "- " + "x" * 200 + "\n"
        (root / "CHANGELOG.md").write_text(
            "## [1.0.0] - 2026-01-01\n\n### Added\n\n" + bullet * 900
        )
        faults, body = _changelog.notes(root, _CHANGELOG_MANIFEST, "1.0.0", "o/r")
        _expect(
            results, "notes/over-ceiling-truncated-not-rejected",
            not faults and 0 < len(body) <= _changelog.CEILING, f"{len(body)} chars",
        )
        _expect(
            results, "notes/over-ceiling-cut-at-bullet-and-linked",
            "blob/v1.0.0/CHANGELOG.md#100---2026-01-01" in body
            and body[: body.index("\n\nThis section is")].rstrip().endswith("x" * 200),
            body[-200:],
        )


def _github_cases(results: list) -> None:
    def transport_success(_url: str, _headers: dict) -> tuple[int, str]:
        return 200, '{"check_runs": [{"name": "release-ready", "status": "completed", "conclusion": "success"}]}'

    ok, msg = _github.check_run_status(
        "The-Billy-Company/irregex", "deadbeef", "release-ready", "tok",
        transport=transport_success, sleep=lambda _s: None,
    )
    _expect(results, "github/ci-status-success-accepted", ok, msg)

    def transport_failure(_url: str, _headers: dict) -> tuple[int, str]:
        return 200, '{"check_runs": [{"name": "release-ready", "status": "completed", "conclusion": "failure"}]}'

    ok, msg = _github.check_run_status(
        "The-Billy-Company/irregex", "deadbeef", "release-ready", "tok",
        transport=transport_failure, sleep=lambda _s: None,
    )
    _expect(results, "github/ci-status-failure-rejected", not ok, msg)

    def transport_missing(_url: str, _headers: dict) -> tuple[int, str]:
        return 200, '{"check_runs": []}'

    ok, msg = _github.check_run_status(
        "The-Billy-Company/irregex", "deadbeef", "release-ready", "tok",
        timeout_seconds=0, transport=transport_missing, sleep=lambda _s: None,
    )
    _expect(results, "github/ci-status-missing-rejected-on-timeout", not ok, msg)

    def transport_ancestor(_url: str, _headers: dict) -> tuple[int, str]:
        return 200, '{"status": "ahead"}'

    ok, msg = _github.tag_is_ancestor(
        "The-Billy-Company/irregex", "deadbeef", "main", "tok", transport=transport_ancestor
    )
    _expect(results, "github/tag-ancestor-accepted", ok, msg)

    def transport_diverged(_url: str, _headers: dict) -> tuple[int, str]:
        return 200, '{"status": "diverged"}'

    ok, msg = _github.tag_is_ancestor(
        "The-Billy-Company/irregex", "deadbeef", "main", "tok", transport=transport_diverged
    )
    _expect(results, "github/tag-diverged-rejected", not ok, msg)


def _registry_cases(results: list) -> None:
    absent = lambda _url, _headers: (404, "")  # noqa: E731
    present = lambda _url, _headers: (200, "{}")  # noqa: E731
    broken = lambda _url, _headers: (503, "")  # noqa: E731

    _expect(results, "registry/pypi-absent", _registry.pypi_state("x", "1.0.0", absent) == "absent", "")
    _expect(results, "registry/pypi-present", _registry.pypi_state("x", "1.0.0", present) == "present", "")
    _expect(results, "registry/pypi-error-not-absent", _registry.pypi_state("x", "1.0.0", broken) == "error", "")
    _expect(results, "registry/crates-absent", _registry.crates_state("x", "1.0.0", absent) == "absent", "")
    _expect(results, "registry/crates-present", _registry.crates_state("x", "1.0.0", present) == "present", "")


def run() -> int:
    results: list[tuple[str, str, str]] = []
    _version_cases(results)
    _changelog_cases(results)
    _notes_cases(results)
    _github_cases(results)
    _registry_cases(results)
    return _report(results)
