"""Materialize explicit local documentation snippets without executing code.

Supports the ``{* docs_src/example.py hl[1:3] *}`` directives used by Typer.
Output must be a new directory outside the source repository. A manifest maps
each inserted source span to its original file and SHA-256. This is an explicit
preprocessing command, not a change to Cairn's default Markdown parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

_DIRECTIVE = re.compile(r"\{\*\s*(.*?)\s*\*\}", re.DOTALL)
_SPEC = re.compile(r"(docs_src/[^\s]+\.py)(?:\s+hl\[[\d,:\s]+\])?")
_MAX_FILE_BYTES = 4 * 1024 * 1024
_MAX_TOTAL_BYTES = 32 * 1024 * 1024


def _read(root: Path, relative: str) -> tuple[str, str]:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"source path must be repository-relative: {relative!r}")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"source path leaves the repository: {relative!r}")
    if resolved.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError(f"source file exceeds {_MAX_FILE_BYTES} bytes: {relative!r}")
    raw = resolved.read_bytes()
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


def materialize(root: Path, documents: list[str], output: Path) -> dict[str, Any]:
    """Prepare a separate, provenance-mapped source tree; never overwrite input."""
    root = root.resolve(strict=True)
    output = output.resolve()
    if not root.is_dir():
        raise ValueError("root must be a repository directory")
    if output.is_relative_to(root):
        raise ValueError("output must be outside the source repository")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    if not documents:
        raise ValueError("provide at least one Markdown document")

    rendered: dict[str, str] = {}
    records: dict[str, Any] = {}
    total_bytes = 0
    for relative in dict.fromkeys(documents):
        if Path(relative).suffix.lower() not in {".md", ".markdown", ".mdown"}:
            raise ValueError(f"not a Markdown document: {relative!r}")
        text, source_hash = _read(root, relative)
        parts: list[str] = []
        spans: list[dict[str, Any]] = []
        cursor = 0
        characters = 0
        document_bytes = 0
        for match in _DIRECTIVE.finditer(text):
            spec = _SPEC.fullmatch(match.group(1).strip())
            if spec is None:
                raise ValueError(f"unsupported snippet directive in {relative}: {match.group(0)!r}")
            source = spec.group(1)
            code, code_hash = _read(root, source)
            preceding = text[cursor : match.start()]
            # Code may itself contain Markdown fences. Preserve it verbatim.
            longest = max((len(run) for run in re.findall(r"`+", code)), default=0)
            fence = "`" * max(3, longest + 1)
            opening = f"\n{fence}python\n"
            closing = ("" if code.endswith("\n") else "\n") + fence + "\n"
            document_bytes += sum(
                len(part.encode("utf-8")) for part in (preceding, opening, code, closing)
            )
            if total_bytes + document_bytes > _MAX_TOTAL_BYTES:
                raise ValueError(f"prepared documents exceed {_MAX_TOTAL_BYTES} bytes")
            parts.append(preceding)
            characters += len(preceding)
            parts.extend([opening, code])
            start = characters + len(opening)
            spans.append(
                {
                    "source": source,
                    "source_sha256": code_hash,
                    "directive_span": {"start": match.start(), "end": match.end()},
                    "output_span": {"start": start, "end": start + len(code)},
                    "unit": "unicode_characters",
                    "highlight": "annotation ignored; complete original code retained",
                }
            )
            parts.append(closing)
            characters = start + len(code) + len(closing)
            cursor = match.end()
        suffix = text[cursor:]
        if total_bytes + document_bytes + len(suffix.encode("utf-8")) > _MAX_TOTAL_BYTES:
            raise ValueError(f"prepared documents exceed {_MAX_TOTAL_BYTES} bytes")
        parts.append(suffix)
        result = "".join(parts)
        raw = result.encode("utf-8")
        total_bytes += len(raw)
        if total_bytes > _MAX_TOTAL_BYTES:
            raise ValueError(f"prepared documents exceed {_MAX_TOTAL_BYTES} bytes")
        rendered[relative] = result
        records[relative] = {
            "source_sha256": source_hash,
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "snippets": spans,
        }

    manifest = {"format_version": 1, "documents": records, "output_bytes": total_bytes}
    # Validate and render every input before creating the destination.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".doc-snippets-", dir=output.parent) as temporary:
        stage = Path(temporary) / "prepared"
        stage.mkdir()
        for relative, result in rendered.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(result.encode("utf-8"))
        (stage / "snippet-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("documents", nargs="+")
    args = parser.parse_args()
    manifest = materialize(args.root, args.documents, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "documents": len(manifest["documents"]),
                "snippets": sum(len(d["snippets"]) for d in manifest["documents"].values()),
                "manifest": str(args.output / "snippet-manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
