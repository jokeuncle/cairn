"""Optional, lossless text representation of JSON tool payloads.

Long strings appear verbatim in length-delimited records. Metadata references
them with a collision-free marker; all source and warning values are retained.
Compact JSON is used when framing would increase the UTF-8 byte count.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

_HEADER = "CAIRN-TEXT-1 "


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def render_tool_text(payload: dict[str, Any]) -> str:
    """Render complete JSON values without escaping long source/code strings."""
    plain = compact_json(payload)
    # Work in the same value domain as JSON, including tuple-to-list conversion.
    value = json.loads(plain)
    keys: set[str] = set()
    frequency: Counter[str] = Counter()

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            keys.update(item)
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)
        elif isinstance(item, str):
            frequency[item] += 1

    collect(value)
    marker = "$cairn_text"
    while marker in keys:
        marker += "_"
    texts: list[str] = []
    identifiers: dict[str, int] = {}
    tables = 0

    def replace(item: Any) -> Any:
        nonlocal tables
        if (
            isinstance(item, str)
            and ("\n" in item or (len(item) >= 80 and frequency[item] > 1))
            and "\r" not in item
            and all(ord(c) >= 32 or c in "\t\n" for c in item)
        ):
            if item not in identifiers:
                identifiers[item] = len(texts)
                texts.append(item)
            return {marker: identifiers[item]}
        if isinstance(item, dict):
            return {key: replace(child) for key, child in item.items()}
        if isinstance(item, list):
            values = [replace(child) for child in item]
            # Repeated section/hit keys need be stated only once. Preserve
            # exactly matching key order; missing keys never become nulls.
            if (
                len(values) >= 2
                and all(isinstance(child, dict) for child in values)
                and len(values[0]) >= 2
                and all(tuple(child) == tuple(values[0]) for child in values)
            ):
                columns = list(values[0])
                table = {
                    marker: {
                        "columns": columns,
                        "rows": [[child[key] for key in columns] for child in values],
                    }
                }
                if len(compact_json(table).encode("utf-8")) < len(
                    json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ):
                    tables += 1
                    return table
            return values
        return item

    metadata = replace(value)
    if not texts and not tables:
        return plain
    chunks = [_HEADER + marker + "\n", compact_json(metadata), "\n"]
    for identifier, text in enumerate(texts):
        chunks.extend([f"TEXT {identifier} {len(text)}\n", text, "\n"])
    rendered = "".join(chunks)
    return rendered if len(rendered.encode("utf-8")) < len(plain.encode("utf-8")) else plain


def parse_tool_text(text: str) -> dict[str, Any]:
    """Recover the JSON result; reject truncated/ambiguous text records."""
    if not text.startswith(_HEADER):
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("tool result must be a JSON object")
        return value
    # Framing may pass through a Windows text stream. CR-containing payload
    # strings stay JSON-escaped, so normalization cannot change their values.
    text = text.replace("\r\n", "\n")
    header, separator, remaining = text.partition("\n")
    marker = header[len(_HEADER) :]
    if not separator or re.fullmatch(r"\$cairn_text_*", marker) is None:
        raise ValueError("invalid text header")
    line, separator, remaining = remaining.partition("\n")
    if not separator:
        raise ValueError("missing metadata")
    metadata = json.loads(line)
    texts: list[str] = []
    while remaining:
        line, separator, remaining = remaining.partition("\n")
        match = re.fullmatch(r"TEXT (\d+) (\d+)", line)
        if not separator or match is None or int(match[1]) != len(texts):
            raise ValueError("invalid text record")
        length = int(match[2])
        if len(remaining) < length + 1 or remaining[length] != "\n":
            raise ValueError("truncated text record")
        texts.append(remaining[:length])
        remaining = remaining[length + 1 :]
    used: set[int] = set()

    def restore(item: Any) -> Any:
        if isinstance(item, dict):
            if set(item) == {marker}:
                identifier = item[marker]
                if isinstance(identifier, dict):
                    columns = identifier.get("columns")
                    rows = identifier.get("rows")
                    if (
                        set(identifier) != {"columns", "rows"}
                        or not isinstance(columns, list)
                        or not columns
                        or any(not isinstance(key, str) for key in columns)
                        or len(set(columns)) != len(columns)
                        or not isinstance(rows, list)
                        or any(
                            not isinstance(row, list) or len(row) != len(columns) for row in rows
                        )
                    ):
                        raise ValueError("invalid columnar metadata")
                    return [
                        {key: restore(child) for key, child in zip(columns, row, strict=True)}
                        for row in rows
                    ]
                if type(identifier) is not int or not 0 <= identifier < len(texts):
                    raise ValueError("invalid text reference")
                used.add(identifier)
                return texts[identifier]
            return {key: restore(child) for key, child in item.items()}
        if isinstance(item, list):
            return [restore(child) for child in item]
        return item

    value = restore(metadata)
    if not isinstance(value, dict) or used != set(range(len(texts))):
        raise ValueError("invalid text metadata or unused records")
    return value
