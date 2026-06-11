<!--
  Thanks for opening a PR! Before you submit, please make sure the items
  below are taken care of. CI will catch most of them, but it helps
  reviewers move faster if you've already verified them locally.
-->

## Summary

<!-- One sentence: what changes and why. -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] Feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Documentation only
- [ ] Refactor / internal cleanup

## Linked ADR / Roadmap milestone

<!--
  If this PR touches PRODUCT.md, ARCHITECTURE.md, the MCP tool catalog,
  or on-disk formats, an ADR is required. Link it here.
  Otherwise reference the ROADMAP milestone (e.g. "v0.2.5").
-->

## Test plan

<!--
  Walk through what you ran locally. Concrete commands beat "I tested it".
-->

```
ruff check src tests
mypy src/cairn
pytest tests/unit -q
```

- [ ] Unit tests added / updated
- [ ] CHANGELOG.md updated (for user-facing changes)

## Anti-checklist (CLAUDE.md anti-patterns)

The following are non-goals; check that this PR does **not**:

- [ ] Add a chatbot / answer-generation tool to the public catalog
- [ ] Replace structure-aware retrieval with vector-chunking as the primary path
- [ ] Change progressive-disclosure defaults to return more by default
- [ ] Introduce a network dependency in the default install
- [ ] Pull a heavy dependency without an ADR
