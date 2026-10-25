"""Evidence packs must cover query parts rather than repeat a topic overview."""

from typing import Any

from cairn.repo_search import select_context_hits


def hit(doc: str, section: str, terms: list[str], sparse: float, score: float) -> dict[str, Any]:
    return {
        "doc": doc,
        "id": section,
        "score": score,
        "sparse_score": sparse,
        "explanation": {"matched_terms": terms},
    }


def test_evidence_selection_covers_distinct_requirements_over_topic_repeats() -> None:
    candidates = [
        hit("overview", "intro", ["client"], 0.03, 0.95),
        hit("overview", "platforms", ["client"], 0.02, 0.9),
        hit("config", "timeout", ["client", "timeout"], 0.2, 0.3),
        hit("config", "hook", ["client", "hook"], 0.15, 0.25),
        hit("transport", "retry", ["client", "retry"], 0.12, 0.2),
    ]
    selected = select_context_hits(candidates, k=3, sections_per_doc=3)
    assert [item["id"] for item in selected] == ["timeout", "hook", "retry"]


def test_semantic_only_candidates_keep_hybrid_rank_and_document_cap() -> None:
    candidates = [
        hit("a", "first", [], 0, 0.9),
        hit("a", "second", [], 0, 0.8),
        hit("b", "third", [], 0, 0.5),
    ]
    selected = select_context_hits(candidates, k=3, sections_per_doc=1)
    assert [item["id"] for item in selected] == ["first", "third"]


def test_empty_candidates_and_equal_scores_are_stable() -> None:
    assert select_context_hits([], k=5, sections_per_doc=3) == []
    candidates = [hit("a", "first", ["shared"], 0.2, 0.5), hit("b", "second", ["shared"], 0.2, 0.5)]
    assert select_context_hits(candidates, k=2, sections_per_doc=3) == candidates
