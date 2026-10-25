"""Original evidence/recovery preservation across compact CLI representations."""

from __future__ import annotations

import json
from typing import Any, Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cairn.cli_output import compact_json, parse_tool_text, render_tool_text


def test_source_code_citations_scope_and_recovery_roundtrip() -> None:
    code = 'print("雪😀 quoted")\n' * 80 + "```\nTEXT 0 0\n"
    result = {
        "ok": True,
        "data": {
            "context_sections": [
                {
                    "anchor": "cairn://doc/intro/example",
                    "content_scope": "selected_blocks_of_section_body",
                    "omitted_content": True,
                    "evidence_blocks": [
                        {"text": code, "span": {"start": 10, "end": 10 + len(code)}},
                        {"text": code, "span": {"start": 9000, "end": 9000 + len(code)}},
                    ],
                }
            ],
            "embedding_mismatch": {"query_dim": 64, "index_dims": [768]},
            "skipped_documents": [{"doc": "old", "reason": "stale"}],
            "next_steps": [{"command": "docsgraph sync --force"}],
        },
    }
    text = render_tool_text(result)
    assert text.startswith("CAIRN-TEXT-1 ")
    assert parse_tool_text(text) == result
    assert code in text
    assert len(text.encode()) < len(compact_json(result).encode())
    assert parse_tool_text(text.replace("\n", "\r\n")) == result


def test_crlf_source_remains_json_escaped_in_a_text_frame() -> None:
    result = {"windows": "source\r\n" * 80, "code": 'print("quoted")\n' * 100}
    text = render_tool_text(result)
    assert text.startswith("CAIRN-TEXT-1 ")
    assert parse_tool_text(text) == result
    assert parse_tool_text(text.replace("\n", "\r\n")) == result


def test_marker_collision_and_control_characters_do_not_change_values() -> None:
    source = 'x = "quoted"\n' * 100
    value = {"$cairn_text": 0, "nested": {"$cairn_text_": False}, "text": source, "nul": "\x00\x1b"}
    text = render_tool_text(value)
    assert text.startswith("CAIRN-TEXT-1 $cairn_text__\n")
    assert parse_tool_text(text) == value


@pytest.mark.parametrize(
    "value", [{"ok": True}, {"content": "a" * 900}, {"ok": False, "error": "bad"}]
)
def test_falls_back_to_json_when_text_framing_is_not_smaller(value: dict[str, Any]) -> None:
    text = render_tool_text(value)
    assert text == compact_json(value)
    assert parse_tool_text(text) == value


def test_incomplete_or_invalid_text_records_fail_explicitly() -> None:
    text = render_tool_text({"code": 'print("hello")\n' * 100})
    assert text.startswith("CAIRN-TEXT-1 ")
    for broken in (text[:-2], text.replace("TEXT 0 ", "TEXT 1 ", 1)):
        with pytest.raises(ValueError):
            parse_tool_text(broken)


def test_repeated_section_metadata_has_explicit_columns_without_lost_values() -> None:
    rows = [
        {
            "canonical_citation": f"cairn://doc/section-{i}",
            "original_characters": 100 + i,
            "omitted_content": bool(i % 2),
            "scope": "section_body_only",
            "nullable_field": None,
        }
        for i in range(10)
    ]
    result = {"ok": True, "data": {"sections": rows}}
    text = render_tool_text(result)
    assert text.startswith("CAIRN-TEXT-1 ")
    assert '"columns"' in text and '"rows"' in text
    assert parse_tool_text(text) == result
    assert len(text.encode()) < len(compact_json(result).encode())


def test_differing_shapes_do_not_merge_missing_fields_with_null() -> None:
    result = {"sections": [{"id": "a", "optional": None}, {"id": "b"}]}
    assert parse_tool_text(render_tool_text(result)) == result


def test_bad_columnar_metadata_is_rejected() -> None:
    text = 'CAIRN-TEXT-1 $cairn_text\n{"x":{"$cairn_text":{"columns":["a","a"],"rows":[[1,2]]}}}\n'
    with pytest.raises(ValueError, match="columnar"):
        parse_tool_text(text)


_excluded: tuple[Literal["Cs"], ...] = ("Cs",)
_text = st.text(alphabet=st.characters(blacklist_categories=_excluded), max_size=150)
_json = st.recursive(
    st.none() | st.booleans() | st.integers() | _text,
    lambda child: st.lists(child, max_size=4) | st.dictionaries(_text, child, max_size=4),
    max_leaves=12,
)


@given(st.dictionaries(_text, _json, max_size=5))
@settings(max_examples=60)
def test_arbitrary_json_value_equivalence_and_byte_bound(value: dict[str, Any]) -> None:
    rendered = render_tool_text(value)
    assert parse_tool_text(rendered) == json.loads(compact_json(value))
    assert len(rendered.encode()) <= len(compact_json(value).encode())
