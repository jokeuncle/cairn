# Explicit document and query instructions

Some embedding models require different instructions for indexed documents and
search queries. Nomic v1.5's [official model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5#usage)
specifies `search_document: ` and `search_query: `. Cairn can configure these
explicitly; it does not infer instructions from a model name.

For an endpoint serving that model, set these in the environment used by both
indexing and querying (replace endpoint/model/dimension as appropriate):

```sh
export CAIRN_EMBED_PROVIDER=windowed-openai-compatible
export CAIRN_EMBED_BASE_URL=http://localhost:11434/v1
export CAIRN_EMBED_MODEL=nomic-embed-text
export CAIRN_EMBED_DIM=768
export CAIRN_EMBED_DOCUMENT_PREFIX='search_document: '
export CAIRN_EMBED_QUERY_PREFIX='search_query: '

docsgraph sync --real
docsgraph query tool repo_context \
  '{"query":"connection timeouts","level":"evidence"}' --real
```

Keep the trailing spaces. Both fields default to empty, preserving existing
providers/index identities. Leave them empty when the model does not need
textual instructions or the server already supplies them. Each physical input
window receives its instruction; window byte budgets cover original content,
so leave room for instructions and provider special tokens. This is not a
tokenizer bound. Original cached text, source spans and citations are unchanged.

Both prefix values contribute to a hashed model identity. Changing either
requires rebuilding vectors and using the same configuration when serving or
querying. The CLI's existing compatibility check rejects mismatched identities
before a paid query embedding. `doctor --real` reports index/query compatibility.
MCP configuration generated with `--env-from-current` carries the two variables
along with other `CAIRN_*` settings; normal MCP output is unchanged.

For Python integrations, indexing continues to call `Embedder.embed(texts)`.
Query consumers call `cairn.embed.base.embed_query_texts(embedder, texts)`; it
uses optional `embed_queries(texts)` when available and otherwise falls back to
legacy `embed`. Existing provider implementations need no new method. A custom
provider can implement the optional method for a native query-specific API.
The generic `TaskPrefixEmbedder` preserves that delegated query role. Both
repository/document lookup and the flat-RAG benchmark control use this helper.

Correct model instructions do not certify retrieval relevance, semantic
coverage, task success or a cost advantage. Earlier external prefix adapters
also did not establish commercial superiority. See
[ADR-0015](decisions/0015-explicit-query-document-embedding-roles.md).
