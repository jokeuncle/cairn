"""Optional MarkItDown-backed parser for office/data/web document formats.

MarkItDown converts many source formats into Markdown intended for LLM and
text-analysis pipelines. Cairn uses it as a local-file conversion layer, then
delegates structure extraction to :class:`MarkdownParser`.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from slugify import slugify

from cairn.core.errors import ParseError
from cairn.core.types import Document
from cairn.ingest.markdown import MarkdownParser


class MarkItDownParser:
    """Convert non-native local files to Markdown and parse the result."""

    name = "markitdown"
    extensions: tuple[str, ...] = (
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".csv",
        ".json",
        ".xml",
        ".epub",
        ".msg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".wav",
        ".mp3",
        ".zip",
    )

    def __init__(self) -> None:
        self._markdown = MarkdownParser()

    def parse(
        self,
        source: Path | bytes | str,
        *,
        doc_id: str | None = None,
    ) -> Document:
        if not isinstance(source, Path):
            msg = "MarkItDownParser only accepts local file paths"
            raise ParseError(msg)

        source_path = source.resolve()
        resolved_doc_id = doc_id or _slug_or_raise(source_path.stem, ctx="filename stem")
        markdown = self._convert_local(source_path)
        if not markdown.strip():
            msg = f"MarkItDown produced empty Markdown for: {source_path}"
            raise ParseError(msg, details={"path": str(source_path)})
        markdown = _ensure_heading(markdown, source_path.stem)

        parsed = self._markdown.parse(markdown, doc_id=resolved_doc_id)
        try:
            source_bytes = source_path.read_bytes()
        except OSError as exc:
            msg = f"could not read converted source file: {source_path}"
            raise ParseError(msg, details={"path": str(source_path)}) from exc
        converter_version = _markitdown_version()
        source_hash = hashlib.sha256(
            b"\x00".join(
                [
                    source_bytes,
                    converter_version.encode("utf-8"),
                    markdown.encode("utf-8"),
                ]
            )
        ).hexdigest()
        return parsed.model_copy(
            update={
                "source_path": source_path,
                "source_hash": source_hash,
            }
        )

    @staticmethod
    def _convert_local(path: Path) -> str:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            msg = (
                "MarkItDown support is not installed. Install with "
                "`pip install 'cairn[markitdown]'` or "
                "`uv pip install -e '.[markitdown]'`."
            )
            raise ParseError(msg, details={"path": str(path)}) from exc

        try:
            converter: Any = MarkItDown(enable_plugins=False)
            if hasattr(converter, "convert_local"):
                result = converter.convert_local(str(path))
            else:
                result = converter.convert(str(path))
        except Exception as exc:
            msg = f"MarkItDown could not convert local file: {path}"
            raise ParseError(msg, details={"path": str(path)}) from exc

        text = getattr(result, "text_content", None)
        if text is None:
            text = getattr(result, "markdown", None)
        if not isinstance(text, str):
            msg = "MarkItDown returned no Markdown text content"
            raise ParseError(msg, details={"path": str(path)})
        return text


def _slug_or_raise(text: str, *, ctx: str) -> str:
    slug = slugify(text)
    if not slug:
        msg = f"could not derive a slug from {ctx}: {text!r}"
        raise ParseError(msg)
    return slug


def _markitdown_version() -> str:
    try:
        return version("markitdown")
    except PackageNotFoundError:
        return "not-installed"


def _ensure_heading(markdown: str, fallback_title: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return markdown
        if stripped:
            break
    title = fallback_title.replace("_", " ").replace("-", " ").strip() or "Document"
    return f"# {title}\n\n{markdown}"
