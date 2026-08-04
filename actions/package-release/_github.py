"""Two questions the GitHub REST API answers, asked before a publish starts.

Both take a `transport` so `--selftest` can prove the decision logic against
canned responses with no network and no token — the only thing worth trusting
less than "it passed once against the live API" is "it was never proven at all".
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

Transport = "typing.Callable[[str, dict], tuple[int, str]]"  # str alias, no import needed


def live_transport(url: str, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https host)
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def check_run_status(
    repo: str,
    sha: str,
    check_name: str,
    token: str,
    timeout_seconds: int = 900,
    interval_seconds: int = 15,
    transport=live_transport,
    sleep=time.sleep,
) -> tuple[bool, str]:
    """Poll for one named check-run on `sha`, and require it to have passed."""
    deadline = time.monotonic() + timeout_seconds
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    while True:
        status, body = transport(url, _headers(token))
        if status != 200:
            return False, f"check-runs lookup failed ({status}): {body[:300]}"
        runs = [r for r in json.loads(body).get("check_runs", []) if r.get("name") == check_name]
        if runs:
            run = runs[0]
            if run.get("status") != "completed":
                pass  # still running — fall through to the wait below
            elif run.get("conclusion") == "success":
                return True, f"{check_name!r} succeeded on {sha}"
            else:
                return False, f"{check_name!r} concluded {run.get('conclusion')!r} on {sha} — not publishing"
        if time.monotonic() >= deadline:
            seen = "found but incomplete" if runs else "never appeared"
            return False, f"{check_name!r} {seen} on {sha} within {timeout_seconds}s — not publishing"
        sleep(interval_seconds)


def tag_is_ancestor(
    repo: str,
    sha: str,
    branch: str,
    token: str,
    transport=live_transport,
) -> tuple[bool, str]:
    """Is `sha` reachable from `branch`'s tip? Rejects a tag cut off a stray commit."""
    url = f"https://api.github.com/repos/{repo}/compare/{sha}...{branch}"
    status, body = transport(url, _headers(token))
    if status != 200:
        return False, f"compare lookup failed ({status}): {body[:300]}"
    result = json.loads(body).get("status")
    if result in ("identical", "ahead"):
        return True, f"{sha} is reachable from {branch} ({result})"
    return False, f"{sha} is not reachable from {branch} (compare status {result!r}) — refusing to publish"
