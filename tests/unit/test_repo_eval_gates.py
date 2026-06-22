"""Tests for repository eval/smoke strict gate helpers."""

from __future__ import annotations

from scripts.eval_repos import eval_gate_failures
from scripts.smoke_many_repos import smoke_gate_failures


def test_smoke_gate_strict_requires_all_queries_and_drilldowns() -> None:
    report = {
        "repos": 2,
        "ok": 2,
        "failed": 0,
        "sync_failures": 0,
        "query_count": 4,
        "queries_with_hits": 3,
        "drilldowns_ok": 4,
    }

    failures = smoke_gate_failures(report, strict=True)

    assert failures == ["queries with hits 3 < required 4"]


def test_smoke_gate_passes_with_explicit_thresholds() -> None:
    report = {
        "repos": 2,
        "ok": 1,
        "failed": 1,
        "sync_failures": 2,
        "query_count": 4,
        "queries_with_hits": 3,
        "drilldowns_ok": 2,
    }

    failures = smoke_gate_failures(
        report,
        strict=False,
        min_ok_repos=1,
        max_sync_failures=2,
        min_queries_with_hits=3,
        min_drilldowns_ok=2,
    )

    assert failures == []


def test_eval_gate_strict_uses_aggregate_rates() -> None:
    report = [
        {
            "sync": {"failed": 0},
            "status": {"stale": 0, "missing": 0, "errors": 0},
            "metrics": {
                "total": 10,
                "top1": 8,
                "top3": 10,
                "top5": 10,
                "drilldown": 10,
            },
        }
    ]

    failures = eval_gate_failures(report, strict=True)

    assert failures == ["top1 rate 0.800 < required 0.900 (8/10)"]


def test_eval_gate_can_relax_top1_threshold() -> None:
    report = [
        {
            "sync": {"failed": 0},
            "status": {"stale": 0, "missing": 0, "errors": 0},
            "metrics": {
                "total": 10,
                "top1": 8,
                "top3": 10,
                "top5": 10,
                "drilldown": 10,
            },
        }
    ]

    failures = eval_gate_failures(report, strict=True, min_top1_rate=0.8)

    assert failures == []
