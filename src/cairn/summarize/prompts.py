"""Prompt templates and word budgets for summarization.

The prompts are deliberately terse. We trust word budgets more than
elaborately worded instructions; the budget is enforced at the call site
regardless of model compliance.
"""

from __future__ import annotations

import re
from typing import Final

from cairn.summarize.base import SummaryLevel

WORD_BUDGETS: Final[dict[SummaryLevel, int]] = {
    SummaryLevel.GIST: 20,
    SummaryLevel.SYNOPSIS: 80,
    SummaryLevel.DIGEST: 300,
}

SYSTEM_PROMPT: Final = (
    "You write structural document summaries for a hierarchical retrieval "
    "system.\n"
    "- Be precise and factual. Do not interpret, extrapolate, or add opinions.\n"
    "- Do not begin with 'This section…', 'The author…', or similar preamble.\n"
    "- Output ONLY the summary text. No headers, labels, or quotation marks.\n"
    "- Stay strictly within the word budget.\n"
)


def user_prompt(title: str, body: str, level: SummaryLevel) -> str:
    """Build the user-role prompt for one summary request."""
    budget = WORD_BUDGETS[level]
    if level is SummaryLevel.GIST:
        instruction = (
            f"Summarize the section below in a single sentence of at most "
            f"{budget} words. Capture the single most important fact or claim."
        )
    elif level is SummaryLevel.SYNOPSIS:
        instruction = (
            f"Summarize the section below in one paragraph of at most "
            f"{budget} words. Cover the main idea, key specifics, and what "
            "the reader will learn."
        )
    else:  # DIGEST
        instruction = (
            f"Summarize the section below in 2 to 3 short paragraphs, totaling "
            f"at most {budget} words. Preserve structural ordering and any "
            "concrete facts (names, numbers, code identifiers)."
        )

    body_excerpt = body.strip() or "(empty section body)"
    return (
        f"{instruction}\n\n"
        f"SECTION TITLE: {title}\n\n"
        f"SECTION BODY:\n{body_excerpt}"
    )


_WORD = re.compile(r"\S+")


def enforce_word_budget(text: str, level: SummaryLevel) -> str:
    """Soft-truncate ``text`` to the level's word budget at a word boundary.

    Appends a horizontal ellipsis (``…``) when truncation occurred. Returns
    the original text untouched when already within budget.
    """
    budget = WORD_BUDGETS[level]
    words = _WORD.findall(text)
    if len(words) <= budget:
        return text
    return " ".join(words[:budget]) + "…"
