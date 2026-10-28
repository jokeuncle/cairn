"""Original-evidence compression must obey provenance and syntax boundaries."""

from hypothesis import given, settings
from hypothesis import strategies as st

from cairn.tools.context_blocks import EvidenceSource, pack_evidence


def source(body: str, name: str = "guide") -> EvidenceSource:
    return EvidenceSource(
        doc=name,
        source=f"{name}.md",
        id="options",
        title="Options",
        path=["Guide", "Options"],
        anchor=f"cairn://{name}/options",
        body=body,
    )


def test_code_example_keeps_neighboring_conditions_and_exact_spans() -> None:
    body = (
        "General background.\n\n"
        + "Unrelated notes.\n\n" * 30
        + "Use this timeout only for local connections.\n\n"
        + "```python\nclient = Client(timeout=17)\n```\n\n"
        + "Unless streaming, release the handle after completion.\n\n"
        + "Unrelated notes.\n\n" * 30
    )
    result = pack_evidence(
        [source(body)], query="Client timeout", max_chars=1000, max_section_chars=400
    )
    text = "".join(b["text"] for b in result[0]["evidence_blocks"])
    assert "```python\nclient = Client(timeout=17)\n```" in text
    assert "only for local" in text and "Unless streaming" in text
    assert result[0]["omitted_content"]
    for block in result[0]["evidence_blocks"]:
        span = block["span"]
        assert block["text"] == body[span["start"] : span["end"]]


def test_oversized_arbitrary_code_is_not_split_to_fake_a_complete_example() -> None:
    body = "```python\n" + "timeout = 17\n" * 100 + "```\n"
    assert (
        pack_evidence([source(body)], query="timeout", max_chars=1000, max_section_chars=200) == []
    )


def test_cli_options_keep_usage_group_and_wrapped_descriptions() -> None:
    body = (
        "```text\nService checker.\n\nUsage: service check [OPTIONS]\n\nOptions:\n"
        "  --unrelated\n      General information.\n"
        "  --pool-timeout INTEGER\n      Pool timeout in seconds.\n"
        "      Only applies when pooling is enabled.\n"
        "  --unrelated-two\n      General information.\n```\n"
    )
    packed = pack_evidence(
        [source(body)], query="pool timeout", max_chars=1000, max_section_chars=220
    )
    blocks = packed[0]["evidence_blocks"]
    text = "".join(b["text"] for b in blocks)
    assert "Usage: service check" in text and "Options:" in text
    assert "--pool-timeout" in text and "Only applies when pooling" in text
    assert "--unrelated-two" not in text
    assert any(b["kind"] == "cli_option" for b in blocks)


def test_budget_selects_complementary_sources_once_and_is_deterministic() -> None:
    sources = [source("Timeout is seventeen.\n", "a"), source("Authentication uses amber.\n", "b")]
    packed = pack_evidence(
        sources, query="timeout authentication", max_chars=80, max_section_chars=200
    )
    assert [s["doc"] for s in packed] == ["a", "b"]
    assert (
        pack_evidence(sources, query="timeout authentication", max_chars=80, max_section_chars=200)
        == packed
    )
    assert all(not s["omitted_content"] for s in packed)


def test_no_lexical_overlap_uses_source_order_not_shortest_fragment() -> None:
    body = "First context sentence.\n\n" + "Background material.\n\n" * 30 + "X.\n"
    packed = pack_evidence([source(body)], query="sapphire", max_chars=1000, max_section_chars=200)
    assert packed[0]["evidence_blocks"][0]["span"]["start"] == 0


def test_joint_selection_uses_later_complementary_candidate_with_section_caps() -> None:
    sources = [
        source("Timeout is seventeen.\n", "a"),
        source("Timeout is seventeen with identical notes.\n", "a"),
        source("Authentication uses amber.\n", "b"),
    ]
    packed = pack_evidence(
        sources,
        query="timeout authentication",
        max_chars=1000,
        max_section_chars=200,
        max_sections=2,
        sections_per_doc=1,
    )
    assert [s["doc"] for s in packed] == ["a", "b"]
    assert len(packed) <= 2


def test_focused_queries_cover_distinct_needs_without_leaking_internal_ranks() -> None:
    sources = [
        source("Timeout is seventeen.\n", "a").model_copy(update={"query_ranks": [0, None]}),
        source("Timeout details.\n", "distractor").model_copy(update={"query_ranks": [1, None]}),
        source("Authentication uses amber.\n", "b").model_copy(update={"query_ranks": [None, 0]}),
    ]
    packed = pack_evidence(
        sources,
        query="service options",
        queries=["timeout", "authentication"],
        max_chars=1000,
        max_section_chars=200,
        max_sections=2,
    )
    assert {s["doc"] for s in packed} == {"a", "b"}
    assert all("query_ranks" not in s for s in packed)


def test_hidden_comments_and_empty_layout_tags_are_not_evidence() -> None:
    body = (
        "<!-- quartz_dispatch_only_in_comment -->\n\n<details>\n\n"
        + "Actual visible source context.\n\n" * 30
        + "</details>\n"
    )
    packed = pack_evidence(
        [source(body)],
        query="quartz_dispatch_only_in_comment",
        max_chars=1000,
        max_section_chars=200,
    )
    text = "".join(b["text"] for b in packed[0]["evidence_blocks"])
    assert "Actual visible" in text
    assert "<!--" not in text and "<details>" not in text


@settings(max_examples=50)
@given(st.lists(st.text(alphabet="ab🙂条件 ", min_size=1, max_size=70), min_size=1, max_size=12))
def test_unicode_source_roundtrip_and_global_and_local_budgets(paragraphs: list[str]) -> None:
    body = "\n\n".join(paragraphs)
    sources = [source(body, "a"), source(body, "b")]
    packed = pack_evidence(sources, query="ab 条件", max_chars=350, max_section_chars=220)
    total = 0
    for section in packed:
        spans = [b["span"] for b in section["evidence_blocks"]]
        assert len({(s["start"], s["end"]) for s in spans}) == len(spans)
        count = 0
        for block in section["evidence_blocks"]:
            start, end = block["span"]["start"], block["span"]["end"]
            assert block["text"] == body[start:end]
            count += end - start
        assert count == section["returned_source_characters"] <= 220
        total += count
    assert total <= 350
