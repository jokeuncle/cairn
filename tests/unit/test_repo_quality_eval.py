"""Guard the evaluation oracle against losing headings or echoing query answers."""

from scripts.eval_repo_quality import evidence_text, marker_checks


def test_qa_keeps_configuration_name_from_source_heading() -> None:
    payload = {
        "data": {
            "query": "How do warnings become errors?",
            "context_sections": [
                {
                    "source": "configuration.md",
                    "title": "strict",
                    "content": "Set to true to stop on warnings. Default: false.",
                    "evidence": {"text": "Determines how warnings are handled."},
                }
            ],
        }
    }
    evidence = evidence_text(payload)
    assert "# strict" in evidence
    assert "Source: configuration.md" in evidence
    assert all(marker_checks(evidence, {"facts": [["strict"], ["false"]]}))


def test_query_echo_cannot_satisfy_an_evidence_marker() -> None:
    payload = {
        "data": {
            "query": "Is hypothetical_flag enabled?",
            "context_sections": [
                {
                    "source": "guide.md",
                    "title": "Guide",
                    "content": "General introduction.",
                }
            ],
        }
    }
    assert marker_checks(evidence_text(payload), {"facts": [["hypothetical_flag"]]}) == [False]
