# Read cached documentation from the CLI

`docsgraph query tool` exposes the existing read-only repository tools without
starting an MCP client. It accepts a tool name and one JSON argument object.
The default output is a complete compact JSON envelope; a failure exits nonzero.

```sh
docsgraph query tool repo_context \
  '{"query":"timeout limits","level":"evidence","k":5}' \
  --repo /path/to/project --retrieval lexical --format text

docsgraph query tool get_section \
  '{"id":"cairn://docs-guide/guide/limits","level":"full"}' \
  --repo /path/to/project
```

Available names are `repo_context`, `search_documents`, `get_section`,
`get_related`, `outline`, `read_range`, `search_keyword`, `list_documents`,
`repo_graph` and `repo_impact`.
Arguments follow the [tool specification](specs/mcp-tools.md). Select the
repository with `--repo`; the CLI rejects `projectPath` in JSON arguments.
`--trace` opts into diagnostics. Backend progress goes to stderr, leaving stdout
for the result. Canonical `cairn://` citations can be used directly as section IDs.

## Explicit retrieval strategy

`--retrieval lexical` applies to `search_documents` and `repo_context`. It uses
the existing cached section bodies, summaries, BM25/field support and structure.
It neither constructs an embedding provider nor reads vector entries. Cached
section reads also need no provider, so they work while a model endpoint is
unavailable. Other reads ignore the strategy flag.

An existing index and its metadata are still required. This option does not
remove initial indexing, summary generation or storage costs. Lexical matches
may miss paraphrases; an empty result does not prove absence. Semantic retrieval
is an explicit choice with `--retrieval hybrid` and the normal model configuration.
There is no automatic score-threshold fallback. Hybrid CLI queries check that
the configured provider matches the index before querying.

The same strategy is available as `retrieval="lexical"` in repository
`search_documents`/`repo_context` MCP arguments. Their default remains hybrid;
the default context view remains synopsis. Original full/evidence text is still
opt-in. Lexical results identify their mode and preserve stale/skipped warnings.

## Optional complete text representation

`--format text` can show multiline payload strings verbatim instead of JSON
escapes. A `CAIRN-TEXT-1` header names a collision-free marker; JSON marker
objects refer to `TEXT <id> <Unicode-character-length>` records below. Every
value, including code, citations, spans, scope and recovery hints, is retained.
Lists of equally shaped metadata records can share an explicit `columns` list
and positional `rows`, reducing repeated section/hit keys without dropping fields.
Identical strings can share a record. CR/control-containing strings remain
JSON-escaped, and the decoder accommodates CRLF transport framing.

If framing would be larger in UTF-8 bytes, the command returns ordinary compact
JSON. This is a serialized-size bound, not a model-token or whole-task cost
guarantee. `tokens_returned` remains the backend's approximate payload estimate,
not an exact tokenizer count for the rendered stdout. Machine clients can keep
the default JSON, or reconstruct text output using `cairn.cli_output.parse_tool_text`.
MCP wire output is unchanged.

## Explicit document references

```sh
docsgraph query tool repo_graph \
  '{"view":"documents","max_documents":100,"max_references":200}' \
  --repo /path/to/project --format text
```

This opt-in view follows explicit cross-document Markdown links in cached
section bodies. It needs no model endpoint after indexing. Each document-pair
edge includes a source-section citation; `include_evidence=true` opts into a
short verbatim source-block excerpt. Heading links, HTML links and unknown
targets are outside its declared scope; URL fragments are not validated.
Check `complete`, scope and stale/skipped/unavailable records before treating
an absent edge as absent in that scope. The default section/entity graph stays
unchanged. Document references alone do not establish semantic or code impact.

For bounded reverse paths, cycle membership and deletion reachability, use the
local deterministic reference view of the existing impact tool:

```sh
docsgraph query tool repo_impact \
  '{"view":"references","doc":"docs/guide.md","entry":"README.md","max_hops":3}' \
  --repo /path/to/project --format json
```

`doc`/`entry` can be exact indexed source paths or document IDs. Without `entry`,
deletion reachability is unrequested and returned as null. Check completeness
and limits; proof edges carry source-section anchors. Ordinary JSON is convenient
for local programs consuming metadata. Original source excerpts remain opt-in.

Source bodies still exclude descendants; evidence blocks may omit conditions.
Reuse complete evidence and expand missing requirements. Neither representation
certifies semantic coverage or task correctness. Both options are experimental;
their end-to-end cost benefit must be measured on the intended workload.

The [ten-session development screen](research/2026-10-25-lean-cli.md) tests the
actual installed product CLI. Every arm passes both tasks, but the preselected
lexical/text candidate fails the cost gate. Keep lexical mode for endpoint-free
queries; these results do not support promoting it as a cheaper default.

A subsequent [native-source shortcut experiment](research/2026-10-25-source-cli.md)
increased all input/output cost components against fresh controls. Its two
commands were withdrawn; use the shared `query tool` interface above.
