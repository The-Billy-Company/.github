"""Fragments are the release notes. Prove they exist, parse, and fold — then
hand the folded section to the GitHub Release that names it.

`towncrier build --draft` alone is not the gate: it silently drops any
filename it cannot parse and happily renders a clean changelog over that
silence, so a fragment named `.fixd.md` instead of `.fixed.md` disappears
with no complaint. This checks the filenames and bodies itself — with a
message that names the exact file and the exact rule — and then still shells
to `towncrier` for the belt-and-suspenders vacuous-green guard, because the
two catch different failure shapes.

`notes` closes the other end. release-please's `skip-changelog` stops the bot
writing CHANGELOG.md so towncrier can own it, but that key governs the *file*;
composing the release **body** is a separate path inside release-please and
still runs, off conventional-commit subjects filtered through
`changelog-sections`. A repo whose real notes are fragments therefore ships a
release page built from commit subjects — irregex v2.1.1 published two lines
against a hundred and ten, because eleven of its thirteen commits were `ci:`
and `docs:` and both are `hidden`.
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
        if _section(root / changelog["file"], version) is None:
            faults.append(
                f"{changelog['file']}: no '## [{version}]' entry — "
                f"run `towncrier build --version {version}` and commit it before tagging"
            )

    return faults


# --- notes: the folded section, rendered for a GitHub Release body ----------

# GitHub rejects a release body over 125,000 characters. Held a little under
# it: the notice a truncation appends has to fit inside the same budget.
CEILING = 125_000
NOTICE_BUDGET = 400


def _section(changelog: pathlib.Path, version: str) -> tuple[str, str] | None:
    """One version's heading and body, or None if the fold never landed it.

    The span runs from `## [VERSION]` to the next `## ` at column zero, so a
    `### Added` subsection cannot end it early. The body is towncrier's own
    render — the same bytes `towncrier build --draft` printed on the release
    PR — so posting it is fidelity-preserving rather than a second opinion.
    """
    if not changelog.is_file():
        return None
    lines = changelog.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if match := re.match(r"^## \[([^\]]+)\]", line):
            if match[1] == version:
                start = i
            elif start is not None:
                return lines[start], "\n".join(lines[start + 1 : i]).strip("\n")
        elif line.startswith("## ") and start is not None:
            return lines[start], "\n".join(lines[start + 1 : i]).strip("\n")
    if start is None:
        return None
    return lines[start], "\n".join(lines[start + 1 :]).strip("\n")


def _anchor(heading: str) -> str:
    """GitHub's own slug for a heading, so a truncation links where it says."""
    text = heading.removeprefix("## ").strip().lower()
    return "#" + re.sub(r"[^\w -]", "", text).replace(" ", "-")


def notes(root: pathlib.Path, changelog: dict, version: str, repo: str | None) -> tuple[list[str], str]:
    """Render the release body for `version`, and any fault that blocks it.

    The version is accepted tag-shaped (`v1.2.3`) as well as bare, because
    every caller is a tag-triggered workflow holding `github.ref_name` and
    nothing else. Normalizing here rather than in six workflows is the
    difference between one rule and six chances to forget it.
    """
    version = version.removeprefix("v")
    found = _section(root / changelog["file"], version)
    if found is None:
        return [
            f"{changelog['file']}: no '## [{version}]' section to publish — the fold "
            f"never ran for this version, or the tag names a version nothing released"
        ], ""
    heading, body = found
    if not body:
        return [f"{changelog['file']}: the '## [{version}]' section is empty"], ""
    if len(body) <= CEILING:
        return [], body + "\n"

    # Over the ceiling the API would reject the whole body with the tag already
    # pushed and immutable, so this posts what fits: cut at a top-level bullet
    # rather than mid-sentence, which is the difference between a shortened
    # page and a corrupted one.
    slug = repo or "OWNER/REPO"
    link = f"https://github.com/{slug}/blob/v{version}/{changelog['file']}{_anchor(heading)}"
    notice = (
        f"\n\nThis section is {len(body):,} characters and GitHub holds "
        f"{CEILING:,}. The rest is in [{changelog['file']}]({link})."
    )
    if len(notice) > NOTICE_BUDGET:  # pragma: no cover - the URL would have to be absurd
        return ["the truncation notice does not fit its own budget"], ""
    keep = body[: CEILING - NOTICE_BUDGET]
    if (cut := keep.rfind("\n- ")) > 0:
        keep = keep[:cut]
    print(
        f"::notice::{version} is {len(body):,} chars against GitHub's {CEILING:,}; "
        f"posted {len(keep):,} to a bullet boundary and linked the rest",
        file=sys.stderr,
    )
    return [], keep.rstrip() + notice + "\n"
