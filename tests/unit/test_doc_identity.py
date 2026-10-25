"""Metamorphic checks for bounded source-namespace relevance."""

from __future__ import annotations

from cairn.repo_search import _build_repo_lexical_query, _doc_identity_bonus


def test_action_prefix_does_not_dilute_a_literal_source_namespace() -> None:
    fields = ("docs rpc adapter", "docs/rpc/adapter.md", "API", "", "")
    exact = _build_repo_lexical_query("rpc adapter")
    procedural = _build_repo_lexical_query("how to expose rpc adapter")
    assert _doc_identity_bonus(procedural, fields) == _doc_identity_bonus(exact, fields)


def test_namespace_matching_normalizes_path_separators_and_opaque_document_ids() -> None:
    query = _build_repo_lexical_query("how to expose rpc adapter")
    hierarchical = ("opaque", "docs/rpc/adapter.md", "API", "", "")
    slugged = ("docs rpc adapter", "manual.md", "API", "", "")
    assert _doc_identity_bonus(query, hierarchical) == _doc_identity_bonus(query, slugged)


def test_partial_tokens_and_body_only_mentions_are_not_an_exact_namespace() -> None:
    query = _build_repo_lexical_query("how to expose rpc adapter")
    canonical = ("docs rpc adapter", "docs/rpc/adapter.md", "API", "", "")
    partial = ("docs rpc adapterness", "docs/rpc/adapterness.md", "API", "", "")
    incidental = ("unrelated", "unrelated.md", "RPC adapter", "", "expose rpc adapter")
    assert _doc_identity_bonus(query, canonical) > _doc_identity_bonus(query, partial)
    assert _doc_identity_bonus(query, canonical) > _doc_identity_bonus(query, incidental)
