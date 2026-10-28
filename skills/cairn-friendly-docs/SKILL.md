---
name: cairn-friendly-docs
description: Use when creating, reorganizing, or reviewing repository documentation so it indexes well in Cairn/DocsGraph, including docs architecture, topic pages, cross-links, stable anchors, .cairn config, and architecture or organization relationship documents for AI coding agents.
---

# Cairn-Friendly Repository Documentation

Use this skill to create or refactor repository docs so Cairn can build a strong
documentation graph: clear document ids, stable section ids, specific headings,
cross-references, entity mentions, and source docs that agents can navigate with
progressive disclosure.

## Core Standard

Cairn rewards docs that expose authorial structure. Optimize for the agent
workflow: discover the right document, inspect the outline, drill into the exact
section, follow related sections, and cite stable anchors.

Non-negotiable rules:

- Create obvious entry points: `README.md`, `docs/index.md`, and a getting-started
  or installation guide when relevant.
- Put one major topic per page. Use semantic paths such as
  `docs/authentication.md`, `docs/configuration.md`, `docs/deployment.md`,
  `docs/testing.md`, `docs/api-reference.md`, and `docs/architecture.md`.
- Use headings that contain the real concept, task, API, module, or workflow
  name. Avoid chains of `Overview`, `Details`, `Advanced`, or `Misc`.
- Keep Markdown heading text stable. Cairn section ids are slug-based anchors.
- Separate guides, concepts, API reference, release history, migrations, ADRs,
  and operations docs.
- Put runnable command examples directly under the task heading they support.
- Repeat the canonical term in path/title/heading/body, and mention common
  synonyms once where useful. Do not stuff keywords.
- Cross-link related guides, concepts, API reference, ADRs, and architecture
  sections. Links create graph routes for follow-up retrieval.
- Keep human-authored source docs indexed. Exclude generated output, vendored
  docs, dependency folders, build artifacts, caches, and generated sites unless
  they are deliberately part of the docs contract.
- For multilingual docs, use explicit locale paths such as `docs/en/...`,
  `docs/zh/...`, `docs/ja/...`, and configure preferred locales.
- Include repository operation docs: local setup, test commands, release process,
  contribution flow, architecture/design notes, and security policy when
  applicable.

## Workflow

1. Inventory the repo documentation surface.
   - List source docs with `rg --files` or the repo's indexed file tool.
   - Identify generated or noisy docs that should be excluded.
   - If `.cairn/config.toml` exists, inspect include/exclude/preferred locale
     policy before changing docs.
   - If implementing architecture docs, inspect code structure with the repo's
     structural tools when available. Use literal search only for text, commands,
     filenames, config keys, and log strings.

2. Design the documentation graph before writing.
   - Pick canonical entry points.
   - Split mixed documents into topic pages.
   - Decide guide/concept/reference/history/operations boundaries.
   - Define cross-links between pages and sections.
   - Keep the graph shallow enough for discovery and deep enough for exact
     drilldown: useful H1, specific H2/H3, avoid over-nesting.

3. Write source docs as navigable sections.
   - Start each page with a precise H1 that matches the topic.
   - Use H2/H3 labels that users would search for.
   - Put task steps, commands, config examples, and expected outcomes near the
     relevant heading.
   - Link to related pages at the point of need, not only in a final list.
   - Prefer stable names over clever names.

4. Add or update `.cairn/config.toml` when the repo needs explicit policy.

```toml
include = ["README.md", "docs/**/*.md", "CHANGELOG.md"]
exclude = ["**/node_modules/**", "**/dist/**", "**/build/**", "docs/site/**"]
preferred_locales = ["en"]
```

5. Validate the result when DocsGraph is available.
   - Run `docsgraph init -y` only when no config exists and the user wants Cairn
     setup.
   - Run `docsgraph sync --fake`, `docsgraph status`, and a few representative
     `docsgraph query repo "<question>" --fake` checks.
   - Check that broad questions land on entry points or topic guides, not
     changelog-only evidence.
   - Check that exact task/API questions drill into the intended section.

## Recommended Repository Shape

Use this as a default starting point, then adapt to the actual project:

```text
README.md
CHANGELOG.md
SECURITY.md
CONTRIBUTING.md
docs/
  index.md
  getting-started.md
  installation.md
  configuration.md
  architecture.md
  operations.md
  testing.md
  release-process.md
  api-reference.md
  decisions/
    0000-template.md
```

For larger repos, prefer subdirectories by intent:

```text
docs/
  guides/
  concepts/
  reference/
  operations/
  decisions/
```

Do not split tiny repos just to match this tree. The standard is about clear
retrieval surfaces, not directory ceremony.

## Architecture Doc Pattern

Create or update `docs/architecture.md` when agents need to understand how the
system fits together.

Recommended sections:

- `# Architecture`
- `## System overview`
- `## Runtime flow`
- `## Main components`
- `## Data model`
- `## External integrations`
- `## Configuration`
- `## Extension points`
- `## Failure handling`
- `## Related decisions`

Write architecture docs as facts with stable names. Link each component to its
guide, reference page, ADR, or source module when useful.

## Organization Relationship Doc Pattern

Create `docs/organization.md`, `docs/repository-map.md`, or
`docs/operations/repository-map.md` when the repo has many modules, teams,
services, packages, or ownership boundaries.

Recommended sections:

- `# Repository map`
- `## Product areas`
- `## Modules and packages`
- `## Ownership and responsibilities`
- `## Dependencies between modules`
- `## Development workflow`
- `## Release workflow`
- `## Operational responsibilities`
- `## Related architecture and decisions`

Use tables for stable relationship facts:

| Area | Source path | Responsibility | Related docs |
|---|---|---|---|
| API server | `src/server/` | Serves public API requests | `docs/api-reference.md` |

For dependency or flow relationships, prefer short prose plus links over large
ASCII diagrams. Diagrams can help humans, but Cairn's retrieval quality comes
from headings, nearby text, links, and repeated entity names.

## Review Checklist

Before finishing, check:

- README answers identity, install, quickstart, and where to go next.
- `docs/index.md` links to the major docs surfaces.
- Every important topic has a named page or named section.
- Headings are specific enough to become useful `cairn://` anchors.
- Changelog and migration notes are isolated from primary feature docs.
- Generated output and dependency folders are excluded from Cairn indexing.
- Architecture, operations, testing, release, contribution, and security docs are
  present when the repo's maturity warrants them.
- Related pages link to each other in both directions where follow-up navigation
  would be natural.
