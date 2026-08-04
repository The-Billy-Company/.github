"""Fragments are the release notes. Prove they exist, parse, and fold.

`towncrier build --draft` alone is not the gate: it silently drops any
filename it cannot parse and happily renders a clean changelog over that
silence, so a fragment named `.fixd.md` instead of `.fixed.md` disappears
with no complaint. This checks the filenames and bodies itself — with a
message that names the exact file and the exact rule — and then still shells
to `towncrier` for the belt-and-suspenders vacuous-green guard, because the
two catch different failure shapes.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

PLACEHOLDER = re.compile(r"^(todo|tbd|wip|fill.?in|placeholder|xxx)\W*$", re.IGNORECASE)


def _fragments(directory: pathlib.Path, ignore: set[str]) -> list[pathlib.Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.name not in ignore)


def _validate_name(name: str, stem_pattern: re.Pattern[str], types: list[str]) -> str | None:
    parts = name.rsplit(".", 2)
    if len(parts) != 3 or parts[2] != "md":
        return f"{name}: not a <stem>.<type>.md fragment"
    stem, kind = parts[0], parts[1]
    if kind not in types:
        return f"{name}: type {kind!r} is not one of {types}"
    if not stem_pattern.match(stem):
        return f"{name}: stem {stem!r} does not match the required shape {stem_pattern.pattern!r}"
    return None


def _validate_body(name: str, text: str, min_chars: int) -> str | None:
    body = text.strip()
    if PLACEHOLDER.match(body):
        return f"{name}: body is a placeholder ({body!r}) — write the real note"
    if len(body) < min_chars:
        return f"{name}: body is {len(body)} chars, shorter than the {min_chars}-char floor — say what changed"
    first_line = body.splitlines()[0].lstrip()
    if first_line.startswith(("- ", "* ")):
        return f"{name}: body starts with a bare list marker — towncrier already renders the bullet"
    return None


def _towncrier_draft(root: pathlib.Path, version: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["towncrier", "build", "--draft", "--version", version],
        cwd=root, capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def check(
    root: pathlib.Path,
    changelog: dict,
    version: str | None,
    require_fragments_empty: bool,
) -> list[str]:
    faults: list[str] = []
    directory = root / changelog["directory"]
    ignore = set(changelog.get("ignore", []))
    types = list(changelog["types"])
    stem_pattern = re.compile(changelog["stem_pattern"])
    min_chars = int(changelog.get("min_body_chars", 20))

    fragments = _fragments(directory, ignore)

    # On a tag, "the changelog is done" is two independent facts, and both are
    # required — every fragment folded AND the exact section it was folded
    # into. `require_fragments_empty` only ever narrows which pre-fold checks
    # apply (there is nothing left to lint the name/body of, and no draft to
    # render); it must never skip the post-fold heading check below, or a tag
    # with an empty changelog.d/ and no matching `## [X.Y.Z]` section at all
    # would read as clean.
    if require_fragments_empty:
        if fragments:
            names = ", ".join(p.name for p in fragments)
            faults.append(
                f"{directory}: {len(fragments)} fragment(s) still on disk after the release build "
                f"({names}) — fold them with `towncrier build --version {version}` and commit the result"
            )
    else:
        for path in fragments:
            if issue := _validate_name(path.name, stem_pattern, types):
                faults.append(issue)
                continue
            if issue := _validate_body(path.name, path.read_text(encoding="utf-8"), min_chars):
                faults.append(issue)

        if shutil.which("towncrier") is None:
            print("::warning::towncrier is not on PATH — skipping the draft-render check "
                  "(the action's composite step installs it; a bare local run does not)", file=sys.stderr)
        else:
            draft_version = version or "0.0.0"
            code, out, err = _towncrier_draft(root, draft_version)
            if code != 0:
                faults.append(f"towncrier build --draft failed (exit {code}): {err.strip() or out.strip()}")
            elif fragments and "No significant changes" in out:
                faults.append(
                    f"{len(fragments)} fragment(s) on disk but towncrier rendered none — "
                    "the wiring (directory/ignore/type config) is broken, not the tree"
                )

    if version is not None:
        heading = f"## [{version}]"
        changelog_text = (root / changelog["file"]).read_text(encoding="utf-8")
        if not any(line.startswith(heading) for line in changelog_text.splitlines()):
            faults.append(
                f"{changelog['file']}: no {heading!r} entry — "
                f"run `towncrier build --version {version}` and commit it before tagging"
            )

    return faults
