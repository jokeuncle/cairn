"""Cross-reference extraction — directed edges between sections.

Three kinds of edges (per ARCHITECTURE.md §2.4):

- ``link``: explicit Markdown anchor links (``[text](#anchor)``)
- ``textual``: numeric section references (``"§ 2.5"``, ``"Section 3"``)
- ``entity``: sections that share a high-signal defined entity

The :class:`XRefExtractor` Protocol is the seam. The default
:class:`HeuristicXRefExtractor` produces all three kinds without any model
dependency, and accepts an optional Entities reader for entity-mediated
edges. LLM-verified textual references are a v0.2.3+ refinement.
"""

from cairn.xref.base import ExtractionEdge, XRefExtractor
from cairn.xref.fake import FakeXRefExtractor
from cairn.xref.heuristic import HeuristicXRefExtractor

__all__ = [
    "ExtractionEdge",
    "FakeXRefExtractor",
    "HeuristicXRefExtractor",
    "XRefExtractor",
]
