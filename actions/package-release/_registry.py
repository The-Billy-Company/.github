"""Ask a registry whether a version already exists, before minting a credential.

Both probes answer the same three-way question: `absent` (publish it),
`present` (a prior run already got there — a retry is success, not a
collision), or `error` (the registry itself did not answer — never treated
as `absent`, so a network blip cannot masquerade as a green light to publish).
"""

from __future__ import annotations

from _github import live_transport


def pypi_state(name: str, version: str, transport=live_transport) -> str:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    status, _body = transport(url, {})
    if status == 200:
        return "present"
    if status == 404:
        return "absent"
    return "error"


def crates_state(name: str, version: str, transport=live_transport) -> str:
    url = f"https://crates.io/api/v1/crates/{name}/{version}"
    headers = {"User-Agent": "billy-company-package-release (github.com/The-Billy-Company/.github)"}
    status, _body = transport(url, headers)
    if status == 200:
        return "present"
    if status == 404:
        return "absent"
    return "error"
