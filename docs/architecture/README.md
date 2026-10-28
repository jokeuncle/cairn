# Current architecture artifacts

[Interactive architecture](../architecture-current.html) ·
[Light SVG](../assets/cairn-architecture-light.svg) ·
[Dark SVG](../assets/cairn-architecture-dark.svg)

These artifacts describe experimental alpha0.1.0a13, including ADR-0016 and
ADR-0017. They do not certify production or commercial readiness. The diagram separates initial
index construction, cached queries and the conditional hybrid-model path.
The complete API behavior and limits live in [the tool contract](../specs/mcp-tools.md).

`current.architecture.json` is the editable Archify specification. Its source
citations reference a75-module release-candidate snapshot. Its graph/impact implementation matches the reference-impact evaluation wheel.
The release also updates package metadata and adds the separately regression-tested
source-namespace confidence guard (ADR-0018); earlier Agent cost results remain
results for their frozen builds, rather than measurements of this last guard.
`source-snapshot.json` records the source SHA-256 values, upstream parent and an
isolated source-evidence Git snapshot. That snapshot was created outside the
user repository; its revision is **not an upstream GitHub commit**, and source
links are explicitly local-only. User repository HEAD/index were not changed.

Archify3.1 automatic schema, source-evidence, artifact and browser checks passed.
The generated HTML was visually inspected in Ego Lite in light/dark desktop
views; both static SVGs were exported using its own viewer. The SVGs contain no
scripts. The HTML is standalone. See `verification.json` for artifact hashes and
the scope of those checks; these are diagram checks, not Agent cost evidence.

For a later source change, recreate a clean isolated snapshot from the intended
source bytes, update the source hashes and candidate revision/ranges, then run
the installed Archify CLI from the project root:

```sh
node /path/to/archify/bin/archify.mjs finalize architecture \
  docs/architecture/current.architecture.json docs/architecture-current.html \
  --repo-root /path/to/isolated-source-snapshot --quality showcase \
  --out-dir /path/to/new-verification-directory --json
```

Export fresh light/dark SVGs after validation and inspect them before replacing
the README images. Do not relabel uncommitted bytes as evidence for upstream
HEAD or edit generated HTML after its provenance receipt is issued.
