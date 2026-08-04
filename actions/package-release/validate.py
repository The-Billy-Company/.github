#!/usr/bin/env python3
"""package-release — the one release contract every Billy-Company OSS repo runs.

Six commands, each answering exactly one question a release must not get
wrong. Every command prints `::error::`-annotated faults on stderr (so they
surface directly on the GitHub Actions run) and exits non-zero on any fault;
`--json` gets the same facts as a machine-readable report instead.

    version    <root>                 does the declared version agree with
                                       every mirror (and, with --tag, the tag)?
    changelog  <root>                 are the fragments well-formed, and does
                                       towncrier actually render them?
    ci-status  <owner/repo> <sha>     did the required check succeed on this
                                       exact commit?
    tag-ancestor <owner/repo> <sha>   is this commit reachable from the
                                       protected branch, or a stray push?
    registry-probe <pypi|crates>      is this version already published?
    selftest                          offline proof the five commands above
                                       reject what they claim to reject.

See README.md for the `release.toml` schema every command but `selftest`
reads from `--root`.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _changelog
import _github
import _registry
import _selftest
import _version


def _load_manifest(root: pathlib.Path, path: str) -> dict:
    manifest = root / path
    if not manifest.is_file():
        raise SystemExit(f"release contract: {manifest} does not exist — see action README.md")
    return tomllib.loads(manifest.read_text(encoding="utf-8"))


def _emit(faults: list[str], as_json: bool, extra: dict | None = None) -> int:
    if as_json:
        print(json.dumps({"faults": faults, **(extra or {})}, indent=2))
    else:
        for fault in faults:
            print(f"::error::{fault}", file=sys.stderr)
        if not faults:
            print("ok" if not extra else json.dumps(extra))
    return 1 if faults else 0


def cmd_version(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    contract = _load_manifest(root, args.manifest)
    faults, version = _version.check(root, contract["package"], args.tag)
    return _emit(faults, args.json, {"version": version})


def cmd_changelog(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.root).resolve()
    contract = _load_manifest(root, args.manifest)
    faults = _changelog.check(root, contract["changelog"], args.version, args.require_fragments_empty)
    return _emit(faults, args.json)


def cmd_ci_status(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("ci-status: no token (pass --token or set GITHUB_TOKEN)")
    ok, message = _github.check_run_status(
        args.repo, args.sha, args.check_name, token, args.timeout_seconds, args.interval_seconds
    )
    return _emit([] if ok else [message], args.json)


def cmd_tag_ancestor(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("tag-ancestor: no token (pass --token or set GITHUB_TOKEN)")
    ok, message = _github.tag_is_ancestor(args.repo, args.sha, args.branch, token)
    return _emit([] if ok else [message], args.json)


def cmd_registry_probe(args: argparse.Namespace) -> int:
    state = (_registry.pypi_state if args.registry == "pypi" else _registry.crates_state)(
        args.name, args.version
    )
    if args.json:
        print(json.dumps({"registry": args.registry, "name": args.name, "version": args.version, "state": state}))
    else:
        print(state)
    return 2 if state == "error" else 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    return _selftest.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    common = {"root": lambda p: p.add_argument("--root", default="."), }

    p = sub.add_parser("version")
    common["root"](p)
    p.add_argument("--manifest", default="release.toml")
    p.add_argument("--tag", default=None, help="the git ref name being released, e.g. v1.2.3")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_version)

    p = sub.add_parser("changelog")
    common["root"](p)
    p.add_argument("--manifest", default="release.toml")
    p.add_argument("--version", default=None, help="require a `## [VERSION]` CHANGELOG heading")
    p.add_argument("--require-fragments-empty", action="store_true",
                    help="assert every fragment was folded (post release-build state)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_changelog)

    p = sub.add_parser("ci-status")
    p.add_argument("repo", help="owner/name")
    p.add_argument("sha")
    p.add_argument("--check-name", default="release-ready")
    p.add_argument("--token", default=None)
    p.add_argument("--timeout-seconds", type=int, default=900)
    p.add_argument("--interval-seconds", type=int, default=15)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ci_status)

    p = sub.add_parser("tag-ancestor")
    p.add_argument("repo", help="owner/name")
    p.add_argument("sha")
    p.add_argument("--branch", default="main")
    p.add_argument("--token", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_tag_ancestor)

    p = sub.add_parser("registry-probe")
    p.add_argument("registry", choices=["pypi", "crates"])
    p.add_argument("name")
    p.add_argument("version")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_registry_probe)

    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
