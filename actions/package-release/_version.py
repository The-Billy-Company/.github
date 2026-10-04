"""One declared version, many mirrors — prove they still agree.

Generalizes the per-repo `tools/version_parity.py` copies that used to hand-roll
this same walk against a hardcoded `build.zig.zon` authority. The authority is
now a `release.toml` fact (`[package] version_source` + `version_kind`), so the
same walk serves Zig packages (`build.zig.zon`), a Cargo workspace (`zoning`),
and a single Cargo package (`sheng`, `brigade`) without three copies of the walk.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tomllib

MARKER = "x-release-please-version"
SEMVER = re.compile(r"\b\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\b")

# Build output, vendored trees, and package caches — these hold stale copies of
# our own files (and other projects' versions), so walking them turns a parity
# gate into a scavenger hunt. Release notes are excluded for the same reason
# `tools/version_parity.py` excluded them: their whole subject is versions, so
# a past entry can name this marker and a number in one sentence and read as a
# mirror to any line-level heuristic — and they are the one place the release
# bot must never rewrite, since a past release's number is history, not a copy
# of the current one.
SKIP = {
    ".git",
    ".zig-cache",
    "zig-cache",
    "zig-out",
    "zig-pkg",
    ".local",
    "target",
    "vendor",
    "node_modules",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "testdata",
    "changelog.d",
    "CHANGELOG.md",
}
SUFFIXES = {
    ".zon",
    ".toml",
    ".py",
    ".rs",
    ".go",
    ".zig",
    ".h",
    ".json",
    ".md",
    ".yml",
    ".yaml",
}

KINDS = {"zig-zon", "cargo-workspace", "cargo-package"}


def _cargo_version(data: dict, kind: str) -> str:
    table = (
        data["workspace"]["package"] if kind == "cargo-workspace" else data["package"]
    )
    version = table["version"]
    if not isinstance(version, str):
        raise ValueError(
            "the authority must be a version string, not an inherited or numeric value"
        )
    return version


def _declared_authority(
    root: pathlib.Path, source: str, kind: str
) -> tuple[str, int | None]:
    path = root / source
    if not path.is_file():
        raise SystemExit(
            f"version: version_source {source!r} does not exist under {root}"
        )
    if kind not in KINDS:
        raise SystemExit(
            f"version: unknown version_kind {kind!r} (want one of {sorted(KINDS)})"
        )
    try:
        line = None
        if kind == "zig-zon":
            parser = pathlib.Path(__file__).with_name("_zon.zig")
            result = subprocess.run(
                ["zig", "run", str(parser), "--", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise ValueError(result.stderr.strip())
            authority = json.loads(result.stdout)
            version, line = authority["version"], authority["line"]
        else:
            version = _cargo_version(
                tomllib.loads(path.read_text(encoding="utf-8")), kind
            )
        if not SEMVER.fullmatch(version):
            raise ValueError(f"invalid version string {version!r}")
        return version, line
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(
            f"version: {source} has no valid {kind} authority: {error}"
        ) from error


def declared_version(root: pathlib.Path, source: str, kind: str) -> str:
    return _declared_authority(root, source, kind)[0]


def marked_mirrors(
    root: pathlib.Path, here: pathlib.Path
) -> list[tuple[pathlib.Path, int, str]]:
    """Every mirror line, ordered by path, without descending into skipped trees."""
    out: list[tuple[pathlib.Path, int, str]] = []
    paths = []
    for directory, children, files in os.walk(root):
        children[:] = [name for name in children if name not in SKIP]
        paths.extend(
            pathlib.Path(directory) / name
            for name in files
            if name not in SKIP and pathlib.Path(name).suffix in SUFFIXES
        )
    for path in sorted(paths):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if path.resolve() == here:
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
    want, authority_line = _declared_authority(root, source, kind)
    here = pathlib.Path(__file__).resolve()
    mirrors = marked_mirrors(root, here)
    declared = declared_extra_files(root)

    faults: list[str] = []
    for path, number, line in mirrors:
        got = SEMVER.search(line).group(0)
        if got != want:
            faults.append(
                f"{path}:{number}: mirrors {got}, but {source} declares {want} — {line}"
            )

    source_mirrors = [m for m in mirrors if str(m[0]) == source]
    if authority_line is not None:
        source_mirrors = [m for m in source_mirrors if m[1] == authority_line]
    if kind.startswith("cargo-"):
        # release-please rewrites only the marked line. A dependency's marker
        # or a comment naming the authority cannot stand in for that line.
        lines = (root / source).read_text(encoding="utf-8").splitlines(keepends=True)
        authorities = []
        for mirror in source_mirrors:
            number = mirror[1]
            try:
                _cargo_version(tomllib.loads("".join(lines[: number - 1])), kind)
            except (KeyError, TypeError, ValueError):
                try:
                    if (
                        _cargo_version(tomllib.loads("".join(lines[:number])), kind)
                        == want
                    ):
                        authorities.append(mirror)
                except (KeyError, TypeError, ValueError):
                    pass
        source_mirrors = authorities
    if not source_mirrors:
        faults.append(
            f"{source}: carries no {MARKER} marker — the release bot would never move it"
        )

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
