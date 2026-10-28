# Prepare documentation with local Python snippets

Some documentation stores examples in separate files. Typer, for example,
uses directives such as `{* docs_src/example.py hl[1:3] *}`. Indexing that
Markdown directly preserves the directive but does not supply the example.

From a Cairn source checkout, prepare a separate Markdown snapshot:

```sh
python scripts/materialize_doc_snippets.py \
  --root /path/to/typer \
  --output /tmp/typer-expanded-docs \
  docs/tutorial/options/version.md \
  docs/tutorial/testing.md
```

The destination must be new and outside the source repository. The command
preserves document paths, expands supported `docs_src/*.py` directives into
complete Python fences, and writes `snippet-manifest.json`. Highlight annotations
are ignored; the original code is retained. The code is never executed.

Index the prepared Markdown using the existing indexing workflow. Citations
and byte positions then refer to this **prepared snapshot**. The manifest maps
each inserted Unicode character span to the original snippet path and SHA-256,
and records original-document and output hashes. Do not describe prepared
positions as byte positions in the original unexpanded Markdown.

Absolute/traversing paths, symlink escapes, unsupported directives and missing
files fail before the destination is created. Existing output is not overwritten.
Inputs are limited to 4 MiB per file and output to 32 MiB; repeated includes
are checked during expansion. No remote include or Python execution is supported.

The command is deliberately explicit: it does not change the default Markdown
parser or watch upstream files. After a document or snippet changes, rerun into
a fresh destination and refresh the index from that snapshot. An index of old
prepared Markdown cannot automatically detect a change in the original project.

This is a source-checkout utility, not an installed `docsgraph` subcommand.
It was checked against nine pinned Typer documents containing 37 snippet
directives, with every inserted source span and hash verified. The associated
Agent comparison used an earlier equivalent snippet-expansion fixture;
that comparison is not an Agent test of this new command itself.
