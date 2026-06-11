# Hero Demo — Cairn Indexes Its Own Architecture

This recipe is **self-referential**: we use Cairn to navigate Cairn's own
`ARCHITECTURE.md`. Everything below is reproducible from a fresh clone.

All commands use the `--fake` flag, which means **no LLM, no embedding model,
no API keys**. Real summaries and semantic search require a local Ollama or
any OpenAI-compatible endpoint (see the bottom of this file).

---

## Setup

```bash
git clone https://github.com/cairn-dev/cairn.git
cd cairn
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

---

## Step 1 — Index the document

```bash
.venv/bin/cairn index ARCHITECTURE.md --out /tmp/cairn-arch --fake
```

Expected output (≤ 1 second on an M-series MacBook):

```
indexed: /tmp/cairn-arch/manifest.json
```

What just happened:

- **TreeBuilder** parsed `ARCHITECTURE.md` into 32 `SectionNode`s
  (1 H1 + 11 H2 + 11 H3 + 9 H4) and wrote `tree.json`.
- **SummaryBuilder** ran `FakeSummarizer` to produce a `gist` and `synopsis`
  for every section into `summaries.json`.
- **VectorBuilder** ran `FakeEmbedder` (64-d BoW hash) on every section
  and wrote `vectors.lance/` + `vectors_manifest.json`.
- **manifest.json** records the source hash, builder versions, and the
  model identifiers that produced each artifact.

```
$ du -sh /tmp/cairn-arch
124K    /tmp/cairn-arch    # source ARCHITECTURE.md is ~36K
```

---

## Step 2 — The map (`outline`)

Get the document outline. This is the cheapest tool — agents should call it
first when they meet an unfamiliar document.

```bash
.venv/bin/cairn outline /tmp/cairn-arch --depth 2
```

Output (excerpt):

```json
{
  "doc": "architecture",
  "depth": 2,
  "tree": [{
    "id": "cairn-technical-architecture",
    "title": "Cairn — Technical Architecture",
    "level": 1,
    "children": [
      { "id": ".../1-system-overview",        "gist": "...overview diagram..." },
      { "id": ".../2-layered-architecture",   "gist": "...", "truncated": true },
      { "id": ".../3-plug-in-architecture",   "gist": "Five plug-in points..." },
      { "id": ".../4-data-model",             "gist": "Canonical Python types..." },
      { "id": ".../5-storage-layout",         "gist": "Everything Cairn persists..." },
      { "id": ".../6-mcp-tool-reference-summary", "gist": "..." }
    ]
  }]
}
```

Drill into Layer 2:

```bash
.venv/bin/cairn outline /tmp/cairn-arch \
  --depth 3 \
  --focus cairn-technical-architecture/2-layered-architecture
```

This narrows the outline to the Layered Architecture subtree, exposing
the five sub-indexes (T, S, E, X, V):

```
2. Layered Architecture
├── Invariants across all layers
├── Layer 1: Ingestion
├── Layer 2: Index
│   ├── 2.1 Tree (T) — Structural backbone
│   ├── 2.2 Summaries (S) — Multi-granularity views
│   ├── 2.3 Entities (E) — Term and concept index
│   ├── 2.4 Cross-references (X) — Document graph
│   ├── 2.5 Vectors (V) — Semantic overlay
│   └── 2.6 Builder pipeline
└── Layer 3: Retrieval Tools
    └── ...
