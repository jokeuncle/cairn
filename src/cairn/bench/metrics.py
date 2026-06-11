"""Recall@k computation for bench questions.

An ``expected_anchor`` is considered matched if it appears as a substring
of any retrieved section id within the top ``k`` results. This is a
deliberate convenience: authoring full hierarchical slugs in YAML/TOML is
brittle, so we accept short suffixes that uniquely identify a section.
"""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(
    retrieved_section_ids: Sequence[str],
    expected_anchors: Sequence[str],
    *,
    k: int,
) -> float:
    """Return the fraction of expected anchors found in the top-k retrieval.

    Returns ``1.0`` when ``expected_anchors`` is empty (vacuously true).
    """
    if not expected_anchors:
        return 1.0

    top_k = retrieved_section_ids[:k]
    matched = 0
    for expected in expected_anchors:
        if any(expected in retrieved for retrieved in top_k):
            matched += 1
    return matched / len(expected_anchors)
