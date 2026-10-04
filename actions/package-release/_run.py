"""Bind composite-action inputs as arguments and retain the command's output."""

from __future__ import annotations

import os
import pathlib
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile

import validate


def _output(name: str, value: str) -> None:
    delimiter = secrets.token_hex(16)
    while delimiter in value.splitlines():
        delimiter = secrets.token_hex(16)
    with open(
        os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def main(prepare: bool = False) -> int:
    try:
        argv = [
            os.environ["RELEASE_COMMAND"],
            *shlex.split(os.environ.get("RELEASE_ARGS", "")),
        ]
    except (KeyError, ValueError) as error:
        print(f"::error::package-release inputs: {error}", file=sys.stderr)
        return 2

    if prepare:
        # Use the command's own parser and manifest; invalid input fails before
        # downloading tools, and a Cargo authority never pays for a compiler.
        args = validate.parse_args(argv)
        zig = args.command == "selftest"
        if args.command == "version":
            contract = validate._load_manifest(
                pathlib.Path(args.root).resolve(), args.manifest
            )
            zig = contract["package"]["version_kind"] == "zig-zon"
        _output("zig", str(zig).lower())
        _output("towncrier", str(args.command in {"changelog", "selftest"}).lower())
        return 0

    command = [
        sys.executable,
        str(pathlib.Path(__file__).with_name("validate.py")),
        *argv,
    ]
    environment = os.environ.copy()
    towncrier = argv[0] in {"changelog", "selftest"}
    if towncrier:
        environment.setdefault("TZ", "UTC")
        if argv[0] == "changelog" and "SOURCE_DATE_EPOCH" not in environment:
            args = validate.parse_args(argv)
            if shutil.which("git"):
                timestamp = subprocess.run(
                    ["git", "-C", args.root, "show", "-s", "--format=%ct", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if timestamp.returncode == 0:
                    environment["SOURCE_DATE_EPOCH"] = timestamp.stdout.strip()
    # Private per-call files avoid concurrent output corruption and keep large
    # reports off the heap. TemporaryDirectory cleans them after success or failure.
    with tempfile.TemporaryDirectory(
        prefix="package-release-", dir=os.environ.get("RUNNER_TEMP")
    ) as tmp:
        out = pathlib.Path(tmp) / "stdout"
        err = pathlib.Path(tmp) / "stderr"
        commands = [command]
        if towncrier:
            venv = pathlib.Path(tmp) / "env"
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            requirements = pathlib.Path(__file__).with_name("requirements.txt")
            commands = [
                ["uv", "--no-config", "venv", "--python", "3.12", str(venv)],
                [
                    "uv",
                    "--no-config",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "--exclude-newer",
                    "P2D",
                    "--requirements",
                    str(requirements),
                ],
                [str(python), *command[1:]],
            ]
        with out.open("wb") as stdout, err.open("wb") as stderr:
            for command in commands:
                try:
                    code = subprocess.run(
                        command,
                        stdout=stdout,
                        stderr=stderr,
                        env=environment,
                        check=False,
                    ).returncode
                except (FileNotFoundError, PermissionError) as error:
                    stderr.write(f"{error}\n".encode())
                    code = 127 if isinstance(error, FileNotFoundError) else 126
                if code:
                    break
        for path, destination in [(out, sys.stdout.buffer), (err, sys.stderr.buffer)]:
            with path.open("rb") as source:
                shutil.copyfileobj(source, destination)
            destination.flush()
        # Iteration preserves tail -n1 semantics without reading a whole report.
        last = b""
        with out.open("rb") as source:
            for last in source:
                pass
        _output("result", last.rstrip(b"\r\n").decode("utf-8"))
        return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main(prepare=sys.argv[1:] == ["--prepare"]))
