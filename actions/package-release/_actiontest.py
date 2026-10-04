"""Exercise the composite entry point against real files, processes and outputs."""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest

import _run

HERE = pathlib.Path(__file__).parent


def fixture(root: pathlib.Path, version: str = "1.2.3") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        f'[package]\nversion="{version}" # x-release-please-version\n'
    )
    (root / "release.toml").write_text(
        '[package]\nversion_source="Cargo.toml"\nversion_kind="cargo-package"\n'
        '[changelog]\ndirectory="changelog.d"\nfile="CHANGELOG.md"\n'
        'ignore=[]\ntypes=["added"]\nstem_pattern="^\\\\+[a-z-]+$"\nmin_body_chars=20\n'
    )
    (root / "CHANGELOG.md").write_text(
        f"## [{version}]\n\nA real release body with its own text.\n"
    )
    (root / "changelog.d").mkdir(exist_ok=True)
    (root / "towncrier.toml").write_text(
        '[tool.towncrier]\ndirectory="changelog.d"\nfilename="CHANGELOG.md"\n'
        'title_format="## [{version}]"\n[[tool.towncrier.type]]\n'
        'directory="added"\nname="Added"\nshowcontent=true\n'
    )
    (root / "changelog.d/+actual-capability.added.md").write_text(
        "We keep quoted paths literal and concurrent release outputs separate."
    )


def invoke(
    directory: pathlib.Path,
    command: str,
    args: list[str] | str,
    prepare: bool = False,
    runner_temp: pathlib.Path | None = None,
):
    output = directory / "output"
    env = {
        **os.environ,
        "RELEASE_COMMAND": command,
        "RELEASE_ARGS": shlex.join(args) if isinstance(args, list) else args,
        "GITHUB_OUTPUT": str(output),
        "RUNNER_TEMP": str(runner_temp or directory),
    }
    result = subprocess.run(
        [sys.executable, str(HERE / "_run.py"), *(["--prepare"] if prepare else [])],
        capture_output=True,
        env=env,
        check=False,
    )
    values = {}
    lines = output.read_text().splitlines() if output.exists() else []
    index = 0
    while index < len(lines):
        name, delimiter = lines[index].split("<<", 1)
        end = lines.index(delimiter, index + 1)
        values[name] = "\n".join(lines[index + 1 : end])
        index = end + 1
    return result, values


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="release-action-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = pathlib.Path(self.tmp.name)
        self.root = (
            self.directory / "root space 'quote' $(touch injected) `touch injected`"
        )
        fixture(self.root)

    def test_quoted_literal_arguments_and_output(self):
        result, values = invoke(
            self.directory, "version", ["--root", str(self.root), "--tag", "v1.2.3"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, ('{"version": "1.2.3"}' + os.linesep).encode())
        self.assertEqual(values["result"], '{"version": "1.2.3"}')
        self.assertFalse((pathlib.Path.cwd() / "injected").exists())
        self.assertEqual(
            sorted(p.name for p in self.directory.iterdir()), ["output", self.root.name]
        )

    def test_failure_preserves_stderr_and_exit(self):
        result, values = invoke(
            self.directory, "version", ["--root", str(self.root), "--tag", "v9.9.9"]
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            b"::error::tag 'v9.9.9' would publish version 1.2.3", result.stderr
        )
        self.assertEqual(result.stdout, b"")
        self.assertEqual(values["result"], "")

    def test_missing_tool_preserves_shell_exit_and_cleanup(self):
        output = self.directory / "output"
        env = {
            **os.environ,
            "PATH": str(self.directory),
            "RELEASE_COMMAND": "selftest",
            "GITHUB_OUTPUT": str(output),
            "RUNNER_TEMP": str(self.directory),
        }
        result = subprocess.run(
            [sys.executable, str(HERE / "_run.py")],
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn(b"uv", result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            sorted(p.name for p in self.directory.iterdir()), ["output", self.root.name]
        )

    def test_json_retains_last_line_contract(self):
        result, values = invoke(
            self.directory, "version", ["--root", str(self.root), "--json"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"faults": [], "version": "1.2.3"})
        self.assertEqual(values["result"], "}")

    def test_prepare_derives_tools_from_native_manifest(self):
        for kind, zig in [("cargo-package", "false"), ("zig-zon", "true")]:
            manifest = self.root / "release.toml"
            text = manifest.read_text().replace("cargo-package", kind)
            manifest.write_text(text)
            result, values = invoke(
                self.directory, "version", ["--root", str(self.root)], prepare=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(values, {"zig": zig, "towncrier": "false"})
            (self.directory / "output").unlink()

    def test_invalid_inputs_fail_before_setup(self):
        for command, args in [
            ("version; touch injected", ""),
            ("version", "--bad-option"),
            ("selftest", "'unclosed"),
            ("selftest", "--root anything"),
        ]:
            result, values = invoke(self.directory, command, args, prepare=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(values, {})
        self.assertFalse((pathlib.Path.cwd() / "injected").exists())

    def test_notes_exact_bytes_and_tag_normalization(self):
        out = self.directory / "notes space 'quote' $(touch injected).md"
        result, values = invoke(
            self.directory,
            "notes",
            ["--root", str(self.root), "--version", "v1.2.3", "--out", str(out)],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            out.read_bytes(),
            ("A real release body with its own text." + os.linesep).encode(),
        )
        self.assertEqual(values["result"], "ok")
        self.assertIn(b"wrote", result.stderr)

    def test_concurrent_calls_keep_private_outputs(self):
        def call(number):
            directory = self.directory / str(number)
            root = directory / "package"
            version = f"1.2.{number}"
            fixture(root, version)
            result, values = invoke(
                directory, "version", ["--root", str(root)], runner_temp=self.directory
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(values["result"]), {"version": version})
            self.assertEqual(
                sorted(p.name for p in directory.iterdir()), ["output", "package"]
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(call, range(8)))


if __name__ == "__main__":
    if sys.argv[1:] == ["--fixture"]:
        root = (
            pathlib.Path(os.environ["RUNNER_TEMP"])
            / "package space 'quote' $(touch injected)"
        )
        fixture(root)
        _run._output("args", shlex.join(["--root", str(root), "--tag", "v1.2.3"]))
        _run._output("bad_args", shlex.join(["--root", str(root), "--tag", "v9.9.9"]))
        _run._output(
            "notes_args",
            shlex.join(
                [
                    "--root",
                    str(root),
                    "--version",
                    "v1.2.3",
                    "--out",
                    str(root / "notes.md"),
                ]
            ),
        )
        _run._output("changelog_args", shlex.join(["--root", str(root)]))
    else:
        unittest.main()
