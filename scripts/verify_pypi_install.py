"""Verify a published docsgraph package from the public Python index."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        default=None,
        help="Version to install. Defaults to the current pyproject version.",
    )
    parser.add_argument(
        "--index-url",
        default="https://pypi.org/simple",
        help="Python package index URL to install from.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Optional initialized repo to smoke-test MCP config against.",
    )
    parser.add_argument(
        "--sync-repo",
        action="store_true",
        help="Run docsgraph sync/status/query in --repo after installing.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    version = args.version or _project_version(root / "pyproject.toml")
    requirement = f"docsgraph=={version}"

    with tempfile.TemporaryDirectory(prefix="docsgraph-pypi-") as tmp:
        venv = Path(tmp) / "venv"
        python = _create_venv(venv)
        _install(python, args.index_url, requirement)

        docsgraph = _script_path(venv, "docsgraph")
        cairn = _script_path(venv, "cairn")
        _run([str(docsgraph), "--help"])
        _run([str(cairn), "--help"])
        _run([str(docsgraph), "version"], expected=version)

        _run(
            [
                str(python),
                "-c",
                (
                    "from importlib.metadata import metadata, version; "
                    "m=metadata('docsgraph'); "
                    "print(m['Name']); print(version('docsgraph'))"
                ),
            ],
            expected=f"docsgraph\n{version}",
        )

        if args.repo is not None:
            repo = args.repo.resolve()
            _run(
                [
                    str(docsgraph),
                    "mcp",
                    "config",
                    "--client",
                    "codex",
                    "--repo",
                    str(repo),
                    "--fake",
                ],
                cwd=repo,
                expected='command = "docsgraph"',
            )
            if args.sync_repo:
                _run([str(docsgraph), "sync", "--fake"], cwd=repo)
                _run([str(docsgraph), "status"], cwd=repo, expected="documents:")
                _run(
                    [
                        str(docsgraph),
                        "query",
                        "repo",
                        "what is this project?",
                        "--fake",
                    ],
                    cwd=repo,
                    expected='"hits"',
                )

    print(f"verified {requirement} from {args.index_url}")
    return 0


def _project_version(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _create_venv(venv: Path) -> Path:
    uv = shutil.which("uv")
    if uv:
        _run([uv, "venv", str(venv)])
        return _venv_python(venv)

    _run([sys.executable, "-m", "venv", str(venv)])
    python = _venv_python(venv)
    _run([str(python), "-m", "ensurepip", "--upgrade"])
    return python


def _install(python: Path, index_url: str, requirement: str) -> None:
    uv = shutil.which("uv")
    if uv:
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--index-url",
                index_url,
                requirement,
            ]
        )
        return
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--index-url",
            index_url,
            requirement,
        ]
    )


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _script_path(venv: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    directory = "Scripts" if sys.platform == "win32" else "bin"
    return venv / directory / f"{name}{suffix}"


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    expected: str | None = None,
) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        raise SystemExit(result.returncode)
    if expected is not None and expected not in result.stdout:
        print(result.stdout, file=sys.stderr)
        msg = f"expected output to contain: {expected!r}"
        raise SystemExit(msg)
    return result.stdout


if __name__ == "__main__":
    raise SystemExit(main())