```

---

## Step 3 — Keyword search

Find every mention of `LanceDB`:

```bash
.venv/bin/cairn query keyword /tmp/cairn-arch LanceDB
```

```
score=7  2.5 Vectors (V) — Semantic overlay
score=7  3. Plug-in Architecture
score=7  5. Storage Layout
score=7  7. Tech Stack and Rationale
score=7  9. Extensibility Boundaries
```

Five hits — every section in `ARCHITECTURE.md` that mentions LanceDB,
with stable anchors back into the source.

Multi-term search, `mode=all` (every term must appear):

```bash
.venv/bin/cairn query keyword /tmp/cairn-arch progressive disclosure --mode all
```

```
score=21  3.3 Progressive-disclosure contract
score=21  9. Extensibility Boundaries
```

The exact target section is the top hit. Score is `count * len(term)`
summed across terms, sorted descending — see `docs/specs/mcp-tools.md` §5.

---

## Step 4 — Semantic search

```bash
.venv/bin/cairn query semantic /tmp/cairn-arch "how do plug-ins work" --k 3 --fake
```

With `--fake`, the `FakeEmbedder` is a deterministic bag-of-words hash —
it respects shared vocabulary but has no semantic understanding. Run the
same command without `--fake` against a real embedder (Ollama
`nomic-embed-text`, OpenAI `text-embedding-3-small`, etc.) and watch the
top hit become **§3 Plug-in Architecture** directly. That switch is the
whole point of the pluggable Embedder.

---

## Step 5 — Fetch a specific section

```python
import asyncio
from pathlib import Path
from cairn.tools.base import DocumentIndex
from cairn.tools.get_section import get_section

async def main():
    idx = DocumentIndex.load(Path("/tmp/cairn-arch"))
    r = await get_section(
        idx,
        id="cairn-technical-architecture/2-layered-architecture/layer-2-index/2-5-vectors-v-semantic-overlay",
        level="synopsis",
    )
    print(r.data["title"])
    print(r.data["anchor"])
    print(r.data["content"][:200])

asyncio.run(main())
```

```
2.5 Vectors (V) — Semantic overlay
cairn://architecture/cairn-technical-architecture/2-layered-architecture/layer-2-index/2-5-vectors-v-semantic-overlay
Dense embeddings per section + per chunk (chunks are sub-section units of ~512 tokens for long sections, aligned to sentence boundaries). Stored in a local vector store (LanceDB default; sqlite-vec ...
```

Progressive disclosure: the agent got the synopsis (~80 words) by default.
If it decides it needs the full body, it calls `expand(id, to="full")` to
get `raw_text`. No agent ever has to swallow the whole 18k-word document.

---

## Step 6 — Serve over MCP

```bash
.venv/bin/cairn serve /tmp/cairn-arch --fake
```

This starts the stdio MCP server. Point any compliant client at it
(Claude Code, Cursor, Cline, Goose) and they see all five tools
(`outline`, `get_section`, `expand`, `search_semantic`, `search_keyword`)
ready to call.

For Claude Code, in your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cairn-architecture": {
      "command": "/absolute/path/to/.venv/bin/cairn",
      "args": ["serve", "/tmp/cairn-arch", "--fake"]
    }
  }
}
```

Restart Claude Code. The agent can now reason about Cairn's architecture
without you pasting anything into the chat.

---

## Going further: real LLM, real embeddings

The defaults target a **local Ollama** so you keep the local-first promise
without paying for API tokens:

```bash
# in a separate terminal
ollama serve

# pull the models the defaults expect
ollama pull llama3.2:3b
ollama pull nomic-embed-text

# re-index without --fake
.venv/bin/cairn index ARCHITECTURE.md --out /tmp/cairn-arch
```

Now summaries are written by `llama3.2:3b` and embeddings by
`nomic-embed-text`. Semantic search becomes genuinely semantic.

To target OpenAI (or any other compatible endpoint) instead:

```bash
export CAIRN_LLM_BASE_URL=https://api.openai.com/v1
export CAIRN_LLM_MODEL=gpt-4o-mini
export CAIRN_LLM_API_KEY=sk-...

export CAIRN_EMBED_BASE_URL=https://api.openai.com/v1
export CAIRN_EMBED_MODEL=text-embedding-3-small
export CAIRN_EMBED_DIM=1536
export CAIRN_EMBED_API_KEY=sk-...

.venv/bin/cairn index ARCHITECTURE.md --out /tmp/cairn-arch
```

The wire shape (`/v1/chat/completions` and `/v1/embeddings`) is universal —
any compatible endpoint works without code changes.
