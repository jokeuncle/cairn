"""Prepare and validate release metadata for docsgraph."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help="Release version without the leading v, e.g. 0.1.0a4.")
    parser.add_argument(
        "--date",
        default=datetime.now(UTC).date().isoformat(),
        help="Release date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    parser.add_argument(
        "--repo-doc-count",
        type=int,
        default=None,
        help="Optional current Cairn repo document count to write into the release checklist.",
    )
    parser.add_argument("--check", action="store_true", help="Validate without modifying files.")
    args = parser.parse_args()

    _validate_version(args.version)
    _validate_date(args.date)

    expected = _expected_text(args.version)
    if args.check:
        errors = _check_release(args.version, expected)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"release metadata ok for {args.version}")
        return 0

    _replace_version(ROOT / "pyproject.toml", r'version = "[^"]+"', f'version = "{args.version}"')
    _replace_version(
        ROOT / "src" / "cairn" / "__init__.py",
        r'__version__ = "[^"]+"',
        f'__version__ = "{args.version}"',
    )
    _replace_version(
        ROOT / "README.md",
        r"Alpha — `[^`]+`",
        f"Alpha — `{args.version}`",
    )
    _replace_version(
        ROOT / "docs" / "retrieval-architecture-canvas.html",
        r"0\.1\.0a\d+",
        args.version,
        count=0,
    )
    if args.repo_doc_count is not None:
        _replace_version(
            ROOT / "docs" / "release-checklist.md",
            r"Cairn repo: \d+/\d+ docs indexed, 0 errors\.",
            (
                "Cairn repo: "
                f"{args.repo_doc_count}/{args.repo_doc_count} docs indexed, 0 errors."
            ),
        )

    _update_changelog(args.version, args.date)
    print(f"prepared release metadata for {args.version}")
    return 0


def _validate_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?", version):
        raise SystemExit(f"invalid version: {version}")


def _validate_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid date: {value}") from exc


def _expected_text(version: str) -> dict[str, str]:
    return {
        "pyproject.toml": f'version = "{version}"',
        "src/cairn/__init__.py": f'__version__ = "{version}"',
        "README.md": f"Alpha — `{version}`",
        "CHANGELOG.md": f"## [{version}]",
    }


def _check_release(version: str, expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for relative, needle in expected.items():
        path = ROOT / relative
        if needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative} does not contain {needle!r}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = _unreleased_body(changelog)
    if unreleased and unreleased != "No unreleased changes yet.":
        errors.append("CHANGELOG.md still has unreleased content; run scripts/prepare_release.py")
    if f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md is missing the {version} release section")
    return errors


def _replace_version(path: Path, pattern: str, replacement: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    updated, replacements = re.subn(pattern, replacement, text, count=count)
    if count == 0 and replacements == 0:
        raise SystemExit(f"expected at least one match for {pattern!r} in {path}")
    if count > 0 and replacements != count:
        raise SystemExit(f"expected one match for {pattern!r} in {path}")
    path.write_text(updated, encoding="utf-8")


def _update_changelog(version: str, release_date: str) -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    version_heading = f"## [{version}]"
    if version_heading in text:
        _ensure_empty_unreleased(path, text)
        return

    match = re.search(r"(?ms)^## Unreleased\n(?P<body>.*?)(?=^## )", text)
    if not match:
        raise SystemExit("CHANGELOG.md is missing an Unreleased section")
    body = match.group("body").strip()
    if not body or body == "No unreleased changes yet.":
        body = _generated_changelog_body()

    replacement = (
        "## Unreleased\n\n"
        "No unreleased changes yet.\n\n"
        f"## [{version}] — {release_date}\n\n"
        f"{body}\n\n"
    )
    updated = text[: match.start()] + replacement + text[match.end() :]
    path.write_text(updated, encoding="utf-8")


def _ensure_empty_unreleased(path: Path, text: str) -> None:
    match = re.search(r"(?ms)^## Unreleased\n(?P<body>.*?)(?=^## )", text)
    if not match:
        raise SystemExit("CHANGELOG.md is missing an Unreleased section")
    body = match.group("body").strip()
    if body == "No unreleased changes yet.":
        return
    replacement = "## Unreleased\n\nNo unreleased changes yet.\n\n"
    path.write_text(text[: match.start()] + replacement + text[match.end() :], encoding="utf-8")


def _generated_changelog_body() -> str:
    previous = _last_version_tag()
    revision_range = f"{previous}..HEAD" if previous else "HEAD"
    result = subprocess.run(
        ["git", "log", revision_range, "--pretty=format:- %s"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return "### Changed\n\n- Prepared release metadata."
    return "### Changed\n\n" + "\n".join(lines)


def _last_version_tag() -> str | None:
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-version:refname"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for line in result.stdout.splitlines():
        tag = line.strip()
        if tag:
            return tag
    return None


def _unreleased_body(changelog: str) -> str:
    match = re.search(r"(?ms)^## Unreleased\n(?P<body>.*?)(?=^## )", changelog)
    return match.group("body").strip() if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
