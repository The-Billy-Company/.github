"""One declared version, many mirrors — prove they still agree.

Generalizes the per-repo `tools/version_parity.py` copies that used to hand-roll
this same walk against a hardcoded `build.zig.zon` authority. The authority is
now a `release.toml` fact (`[package] version_source` + `version_kind`), so the
same walk serves Zig packages (`build.zig.zon`), a Cargo workspace (`zoning`),
and a single Cargo package (`sheng`, `brigade`) without three copies of the walk.
"""

from __future__ import annotations

import json
import pathlib
import re

MARKER = "x-release-please-version"
SEMVER = re.compile(r"\b\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\b")
ZON_VERSION = re.compile(r"\.version\s*=\s*\"([^\"]+)\"")
CARGO_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)

# Build output, vendored trees, and package caches — these hold stale copies of
# our own files (and other projects' versions), so walking them turns a parity
# gate into a scavenger hunt. Release notes are excluded for the same reason
# `tools/version_parity.py` excluded them: their whole subject is versions, so
# a past entry can name this marker and a number in one sentence and read as a
# mirror to any line-level heuristic — and they are the one place the release
# bot must never rewrite, since a past release's number is history, not a copy
# of the current one.
SKIP = {
    ".git", ".zig-cache", "zig-cache", "zig-out", "zig-pkg", ".local",
    "target", "vendor", "node_modules", "__pycache__", ".venv",
    ".pytest_cache", ".ruff_cache", "testdata", "changelog.d", "CHANGELOG.md",
}
SUFFIXES = {".zon", ".toml", ".py", ".rs", ".go", ".zig", ".h", ".json", ".md", ".yml", ".yaml"}

KINDS = {
    "zig-zon": ZON_VERSION,
    "cargo-workspace": CARGO_VERSION,
    "cargo-package": CARGO_VERSION,
}


def declared_version(root: pathlib.Path, source: str, kind: str) -> str:
    path = root / source
    if not path.is_file():
        raise SystemExit(f"version: version_source {source!r} does not exist under {root}")
    pattern = KINDS.get(kind)
    if pattern is None:
        raise SystemExit(f"version: unknown version_kind {kind!r} (want one of {sorted(KINDS)})")
    text = path.read_text(encoding="utf-8")
    if kind == "cargo-workspace":
        # `[workspace.package]` is one table among several `version = "..."`
        # lines a Cargo.toml can carry (dependencies, other members) — narrow
        # to the table itself rather than the first match in the file.
        table = text.split("[workspace.package]", 1)
        if len(table) != 2:
            raise SystemExit(f"version: {source} has no [workspace.package] table")
        text = table[1].split("\n[", 1)[0]
    elif kind == "cargo-package":
        table = text.split("[package]", 1)
        if len(table) != 2:
            raise SystemExit(f"version: {source} has no [package] table")
        text = table[1].split("\n[", 1)[0]
    found = pattern.search(text)
    if not found:
        raise SystemExit(f"version: {source} declares no version under version_kind={kind!r}")
    return found.group(1)


def marked_mirrors(root: pathlib.Path, here: pathlib.Path) -> list[tuple[pathlib.Path, int, str]]:
    """Every mirror line in the tree — marker plus a version — in walk order."""
    out: list[tuple[pathlib.Path, int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if SKIP & set(path.relative_to(root).parts) or path.resolve() == here:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if MARKER not in text:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if MARKER in line and SEMVER.search(line):
                out.append((path.relative_to(root), number, line.strip()))
    return out


def declared_extra_files(root: pathlib.Path) -> set[str] | None:
    """Paths release-please was told to rewrite, or None if it isn't wired yet."""
    config = root / "release-please-config.json"
    if not config.is_file():
        return None
    packages = json.loads(config.read_text(encoding="utf-8")).get("packages", {})
    return {
        entry["path"]
        for package in packages.values()
        for entry in package.get("extra-files", [])
        if isinstance(entry, dict) and "path" in entry
    }


def check(root: pathlib.Path, package: dict, tag: str | None) -> tuple[list[str], str]:
    """Return (faults, declared_version)."""
    source = package["version_source"]
    kind = package["version_kind"]
    want = declared_version(root, source, kind)
    here = pathlib.Path(__file__).resolve()
    mirrors = marked_mirrors(root, here)
    declared = declared_extra_files(root)

    faults: list[str] = []
    for path, number, line in mirrors:
        got = SEMVER.search(line).group(0)
        if got != want:
            faults.append(f"{path}:{number}: mirrors {got}, but {source} declares {want} — {line}")

    if not any(str(m[0]) == source for m in mirrors):
        faults.append(f"{source}: carries no {MARKER} marker — the release bot would never move it")

    if declared is not None:
        for path, _number, _line in mirrors:
            if str(path) not in declared:
                faults.append(
                    f"{path}: mirrors the version, but is absent from "
                    "release-please-config.json's extra-files — the bot would skip it"
                )

    if tag is not None:
        bare = tag.removeprefix("v")
        if bare != want:
            faults.append(
                f"tag {tag!r} would publish version {want} — "
                f"tag the version {source} declares, or bump {source} first"
            )

    return faults, want
