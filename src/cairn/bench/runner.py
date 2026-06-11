"""Bench orchestrator — runs a suite end-to-end against Cairn and the baseline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from cairn.bench.baseline import NaiveHit, NaiveRAG
from cairn.bench.dataset import BenchDocument, BenchQuestion, BenchSuite
from cairn.bench.judge import LLMJudge
from cairn.bench.metrics import recall_at_k
from cairn.bench.report import BenchSummary, QuestionResult, SystemResult
from cairn.embed.base import Embedder
from cairn.engine.indexer import Indexer
from cairn.entity.heuristic import HeuristicExtractor
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.base import Summarizer
from cairn.tools.base import DocumentIndex, estimate_tokens
from cairn.tools.search_semantic import search_semantic
from cairn.xref.heuristic import HeuristicXRefExtractor


class BenchOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    k: int = 8
    naive_chunk_size_words: int = 512


class BenchRunner:
    """Runs a :class:`BenchSuite` against Cairn and a naive baseline."""

    def __init__(
        self,
        *,
        summarizer: Summarizer,
        embedder: Embedder,
        judge: LLMJudge | None = None,
        options: BenchOptions | None = None,
    ) -> None:
        self.summarizer = summarizer
        self.embedder = embedder
        self.judge = judge
        self.options = options or BenchOptions()

    async def run(self, suite: BenchSuite, *, work_dir: Path) -> BenchSummary:
        work_dir.mkdir(parents=True, exist_ok=True)
        results: list[QuestionResult] = []
        for document in suite.documents:
            results.extend(await self._run_document(document, work_dir / document.id))
        return BenchSummary(
            suite_name=suite.name,
            k=self.options.k,
            questions=tuple(results),
        )

    async def _run_document(
        self,
        document: BenchDocument,
        doc_dir: Path,
    ) -> list[QuestionResult]:
        doc_dir.mkdir(parents=True, exist_ok=True)
        source_text = document.source.read_text(encoding="utf-8")

        cairn_dir = doc_dir / "cairn"
        naive_dir = doc_dir / "naive"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        naive_dir.mkdir(parents=True, exist_ok=True)

        parser = MarkdownParser()
        parsed = parser.parse(document.source, doc_id=document.id)

        indexer = Indexer(
            parser=parser,
            summarizer=self.summarizer,
            embedder=self.embedder,
            entity_extractor=HeuristicExtractor(),
            xref_extractor=HeuristicXRefExtractor(),
        )
        await indexer.index_document(parsed, out_dir=cairn_dir)
        cairn_index = DocumentIndex.load(cairn_dir)

        naive = NaiveRAG(
            self.embedder,
            chunk_size_words=self.options.naive_chunk_size_words,
        )
        await naive.index(parsed, source_text, out_dir=naive_dir)

        results: list[QuestionResult] = []
        for question in document.questions:
            cairn_result, cairn_context = await self._run_cairn(
                cairn_index, question
            )
            naive_result, naive_context = await self._run_naive(
                naive, question, naive_dir
            )

            if self.judge is not None and question.reference is not None:
                cairn_result = await self._judge_result(
                    cairn_result, question, cairn_context
                )
                naive_result = await self._judge_result(
                    naive_result, question, naive_context
                )

            results.append(
                QuestionResult(
                    document_id=document.id,
                    question_id=question.id,
                    question=question.question,
                    expected_anchors=question.expected_anchors,
                    tags=question.tags,
                    cairn=cairn_result,
                    naive=naive_result,
                )
            )
        return results

    async def _judge_result(
        self,
        result: SystemResult,
        question: BenchQuestion,
        context: str,
    ) -> SystemResult:
        if self.judge is None or question.reference is None:
            return result
        answer = await self.judge.answer(question.question, context)
        is_correct, _ = await self.judge.judge(
            question.question, question.reference, answer
        )
        return result.model_copy(
            update={"qa_correct": is_correct, "qa_answer": answer}
        )

    async def _run_cairn(
        self,
        index: DocumentIndex,
        question: BenchQuestion,
    ) -> tuple[SystemResult, str]:
        response = await search_semantic(
            index,
            embedder=self.embedder,
            query=question.question,
            k=self.options.k,
        )
        section_ids = [hit["id"] for hit in response.data["hits"]]
        recall = recall_at_k(
            section_ids, question.expected_anchors, k=self.options.k
        )
        context = _format_cairn_context(response.data["hits"])
        result = SystemResult(
            system="cairn",
            section_ids=tuple(section_ids),
            recall_at_k=recall,
            tokens_returned=response.tokens_returned,
        )
        return result, context

    async def _run_naive(
        self,
        naive: NaiveRAG,
        question: BenchQuestion,
        naive_dir: Path,
    ) -> tuple[SystemResult, str]:
        hits = await naive.retrieve(
            question.question, out_dir=naive_dir, k=self.options.k
        )
        section_ids = [hit.section_id or "" for hit in hits]
        recall = recall_at_k(
            section_ids, question.expected_anchors, k=self.options.k
        )
        tokens = sum(estimate_tokens(hit.text) for hit in hits)
        context = _format_naive_context(hits)
        result = SystemResult(
            system="naive",
            section_ids=tuple(section_ids),
            recall_at_k=recall,
            tokens_returned=tokens,
        )
        return result, context


def _format_cairn_context(hits: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for hit in hits:
        title = str(hit.get("title", ""))
        synopsis = str(hit.get("synopsis", ""))
        head = str(hit.get("head", ""))
        body = synopsis or head
        parts.append(f"## {title}\n\n{body}".strip())
    return "\n\n---\n\n".join(parts)


def _format_naive_context(hits: list[NaiveHit]) -> str:
    return "\n\n---\n\n".join(hit.text for hit in hits)
