# ruff: noqa: E501
"""Static inspector generation for built Cairn indexes."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from cairn.tools.base import DocumentIndex


def write_inspector(index: DocumentIndex, *, out: Path) -> Path:
    """Write a standalone HTML inspector for a loaded document index."""
    out.parent.mkdir(parents=True, exist_ok=True)
    data = _build_payload(index)
    out.write_text(_render_html(data), encoding="utf-8")
    return out


def _build_payload(index: DocumentIndex) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for section in index.tree:
        summary = index.summaries.get(section.id)
        nodes.append(
            {
                "id": section.id,
                "label": section.title,
                "kind": "section",
                "level": section.level,
                "path": " / ".join(section.path),
                "gist": summary.gist if summary is not None else "",
                "synopsis": summary.synopsis if summary is not None else "",
                "head": section.raw_text.strip()[:320],
            }
        )
        if section.parent is not None:
            edges.append({"source": section.parent, "target": section.id, "kind": "tree"})

    section_ids = {node["id"] for node in nodes}
    if index.xrefs is not None:
        for ref in index.xrefs:
            if ref.src in section_ids and ref.dst in section_ids:
                edges.append(
                    {
                        "source": ref.src,
                        "target": ref.dst,
                        "kind": f"xref:{ref.kind}",
                        "confidence": ref.confidence,
                    }
                )

    entity_count = 0
    if index.entities is not None:
        entities = sorted(
            index.entities,
            key=lambda ent: (-len(ent.mentions), ent.canonical),
        )
        entity_count = len(entities)
        for entity in entities[:60]:
            entity_id = f"entity:{entity.kind}:{entity.canonical}"
            nodes.append(
                {
                    "id": entity_id,
                    "label": entity.canonical,
                    "kind": "entity",
                    "entityKind": entity.kind,
                    "mentions": len(entity.mentions),
                    "surfaceForms": list(entity.surface_forms),
                }
            )
            seen_sections: set[str] = set()
            for mention in entity.mentions:
                if mention.section_id in section_ids and mention.section_id not in seen_sections:
                    edges.append(
                        {
                            "source": entity_id,
                            "target": mention.section_id,
                            "kind": "mention",
                        }
                    )
                    seen_sections.add(mention.section_id)

    return {
        "docId": index.doc_id,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "sections": len(index.tree),
            "entities": entity_count,
            "entitiesShown": sum(1 for node in nodes if node["kind"] == "entity"),
            "entitiesHidden": max(0, entity_count - 60),
            "maxDepth": max((node.get("level", 0) for node in nodes), default=0),
            "treeEdges": sum(1 for edge in edges if edge["kind"] == "tree"),
            "xrefEdges": sum(1 for edge in edges if str(edge["kind"]).startswith("xref:")),
            "mentionEdges": sum(1 for edge in edges if edge["kind"] == "mention"),
        },
    }


def _render_html(data: dict[str, Any]) -> str:
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(str(data["docId"]), quote=True)
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cairn Inspector - __DOC_TITLE__</title>
<style>
:root {
  --bg: #f5f6f1;
  --surface: #ffffff;
  --surface-2: #fafbf7;
  --ink: #161d18;
  --muted: #657268;
  --quiet: #8c978f;
  --line: #d8ded5;
  --line-strong: #bcc7bf;
  --section: #1f6f78;
  --entity: #a25f20;
  --tree: #5ca69a;
  --mention: #c8923a;
  --xref: #6f5aa5;
  --focus: #0c5b49;
  --danger: #9b3e30;
  --shadow: 0 18px 50px rgba(31, 42, 35, .11);
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ink);
  background: var(--bg);
  letter-spacing: 0;
}
.app {
  display: grid;
  grid-template-columns: 304px minmax(520px, 1fr) 380px;
  min-height: 100vh;
}
.sidebar,
.details {
  background: var(--surface);
  overflow: auto;
}
.sidebar {
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
}
.details {
  border-left: 1px solid var(--line);
}
.sidebar-head,
.details-head,
.panel-block {
  padding: 18px;
}
.sidebar-head,
.details-head {
  border-bottom: 1px solid var(--line);
}
h1,
h2,
h3,
p {
  margin: 0;
}
h1 {
  font-size: 19px;
  line-height: 1.2;
}
h2 {
  font-size: 18px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
h3 {
  font-size: 13px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 10px;
}
.subtle {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
  margin-top: 6px;
  overflow-wrap: anywhere;
}
.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--line);
}
.stat {
  min-height: 72px;
  padding: 14px 18px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}
.stat:nth-child(2n) {
  border-right: 0;
}
.stat strong {
  display: block;
  font-size: 22px;
  line-height: 1;
}
.stat span {
  color: var(--muted);
  font-size: 12px;
}
button,
input {
  border: 1px solid var(--line);
  border-radius: 6px;
  font: inherit;
  background: var(--surface);
  color: var(--ink);
}
button {
  min-height: 34px;
  padding: 7px 10px;
  cursor: pointer;
}
button:hover,
.row:hover {
  border-color: var(--line-strong);
  background: #f7faf5;
}
.segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.segmented button {
  text-align: center;
}
.segmented button.active {
  border-color: var(--focus);
  background: #e8f2ee;
  color: #103f35;
}
.legend {
  display: grid;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.swatch {
  width: 18px;
  height: 5px;
  border-radius: 999px;
  background: var(--line);
  flex: 0 0 auto;
}
.swatch.section {
  background: var(--section);
}
.swatch.entity {
  background: var(--entity);
}
.swatch.tree {
  background: var(--tree);
}
.swatch.mention {
  background: var(--mention);
}
.swatch.xref {
  background: var(--xref);
}
.search {
  width: 100%;
  height: 38px;
  padding: 0 11px;
}
.row-list {
  display: grid;
  gap: 7px;
  max-height: 42vh;
  overflow: auto;
}
.row {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 9px 10px;
  background: var(--surface);
  cursor: pointer;
}
.row.active {
  border-color: var(--focus);
  background: #edf5f0;
}
.row-title {
  font-size: 13px;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.row-meta {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}
main {
  position: relative;
  min-width: 0;
  overflow: hidden;
}
.topbar {
  position: absolute;
  left: 18px;
  right: 18px;
  top: 14px;
  z-index: 2;
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  pointer-events: none;
}
.tool-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: rgba(255, 255, 255, .88);
  box-shadow: var(--shadow);
  pointer-events: auto;
}
.tool-pill button {
  min-height: 28px;
  padding: 4px 8px;
}
.tool-pill button.active {
  border-color: var(--focus);
  background: #e8f2ee;
  color: #103f35;
}
.status {
  color: var(--muted);
  font-size: 12px;
}
svg {
  display: block;
  width: 100%;
  height: 100vh;
  background:
    linear-gradient(90deg, rgba(22, 29, 24, .035) 1px, transparent 1px),
    linear-gradient(0deg, rgba(22, 29, 24, .035) 1px, transparent 1px),
    radial-gradient(circle at 30% 20%, #ffffff 0, #f5f6f1 42%, #edf1ea 100%);
  background-size: 40px 40px, 40px 40px, 100% 100%;
}
.edge {
  stroke: var(--line);
  stroke-width: 1.4;
  opacity: .78;
}
.edge.tree {
  stroke: var(--tree);
  stroke-width: 2;
}
.edge.mention {
  stroke: var(--mention);
  stroke-dasharray: 5 5;
}
.edge.xref {
  stroke: var(--xref);
  stroke-width: 2;
}
.edge.active {
  opacity: 1;
  stroke-width: 3;
}
.node {
  cursor: grab;
}
.node:active {
  cursor: grabbing;
}
.node circle {
  stroke: #fff;
  stroke-width: 2;
  filter: drop-shadow(0 5px 12px rgba(24, 32, 27, .2));
}
.node.section circle {
  fill: var(--section);
}
.node.entity circle {
  fill: var(--entity);
}
.node.selected circle {
  stroke: #102d27;
  stroke-width: 3;
}
.node text {
  font-size: 12px;
  fill: var(--ink);
  opacity: 0;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, .9);
  stroke-width: 4px;
  stroke-linejoin: round;
  pointer-events: none;
}
.node.selected text,
.node.neighbor text,
.node.show-label text {
  opacity: 1;
}
.dim {
  opacity: .15;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}
.pill {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--muted);
  background: var(--surface-2);
}
.details-section {
  padding: 18px;
  border-bottom: 1px solid var(--line);
}
.details-section p {
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.rel-list {
  display: grid;
  gap: 7px;
}
.rel-item {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 9px 10px;
  font-size: 13px;
  background: var(--surface-2);
}
.rel-item strong {
  display: block;
  margin-bottom: 3px;
}
.empty {
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 1180px) {
  .app {
    grid-template-columns: 280px minmax(420px, 1fr);
  }
  .details {
    grid-column: 1 / -1;
    border-left: 0;
    border-top: 1px solid var(--line);
    max-height: 44vh;
  }
}
@media (max-width: 760px) {
  .app {
    display: block;
  }
  .sidebar,
  .details {
    border: 0;
  }
  svg {
    height: 68vh;
  }
  .topbar {
    left: 10px;
    right: 10px;
    top: 10px;
  }
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="sidebar-head">
      <h1>Cairn Inspector</h1>
      <p class="subtle" id="doc"></p>
    </div>
    <div class="stats" id="stats"></div>
    <div class="panel-block">
      <h3>View</h3>
      <div class="segmented">
      <button data-mode="combined" class="active">Combined relations</button>
      <button data-mode="tree">Outline tree</button>
      <button data-mode="entities">Entity mentions</button>
      <button data-mode="xrefs">Cross references</button>
      </div>
    </div>
    <div class="panel-block">
      <h3>Search</h3>
      <input class="search" id="search" placeholder="Filter graph">
    </div>
    <div class="panel-block">
      <h3>Visible Nodes</h3>
      <div class="row-list" id="node-list"></div>
    </div>
    <div class="panel-block">
      <h3>Legend</h3>
      <div class="legend">
        <div class="legend-row"><span class="swatch section"></span> Section</div>
        <div class="legend-row"><span class="swatch entity"></span> Entity</div>
        <div class="legend-row"><span class="swatch tree"></span> Parent-child</div>
        <div class="legend-row"><span class="swatch mention"></span> Mention</div>
        <div class="legend-row"><span class="swatch xref"></span> Cross-reference</div>
      </div>
    </div>
  </aside>
  <main>
    <div class="topbar">
      <div class="tool-pill">
        <button id="fit">Fit</button>
        <button id="stabilize">Stabilize</button>
        <button id="labels">Labels</button>
        <span class="status" id="status"></span>
      </div>
    </div>
    <svg id="graph" role="img" aria-label="Cairn index relationship graph"></svg>
  </main>
  <section class="details" id="details"></section>
</div>
<script>
const DATA = __DATA__;
const svg = document.getElementById('graph');
const details = document.getElementById('details');
const search = document.getElementById('search');
const nodeList = document.getElementById('node-list');
const statusEl = document.getElementById('status');
const SVG_NS = 'http://www.w3.org/2000/svg';
const PERF = {
  largeGraph: DATA.nodes.length > 80 || DATA.edges.length > 360,
  maxVisibleEdges: DATA.edges.length > 900 ? 560 : DATA.edges.length > 360 ? 360 : 900,
  neighborLabelBudget: DATA.nodes.length > 80 || DATA.edges.length > 360 ? 12 : 28,
  allLabelBudget: DATA.nodes.length > 80 || DATA.edges.length > 360 ? 42 : 140,
  allLabelNodeLimit: 120,
  settleLimit: DATA.nodes.length > 80 || DATA.edges.length > 360 ? 48 : 130,
  stabilizeTicks: DATA.nodes.length > 80 || DATA.edges.length > 360 ? 72 : 180,
};
let mode = 'combined';
let selectedId = DATA.nodes[0] ? DATA.nodes[0].id : null;
let nodes = [];
let edges = [];
let untrimmedEdgeCount = 0;
let clippedEdgeCount = 0;
let raf = null;
let settleTicks = 0;
let dragging = null;
let showAllLabels = !PERF.largeGraph;
let edgeEls = [];
let nodeEls = new Map();
let layoutCache = new Map();
function edgeVisible(e) {
  if (mode === 'tree') return e.kind === 'tree';
  if (mode === 'entities') return e.kind === 'mention';
  if (mode === 'xrefs') return String(e.kind).startsWith('xref:');
  return true;
}
function nodeVisible(n) {
  if (mode === 'tree') return n.kind === 'section';
  if (mode === 'entities') return n.kind === 'entity' || DATA.edges.some(e => e.kind === 'mention' && (e.source === n.id || e.target === n.id));
  if (mode === 'xrefs') return n.kind === 'section';
  return true;
}
function nodeSearchText(n) {
  return (n.label + ' ' + (n.path || '') + ' ' + (n.gist || '') + ' ' + (n.synopsis || '') + ' ' + (n.entityKind || '')).toLowerCase();
}
function filteredData() {
  const q = search.value.trim().toLowerCase();
  let outNodes = DATA.nodes.filter(nodeVisible);
  let matched = new Set();
  if (q) {
    matched = new Set(outNodes.filter(n => nodeSearchText(n).includes(q)).map(n => n.id));
    for (const e of DATA.edges) {
      if (matched.has(e.source)) matched.add(e.target);
      if (matched.has(e.target)) matched.add(e.source);
    }
    outNodes = outNodes.filter(n => matched.has(n.id));
  }
  const ids = new Set(outNodes.map(n => n.id));
  const outEdges = DATA.edges.filter(e => edgeVisible(e) && ids.has(e.source) && ids.has(e.target));
  const visibleEdges = prioritizedEdges(outEdges, matched);
  untrimmedEdgeCount = outEdges.length;
  clippedEdgeCount = Math.max(0, outEdges.length - visibleEdges.length);
  return {
    nodes: outNodes,
    edges: visibleEdges,
  };
}
function prioritizedEdges(items, matched) {
  if (items.length <= PERF.maxVisibleEdges) return items;
  const selected = selectedId;
  return [...items].sort((a, b) => edgePriority(b, selected, matched) - edgePriority(a, selected, matched)).slice(0, PERF.maxVisibleEdges);
}
function edgePriority(e, selected, matched) {
  let score = e.kind === 'tree' ? 30 : String(e.kind).startsWith('xref:') ? 22 : 14;
  if (selected && (e.source === selected || e.target === selected)) score += 100;
  if (matched.has(e.source) || matched.has(e.target)) score += 60;
  if (e.confidence) score += Number(e.confidence) * 10;
  return score;
}
function initLayout() {
  const rect = svg.getBoundingClientRect();
  const w = rect.width || 1000;
  const h = rect.height || 800;
  const f = filteredData();
  nodes = f.nodes.map((n, i) => {
    const row = Math.floor(i / 4);
    const column = i % 4;
    const depth = Math.min(n.level || 1, 6);
    const cached = layoutCache.get(n.id);
    return {
    ...n,
    x: cached ? cached.x : n.kind === 'entity' ? w - 160 - (column * 18) : 110 + depth * 90 + (column * 18),
    y: cached ? cached.y : 86 + ((row * 58) % Math.max(160, h - 128)),
    vx: 0,
    vy: 0,
    fixed: false,
  };
  });
  edges = f.edges;
  settleTicks = 0;
  renderNodeList();
  updateStatus();
}
function buildGraphDom() {
  svg.innerHTML = '';
  edgeEls = [];
  nodeEls = new Map();
  const defs = document.createElementNS(SVG_NS, 'defs');
  const marker = document.createElementNS(SVG_NS, 'marker');
  marker.setAttribute('id', 'arrow');
  marker.setAttribute('viewBox', '0 0 10 10');
  marker.setAttribute('refX', '9');
  marker.setAttribute('refY', '5');
  marker.setAttribute('markerWidth', '6');
  marker.setAttribute('markerHeight', '6');
  marker.setAttribute('orient', 'auto-start-reverse');
  const arrow = document.createElementNS(SVG_NS, 'path');
  arrow.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
  arrow.setAttribute('fill', '#6f5aa5');
  marker.appendChild(arrow);
  defs.appendChild(marker);
  svg.appendChild(defs);

  const edgeLayer = document.createElementNS(SVG_NS, 'g');
  edgeLayer.setAttribute('class', 'edge-layer');
  const nodeLayer = document.createElementNS(SVG_NS, 'g');
  nodeLayer.setAttribute('class', 'node-layer');
  svg.appendChild(edgeLayer);
  svg.appendChild(nodeLayer);

  const edgeFragment = document.createDocumentFragment();
  for (const e of edges) {
    const line = document.createElementNS(SVG_NS, 'line');
    const edgeClass = e.kind === 'tree' ? 'tree' : e.kind === 'mention' ? 'mention' : 'xref';
    line.setAttribute('class', 'edge ' + edgeClass);
    if (edgeClass === 'xref') line.setAttribute('marker-end', 'url(#arrow)');
    edgeFragment.appendChild(line);
    edgeEls.push({ edge: e, el: line, edgeClass });
  }
  edgeLayer.appendChild(edgeFragment);

  const nodeFragment = document.createDocumentFragment();
  for (const n of nodes) {
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('class', 'node ' + n.kind);
    g.addEventListener('pointerdown', event => startDrag(event, n.id));
    g.addEventListener('click', () => selectNode(n.id));
    const c = document.createElementNS(SVG_NS, 'circle');
    c.setAttribute('r', n.kind === 'entity' ? Math.min(18, 7 + Math.sqrt(n.mentions || 1) * 3) : Math.max(8, 16 - (n.level || 1)));
    const t = document.createElementNS(SVG_NS, 'text');
    t.setAttribute('x', 14); t.setAttribute('y', 4);
    t.textContent = n.label.length > 34 ? n.label.slice(0, 32) + '...' : n.label;
    g.appendChild(c); g.appendChild(t);
    nodeFragment.appendChild(g);
    nodeEls.set(n.id, g);
  }
  nodeLayer.appendChild(nodeFragment);
}
function tick() {
  const rect = svg.getBoundingClientRect();
  const w = rect.width || 1000;
  const h = rect.height || 800;
  const byId = new Map(nodes.map(n => [n.id, n]));
  for (let step = 0; step < 1; step++) {
    for (const n of nodes) {
      if (n.fixed) continue;
      n.vx += (w / 2 - n.x) * 0.0008;
      n.vy += (h / 2 - n.y) * 0.0008;
      if (n.kind === 'section') n.vx += ((120 + Math.min(n.level || 1, 5) * 115) - n.x) * 0.0017;
      if (n.kind === 'entity') n.vx += ((w - 190) - n.x) * 0.0014;
    }
    const pairStep = nodes.length > 180 ? Math.ceil(nodes.length / 160) : 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j += pairStep) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        const d2 = dx * dx + dy * dy || 1;
        const d = Math.sqrt(d2);
        const force = Math.min(4200 / d2, 1.8);
        dx /= d; dy /= d;
        if (!a.fixed) {
          a.vx -= dx * force; a.vy -= dy * force;
        }
        if (!b.fixed) {
          b.vx += dx * force; b.vy += dy * force;
        }
      }
    }
    for (const e of edges) {
      const a = byId.get(e.source), b = byId.get(e.target);
      if (!a || !b) continue;
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const desired = e.kind === 'tree' ? 145 : 220;
      const force = (d - desired) * 0.012;
      dx /= d; dy /= d;
      if (!a.fixed) {
        a.vx += dx * force; a.vy += dy * force;
      }
      if (!b.fixed) {
        b.vx -= dx * force; b.vy -= dy * force;
      }
    }
    for (const n of nodes) {
      if (n.fixed) continue;
      n.vx *= 0.82; n.vy *= 0.82;
      n.x = Math.max(28, Math.min(w - 28, n.x + n.vx));
      n.y = Math.max(62, Math.min(h - 28, n.y + n.vy));
    }
  }
  settleTicks += 1;
}
function linkedNodeIds() {
  const linked = new Set();
  if (selectedId) {
    linked.add(selectedId);
    for (const e of edges) {
      if (e.source === selectedId) linked.add(e.target);
      if (e.target === selectedId) linked.add(e.source);
    }
  }
  return linked;
}
function relationCounts() {
  const counts = new Map();
  for (const e of edges) {
    counts.set(e.source, (counts.get(e.source) || 0) + 1);
    counts.set(e.target, (counts.get(e.target) || 0) + 1);
  }
  return counts;
}
function labelNodeIds(linked) {
  const labels = new Set();
  const counts = relationCounts();
  const byImportance = (a, b) => {
    const aScore = (a.kind === 'entity' ? a.mentions || 0 : counts.get(a.id) || 0);
    const bScore = (b.kind === 'entity' ? b.mentions || 0 : counts.get(b.id) || 0);
    return bScore - aScore;
  };
  if (showAllLabels) {
    const candidates = PERF.largeGraph
      ? [...nodes].sort(byImportance).slice(0, PERF.allLabelBudget)
      : nodes.length <= PERF.allLabelNodeLimit
        ? nodes
        : [...nodes].sort(byImportance).slice(0, PERF.allLabelBudget);
    for (const n of candidates) labels.add(n.id);
  }
  if (selectedId) labels.add(selectedId);
  const neighbors = nodes
    .filter(n => n.id !== selectedId && linked.has(n.id))
    .sort(byImportance)
    .slice(0, PERF.neighborLabelBudget);
  for (const n of neighbors) labels.add(n.id);
  return labels;
}
function updateGraphDom() {
  const linked = linkedNodeIds();
  const labels = labelNodeIds(linked);
  const byId = new Map(nodes.map(n => [n.id, n]));
  for (const item of edgeEls) {
    const e = item.edge;
    const a = byId.get(e.source), b = byId.get(e.target);
    if (!a || !b) continue;
    item.el.setAttribute('x1', a.x); item.el.setAttribute('y1', a.y);
    item.el.setAttribute('x2', b.x); item.el.setAttribute('y2', b.y);
    const active = selectedId && (e.source === selectedId || e.target === selectedId);
    item.el.setAttribute('class', 'edge ' + item.edgeClass + (active ? ' active' : '') + (selectedId && !linked.has(e.source) && !linked.has(e.target) ? ' dim' : ''));
  }
  for (const n of nodes) {
    const g = nodeEls.get(n.id);
    if (!g) continue;
    const labelClass = labels.has(n.id) ? ' show-label' : '';
    const neighborClass = selectedId !== n.id && linked.has(n.id) ? ' neighbor' : '';
    g.setAttribute('class', 'node ' + n.kind + labelClass + neighborClass + (selectedId === n.id ? ' selected' : '') + (selectedId && !linked.has(n.id) ? ' dim' : ''));
    g.setAttribute('transform', `translate(${n.x},${n.y})`);
    layoutCache.set(n.id, { x: n.x, y: n.y });
  }
}
function renderFrame() {
  if (settleTicks < PERF.settleLimit || dragging) tick();
  updateGraphDom();
  if (settleTicks < PERF.settleLimit || dragging) {
    raf = requestAnimationFrame(renderFrame);
  } else {
    raf = null;
  }
}
function startAnimation() {
  if (raf) cancelAnimationFrame(raf);
  raf = requestAnimationFrame(renderFrame);
}
function renderStatic() {
  if (raf) cancelAnimationFrame(raf);
  raf = null;
  updateGraphDom();
}
function selectNode(id) {
  selectedId = id;
  showDetails();
  renderNodeList();
  renderStatic();
}
function startDrag(event, id) {
  const node = nodes.find(n => n.id === id);
  if (!node) return;
  dragging = { id, dx: node.x - event.clientX, dy: node.y - event.clientY };
  node.fixed = true;
  svg.setPointerCapture(event.pointerId);
  startAnimation();
}
svg.addEventListener('pointermove', event => {
  if (!dragging) return;
  const node = nodes.find(n => n.id === dragging.id);
  if (!node) return;
  const rect = svg.getBoundingClientRect();
  node.x = Math.max(28, Math.min(rect.width - 28, event.clientX + dragging.dx));
  node.y = Math.max(62, Math.min(rect.height - 28, event.clientY + dragging.dy));
  node.vx = 0;
  node.vy = 0;
  renderStatic();
});
svg.addEventListener('pointerup', () => {
  dragging = null;
  startAnimation();
});
svg.addEventListener('pointerleave', () => {
  dragging = null;
  startAnimation();
});
function showDetails() {
  const node = DATA.nodes.find(n => n.id === selectedId) || DATA.nodes[0];
  if (!node) return;
  const rels = DATA.edges.filter(e => e.source === node.id || e.target === node.id).map(e => {
    const otherId = e.source === node.id ? e.target : e.source;
    const other = DATA.nodes.find(n => n.id === otherId);
    return `<div class="rel-item"><strong>${escapeHtml(e.kind)}</strong><span>${escapeHtml(other ? other.label : otherId)}</span></div>`;
  }).join('') || '<p class="empty">No direct relations.</p>';
  if (node.kind === 'section') {
    details.innerHTML = `<div class="details-head"><h2>${escapeHtml(node.label)}</h2><div class="meta"><span class="pill">section</span><span class="pill">level ${node.level}</span></div></div><div class="details-section"><h3>Path</h3><p>${escapeHtml(node.path || '')}</p></div><div class="details-section"><h3>Gist</h3><p>${escapeHtml(node.gist || '')}</p></div><div class="details-section"><h3>Synopsis</h3><p>${escapeHtml(node.synopsis || '')}</p></div><div class="details-section"><h3>Head</h3><p>${escapeHtml(node.head || '')}</p></div><div class="details-section"><h3>Relations</h3><div class="rel-list">${rels}</div></div>`;
  } else {
    details.innerHTML = `<div class="details-head"><h2>${escapeHtml(node.label)}</h2><div class="meta"><span class="pill">entity</span><span class="pill">${escapeHtml(node.entityKind || '')}</span><span class="pill">${node.mentions || 0} mentions</span></div></div><div class="details-section"><h3>Surface Forms</h3><p>${escapeHtml((node.surfaceForms || []).join(', '))}</p></div><div class="details-section"><h3>Relations</h3><div class="rel-list">${rels}</div></div>`;
  }
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}
function drawStats() {
  document.getElementById('doc').textContent = DATA.docId;
  document.getElementById('stats').innerHTML = [
    ['Sections', DATA.stats.sections],
    ['Entities', DATA.stats.entitiesShown + '/' + DATA.stats.entities],
    ['Relations', DATA.stats.edges],
    ['Depth', DATA.stats.maxDepth],
  ].map(([label, value]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`).join('');
}
function renderNodeList() {
  const q = search.value.trim().toLowerCase();
  const visible = new Set(nodes.map(n => n.id));
  const relCount = new Map();
  for (const e of DATA.edges) {
    relCount.set(e.source, (relCount.get(e.source) || 0) + 1);
    relCount.set(e.target, (relCount.get(e.target) || 0) + 1);
  }
  const rows = DATA.nodes
    .filter(n => visible.has(n.id))
    .sort((a, b) => (b.kind === 'entity' ? b.mentions || 0 : relCount.get(b.id) || 0) - (a.kind === 'entity' ? a.mentions || 0 : relCount.get(a.id) || 0))
    .slice(0, 80)
    .map(n => {
      const meta = n.kind === 'entity' ? `${escapeHtml(n.entityKind || 'entity')} - ${n.mentions || 0} mentions` : `level ${n.level || 0} - ${relCount.get(n.id) || 0} relations`;
      return `<div class="row ${selectedId === n.id ? 'active' : ''}" data-id="${escapeHtml(n.id)}"><div class="row-title">${escapeHtml(n.label)}</div><div class="row-meta">${meta}</div></div>`;
    });
  nodeList.innerHTML = rows.join('') || `<p class="empty">${q ? 'No matches.' : 'No visible nodes.'}</p>`;
  nodeList.querySelectorAll('.row').forEach(row => row.addEventListener('click', () => selectNode(row.dataset.id)));
}
function updateStatus() {
  const edgeText = clippedEdgeCount > 0 ? `${edges.length}/${untrimmedEdgeCount} edges` : `${edges.length} edges`;
  statusEl.textContent = `${nodes.length} nodes - ${edgeText}`;
}
function reset() {
  if (raf) cancelAnimationFrame(raf);
  initLayout();
  buildGraphDom();
  const q = search.value.trim().toLowerCase();
  const directMatch = q ? nodes.find(n => nodeSearchText(n).includes(q)) : null;
  if (directMatch) {
    selectedId = directMatch.id;
  } else if (!nodes.some(n => n.id === selectedId)) {
    selectedId = nodes[0] ? nodes[0].id : null;
  }
  showDetails();
  renderNodeList();
  startAnimation();
}
document.querySelectorAll('button[data-mode]').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('button[data-mode]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  mode = btn.dataset.mode;
  reset();
}));
search.addEventListener('input', reset);
document.getElementById('fit').addEventListener('click', reset);
document.getElementById('stabilize').addEventListener('click', () => {
  for (let i = 0; i < PERF.stabilizeTicks; i++) tick();
  settleTicks = PERF.settleLimit;
  renderStatic();
});
document.getElementById('labels').addEventListener('click', event => {
  showAllLabels = !showAllLabels;
  event.currentTarget.classList.toggle('active', showAllLabels);
  renderStatic();
});
window.addEventListener('resize', reset);
document.getElementById('labels').classList.toggle('active', showAllLabels);
drawStats();
reset();
</script>
</body>
</html>
"""
    return template.replace("__DOC_TITLE__", title).replace("__DATA__", data_json)
