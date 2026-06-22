# Cairn Golden Documentation Standard

This document publishes Cairn's documentation preferences as a product
contract. It is for maintainers who want their repository docs to work well
with AI coding agents through Cairn, and for Cairn contributors who tune
retrieval behavior.

The standard is intentionally public: a new repository should be able to read
this document and understand what Cairn rewards, what it avoids, and how to
shape docs without reverse-engineering the ranker.

## Calibration Loop

Cairn's ranking and discovery rules should be calibrated against mature public
repositories, not against one favorite sample.

The loop is:

1. Run broad smoke tests across mature repositories with different doc shapes.
2. Inspect bad or surprising results by category, not by repository name.
3. Turn recurring failures into general rules, tests, or docs guidance.
4. Publish the rule so repository authors know the expected shape.
5. Keep a strict release gate that prevents sync, search, or drilldown
   regressions.

Rules must not special-case repository names, document ids, benchmark answers,
or one-off file paths. A rule is acceptable only when it applies to a general
documentation pattern, such as changelog intent, generated docs, duplicate
translation trees, command examples, API reference pages, or topic guide pages.

## Current Baseline

The current fake-plugin public smoke matrix spans 37 repositories across
Python, JavaScript/TypeScript, Rust, and Go ecosystems. The gate verifies:

- repository clone/discovery/sync works;
- every discovered source either indexes or reports an isolated failure;
- cross-document search returns hits;
- top hits can be drilled into with stable Cairn anchors.

This smoke matrix is a robustness gate, not a final quality benchmark. The
next level is a larger mature-repository corpus with labeled queries and
qualitative result review.

## What Cairn Rewards

### 1. Canonical entry points

A repository should have a small number of obvious entry points:

- `README.md` for product identity, install, quickstart, and links;
- `docs/index.md` or equivalent for documentation navigation;
- `docs/getting-started.md`, `docs/installation.md`, or equivalent for first
  successful use.

Cairn gives structural and lexical value to document ids, source paths, titles,
and shallow headings. Clear entry points help broad queries land on the right
surface before the agent drills down.

### 2. One topic per page

Topic pages should map to concepts users actually ask about:

- `docs/authentication.md`
- `docs/configuration.md`
- `docs/deployment.md`
- `docs/testing.md`
- `docs/mcp-server.md`
- `docs/api-reference.md`

Pages that mix unrelated concepts are harder to rank because dense, sparse,
path, and heading signals disagree.

### 3. Headings that say the thing

Use headings that contain the concept, task, or API name:

```markdown
# Authentication

## Configure API keys

## OAuth provider setup
```

Avoid headings such as `Overview`, `More`, `Advanced`, or `Details` unless the
parent heading already provides the missing context. Cairn indexes the section
tree, and headings are stronger signals than body-only mentions.

### 4. Stable section anchors

Use stable Markdown headings and avoid rewriting heading text casually. Cairn
returns `cairn://` anchors and routes follow-up tools through section ids. Stable
headings make agent citations easier to verify over time.

### 5. Guide, reference, and history separation

Separate these surfaces:

- guide/task docs: how to do something;
- concept docs: what something means and when to use it;
- API reference: exact classes, methods, parameters, schemas;
- history docs: changelog, release notes, migrations, breaking changes.

Cairn intentionally intent-gates changelog, release-note, and migration-history
documents. They remain first-class results for release/version/change queries,
but broad topic queries should prefer guides, API docs, and README-style docs
when comparable evidence exists.

### 6. Repeated vocabulary plus synonyms

Use the canonical term in title/path/heading/body, then mention common synonyms
once where useful:

```markdown
# Configuration

Runtime settings can be configured with environment variables or config files.
```

This helps both lexical and sparse retrieval without stuffing keywords.

### 7. Command examples near task headings

For CLI or SDK projects, put runnable commands under the task section they
belong to:

````markdown
## Install the package

```bash
pip install example
```
````

Cairn boosts exact command phrases when users search for command-like queries.

### 8. Locale-aware documentation trees

If a repository publishes multiple language trees, use explicit path segments:

- `docs/en/...`
- `docs/de/...`
- `docs/ja/...`
- `docs/zh/...`

Cairn can infer broad query locale for common cases and repositories can set
`preferred_locales` in `.cairn/config.toml`. Locale preference is a rank factor,
not a hard filter: non-preferred language pages remain retrievable when their
evidence is stronger or the preferred tree lacks a match.

### 9. Cross-links between related pages

Link concept pages, API references, and guides to each other. Cairn indexes
cross-references and entity mentions, so a good docs graph gives the agent
better follow-up routes after the first hit.

### 10. Fresh source docs over generated noise

Commit human-authored source docs. Keep generated build output, dependency
folders, vendored docs, and caches out of the indexed surface unless they are
deliberately part of the documentation contract.

Use `.cairn/config.toml` to encode this policy explicitly:

```toml
include = ["README.md", "docs/**/*.md", "CHANGELOG.md"]
exclude = ["**/node_modules/**", "**/dist/**", "**/build/**", "docs/site/**"]
preferred_locales = ["en"]
```

### 11. Repo docs that explain repo operation

AI coding agents often need operational docs, not just product docs. Mature
repositories should expose:

- local development setup;
- test commands;
- release process;
- architecture or design notes;
- contribution workflow;
- security or reporting policy, when applicable.

These surfaces help `repo_context` answer practical repository questions.

## Patterns That Hurt Retrieval

Avoid these unless there is a deliberate reason:

- a giant README that contains every concept with shallow or vague headings;
- changelog/release notes as the only place a feature is documented;
- many duplicate pages with the same title and no path distinction;
- generated API dumps mixed into human guides without clear path separation;
- docs hidden in build artifacts or dependency folders;
- multiple unrelated topics under a heading named `Overview`;
- file names like `page1.md`, `misc.md`, `notes.md`, or `new.md`;
- headings that change frequently, breaking stable anchors;
- one query-critical term appearing only in a code block or changelog entry.

## Scorecard

Use this scorecard for repository docs reviews.

| Area | Good | Needs work |
|---|---|---|
| Entry points | README + docs index + getting started | README only or generated site only |
| Topic shape | One major concept per page | Mixed-topic pages |
| Heading quality | Specific H1/H2/H3 labels | Generic `Overview` / `Details` chains |
| History separation | Changelog is named and isolated | Changelog is the main feature docs |
| API/reference split | API reference separate from guides | API dumps mixed into tutorials |
| Locale layout | Explicit `docs/en`, `docs/zh`, etc. | Duplicate translated pages without locale paths |
| Cross-links | Related concepts link to each other | Isolated pages with no references |
| Freshness | Source docs committed and indexed | Generated or stale docs dominate |
| Agent operations | Setup/test/release/contrib docs present | Only user-facing marketing docs |

## Cairn Maintainer Policy

When a mature repository exposes a bad result, fix Cairn in this order:

1. Improve documentation discovery defaults when the indexed surface is wrong.
2. Improve evidence blending when the right page is indexed but under-ranked.
3. Improve `repo_context` composition when search is correct but the returned
   context is not agent-ready.
4. Improve performance through cache layout, batched scoring, or general
   candidate stages only when recall gates keep passing.
5. Add a regression test that models the documentation pattern, not the
   repository.
6. Update this standard if the rule changes what repositories should expect.

Do not hardcode a repository, a benchmark answer, or a specific external file
path. Cairn's credibility comes from stable public rules.
