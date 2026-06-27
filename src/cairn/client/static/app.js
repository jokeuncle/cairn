const stages = [
  ['连接', '接入企业知识源', '文档、Wiki、PDF、Office、API 与 OCR 结果进入本地工作台。'],
  ['清洗', '清理无效内容', '去掉页眉页脚、重复声明、乱码和低价值片段。'],
  ['结构', '还原原文结构', '保留标题、表格、列表、页码、章节路径和引用位置。'],
  ['单元', '生成知识单元', '按语义完整性切分，避免条款、表格和章节被切散。'],
  ['治理', '补齐业务标签', '绑定业务域、密级、权限、来源、版本和负责人。'],
  ['增强', '增强可搜索性', '生成摘要、关键词、实体、术语映射和潜在问题。'],
  ['建图', '建立 Cairn DocsGraph', '生成 Tree、Summaries、Entities、XRefs 和 Vectors。'],
  ['门禁', '上线前质量门禁', '检查异常块、重复内容、增量更新和黄金集回归。'],
];

const views = [
  ['sources', '知识源', '接入策略与文档状态'],
  ['runs', '摄入运行', '同步、失败和增量影响'],
  ['graph', '知识图谱', 'Cairn 结构与上下文包'],
  ['publish', '本地分发', '安装到 AI 客户端'],
];

const clients = [
  ['codex', 'Codex', '写入 ~/.codex/config.toml'],
  ['claude', 'Claude', '写入 Claude Desktop MCP 配置'],
  ['cursor', 'Cursor', '写入 ~/.cursor/mcp.json'],
  ['goose', 'Goose', '写入 ~/.config/goose/config.yaml'],
];

const state = {
  view: 'sources',
  snapshot: null,
  loading: '',
  notice: '',
  error: '',
  lastRun: null,
  context: null,
  graph: null,
  mcpPreview: null,
  activeClient: 'codex',
  fixedRepo: true,
  fake: true,
  markitdown: false,
  query: '如何把公司知识库分发给本地 AI 客户端并保留可验证引用？',
};

const app = document.querySelector('#app');

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json();
  if (!payload.ok) {
    const message = payload.error?.message || payload.error || '请求失败';
    throw new Error(message);
  }
  return payload.data;
}

async function loadSnapshot() {
  state.loading = 'snapshot';
  render();
  try {
    state.snapshot = await api('/api/snapshot');
    state.error = '';
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = '';
    render();
  }
}

async function initRepo() {
  state.loading = 'init';
  state.error = '';
  render();
  try {
    const data = await api('/api/init', {
      method: 'POST',
      body: JSON.stringify({ markitdown: state.markitdown }),
    });
    state.snapshot = data.snapshot;
    state.notice = `已初始化 ${data.config_path}`;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = '';
    render();
  }
}

async function runSync(force = false) {
  state.loading = 'sync';
  state.error = '';
  render();
  try {
    const data = await api('/api/sync', {
      method: 'POST',
      body: JSON.stringify({ fake: state.fake, force }),
    });
    state.lastRun = data;
    state.snapshot = data.snapshot;
    state.notice = `同步完成：${data.summary.rebuilt} rebuilt, ${data.summary.skipped} skipped`;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = '';
    render();
  }
}

async function runContext() {
  const query = state.query.trim();
  if (!query) return;
  state.loading = 'context';
  state.error = '';
  render();
  try {
    state.context = await api(`/api/context?query=${encodeURIComponent(query)}&fake=${state.fake}`);
    state.notice = `已生成 ${state.context.context_sections?.length || 0} 段任务上下文`;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = '';
    render();
  }
}

async function loadGraph() {
  state.loading = 'graph';
  state.error = '';
  render();
  try {
    state.graph = await api('/api/graph');
    state.notice = `图谱载入：${state.graph.stats?.sections || 0} sections`;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = '';
    render();
  }
}

async function refreshMcpPreview() {
  const fixed = state.fixedRepo ? 'true' : 'false';
  try {
    state.mcpPreview = await api(`/api/mcp/config?client=${state.activeClient}&fake=${state.fake}&fixed_repo=${fixed}`);
    render();
  } catch (error) {
    state.error = error.message;
    render();
  }
}

async function installClient() {
  const selected = clients.find(([id]) => id === state.activeClient);
  const confirmed = window.confirm(`安装 Cairn MCP 到 ${selected?.[1] || state.activeClient}？这会写入本机客户端配置文件。`);
  if (!confirmed) return;
  state.loading = 'install';
  state.error = '';
  render();
  try {
    const data = await api('/api/mcp/install', {
      method: 'POST',
      body: JSON.stringify({
        client: state.activeClient,
        fake: state.fake,
        fixed_repo: state.fixedRepo,
        force: true,
      }),
    });
    state.notice = `已安装到 ${data.target}`;
    await loadSnapshot();
  } catch (error) {
    state.error = error.message;
    state.loading = '';
    render();
  }
}

function render() {
  const snap = state.snapshot;
  const configured = snap?.repo?.configured;
  const status = snap?.status;
  const counts = status?.counts || {};
  const readiness = status?.readiness ?? 0;

  app.innerHTML = `
    <div class="shell">
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">AI</div>
          <div>
            <h1>AI.Knowledge Client</h1>
            <p>由 Cairn 驱动的本地企业知识摄入与分发工作台</p>
          </div>
        </div>
        <div class="repo-strip">
          <span class="status-dot ${configured ? 'ok' : ''}"></span>
          <div>
            <strong>${configured ? 'Repo ready' : 'Needs init'}</strong>
            <span title="${escapeHtml(snap?.repo?.root || '')}">${escapeHtml(shortPath(snap?.repo?.root || '正在连接...'))}</span>
          </div>
        </div>
        <div class="top-actions">
          <label class="toggle">
            <input id="fake-toggle" type="checkbox" ${state.fake ? 'checked' : ''} />
            <span>离线模式</span>
          </label>
          <button class="ghost" id="refresh-btn" type="button">刷新</button>
          <button class="primary" id="top-sync-btn" type="button" ${!configured ? 'disabled' : ''}>同步</button>
        </div>
      </header>

      ${banner()}

      <main class="workspace">
        <aside class="rail">
          <div class="readiness">
            <span>Knowledge readiness</span>
            <strong>${readiness}%</strong>
            <div class="bar"><i style="width:${readiness}%"></i></div>
            <small>${counts.indexed || 0} indexed / ${counts.total || 0} sources</small>
          </div>
          <nav>
            ${views.map(([id, label, hint]) => `
              <button class="nav-item ${state.view === id ? 'active' : ''}" data-view="${id}" type="button">
                <b>${label}</b>
                <span>${hint}</span>
              </button>
            `).join('')}
          </nav>
          <div class="doctor">
            <h2>运行检查</h2>
            ${doctorChecks()}
          </div>
        </aside>

        <section class="panel">
          ${!snap ? loadingSplash() : !configured ? initView() : activeView()}
        </section>
      </main>
    </div>
  `;

  bindActions();
}

function banner() {
  if (state.error) {
    return `<div class="banner error">${escapeHtml(state.error)}</div>`;
  }
  if (state.notice) {
    return `<div class="banner">${escapeHtml(state.notice)}</div>`;
  }
  return '';
}

function activeView() {
  if (state.view === 'runs') return runsView();
  if (state.view === 'graph') return graphView();
  if (state.view === 'publish') return publishView();
  return sourcesView();
}

function initView() {
  return `
    <section class="empty-state">
      <p class="eyebrow">first run</p>
      <h2>把当前目录变成可被 AI 客户端使用的知识库</h2>
      <p>Cairn 会创建 .cairn/config.toml，发现 README、docs、Markdown 和 PDF，并在本地生成结构化 DocsGraph。</p>
      <label class="check">
        <input id="markitdown-toggle" type="checkbox" ${state.markitdown ? 'checked' : ''} />
        <span>启用 Office / HTML / 表格等 MarkItDown 接入策略</span>
      </label>
      <div class="action-row">
        <button class="primary large" id="init-btn" type="button">${state.loading === 'init' ? '初始化中...' : '初始化知识策略'}</button>
      </div>
    </section>
  `;
}

function sourcesView() {
  const snap = state.snapshot;
  const cfg = snap.config;
  const docs = snap.status?.documents || [];
  return `
    <div class="view-head">
      <div>
        <p class="eyebrow">source policy</p>
        <h2>知识源接入与治理</h2>
        <p>客户需要看到的不是底层 parser，而是“哪些材料会进知识库、哪些被排除、当前能否发布”。</p>
      </div>
      <button class="primary" id="sync-btn" type="button">${state.loading === 'sync' ? '同步中...' : '运行同步'}</button>
    </div>

    <div class="stat-grid">
      ${statCard('已索引', snap.status.counts.indexed, '可被 AI 检索的文档')}
      ${statCard('需更新', snap.status.counts.stale, '源文件变化后待重建')}
      ${statCard('缺失', snap.status.counts.missing, '已发现但尚未建索引')}
      ${statCard('错误', snap.status.counts.errors, '需要人工处理')}
    </div>

    <div class="split">
      <section class="surface">
        <div class="section-title">
          <h3>接入策略</h3>
          <span>${cfg.enable_markitdown ? 'MarkItDown on' : 'native parsers'}</span>
        </div>
        <div class="policy-list">
          <div>
            <strong>include</strong>
            ${cfg.include.map(item => `<code>${escapeHtml(item)}</code>`).join('')}
          </div>
          <div>
            <strong>exclude</strong>
            ${cfg.exclude.slice(0, 9).map(item => `<code>${escapeHtml(item)}</code>`).join('')}
          </div>
        </div>
      </section>

      <section class="surface">
        <div class="section-title">
          <h3>文档队列</h3>
          <span>${docs.length} sources</span>
        </div>
        <div class="doc-list">
          ${docs.map(docRow).join('')}
        </div>
      </section>
    </div>
  `;
}

function runsView() {
  const run = state.lastRun;
  return `
    <div class="view-head">
      <div>
        <p class="eyebrow">ingestion run</p>
        <h2>摄入链路可观察、可重跑</h2>
        <p>每次同步都能看到发现、解析、建图、跳过和失败结果，便于客户把知识运营变成稳定流程。</p>
      </div>
      <div class="action-row">
        <button class="ghost" id="force-sync-btn" type="button">强制重建</button>
        <button class="primary" id="sync-btn" type="button">${state.loading === 'sync' ? '同步中...' : '同步增量'}</button>
      </div>
    </div>

    <div class="stage-grid">
      ${stages.map((stage, index) => stageCard(stage, index)).join('')}
    </div>

    <section class="surface run-output">
      <div class="section-title">
        <h3>最近一次运行</h3>
        ${run ? `<span>${run.summary.total} docs</span>` : '<span>not started</span>'}
      </div>
      ${run ? `
        <div class="run-summary">
          ${statCard('rebuilt', run.summary.rebuilt, '重新生成 Cairn 索引')}
          ${statCard('skipped', run.summary.skipped, '源文件未变化')}
          ${statCard('failed', run.summary.failed, '失败文档')}
        </div>
        <div class="terminal">${run.progress.map(line => `<p>${escapeHtml(line)}</p>`).join('')}</div>
      ` : `
        <p class="muted">还没有运行记录。点击“同步增量”后，这里会展示 Cairn 的真实同步日志。</p>
      `}
    </section>
  `;
}

function graphView() {
  const ctx = state.context;
  return `
    <div class="view-head">
      <div>
        <p class="eyebrow">docsgraph</p>
        <h2>查看 Cairn 给 AI 的真实上下文</h2>
        <p>客户可以验证：AI 会拿到哪些 section、为什么命中、引用在哪里、关系图补充了什么。</p>
      </div>
      <button class="ghost" id="load-graph-btn" type="button">${state.loading === 'graph' ? '载入中...' : '载入图谱'}</button>
    </div>

    <section class="query-panel">
      <input id="query-input" value="${escapeAttr(state.query)}" />
      <button class="primary" id="query-btn" type="button">${state.loading === 'context' ? '生成中...' : '生成任务上下文'}</button>
    </section>

    <div class="split graph-split">
      <section class="surface">
        <div class="section-title">
          <h3>Cairn 核心图谱</h3>
          <span>${graphStats()}</span>
        </div>
        ${graphMap()}
      </section>

      <section class="surface">
        <div class="section-title">
          <h3>上下文包</h3>
          <span>${ctx?.context_sections?.length || 0} sections</span>
        </div>
        ${ctx ? contextResults(ctx) : '<p class="muted">输入任务问题后，客户端会调用 repo_context 生成可直接交给 Agent 的上下文包。</p>'}
      </section>
    </div>
  `;
}

function publishView() {
  const snap = state.snapshot;
  const fallback = snap.publish.clients.find(item => item.client === state.activeClient) || snap.publish.clients[0];
  const selected = state.mcpPreview?.client === state.activeClient ? state.mcpPreview : fallback;
  return `
    <div class="view-head">
      <div>
        <p class="eyebrow">local distribution</p>
        <h2>一键分发到本地 AI 客户端</h2>
        <p>把公司知识库作为 Cairn MCP server 暴露给 Codex、Claude、Cursor 或 Goose，AI 客户端按需获取可追溯上下文。</p>
      </div>
      <button class="primary" id="install-btn" type="button">${state.loading === 'install' ? '安装中...' : '安装到客户端'}</button>
    </div>

    <div class="client-grid">
      ${clients.map(([id, name, hint]) => `
        <button class="client-card ${state.activeClient === id ? 'active' : ''}" data-client="${id}" type="button">
          <strong>${name}</strong>
          <span>${hint}</span>
        </button>
      `).join('')}
    </div>

    <div class="split">
      <section class="surface">
        <div class="section-title">
          <h3>发布策略</h3>
          <span>${state.fixedRepo ? 'fixed repo' : 'dynamic workspace'}</span>
        </div>
        <label class="check">
          <input id="fixed-toggle" type="checkbox" ${state.fixedRepo ? 'checked' : ''} />
          <span>绑定当前知识库路径，适合公司统一知识包</span>
        </label>
        <label class="check">
          <input id="fake-toggle-inner" type="checkbox" ${state.fake ? 'checked' : ''} />
          <span>分发离线演示配置，适合 smoke test 和培训</span>
        </label>
        <div class="publish-steps">
          <p><b>1</b> 安装 MCP 配置</p>
          <p><b>2</b> 客户端启动 docsgraph serve</p>
          <p><b>3</b> Agent 调用 repo_context / get_section</p>
          <p><b>4</b> 答案携带 cairn:// 引用回溯</p>
        </div>
      </section>

      <section class="surface">
        <div class="section-title">
          <h3>${selected.client} 配置预览</h3>
          <span>${escapeHtml(shortPath(selected.target))}</span>
        </div>
        <pre class="config-block">${escapeHtml(selected.config)}</pre>
      </section>
    </div>
  `;
}

function doctorChecks() {
  const checks = state.snapshot?.doctor?.checks || [];
  if (!checks.length) return '<p class="muted">等待客户端连接。</p>';
  return checks.map(check => `
    <div class="doctor-row">
      <span class="${check.ok ? 'ok' : ''}"></span>
      <div>
        <strong>${escapeHtml(check.label || check.name)}</strong>
        <p>${escapeHtml(check.message || '')}</p>
      </div>
    </div>
  `).join('');
}

function loadingSplash() {
  return `
    <section class="empty-state">
      <p class="eyebrow">connecting</p>
      <h2>正在连接本地 Cairn 客户端</h2>
      <p>客户端会读取当前目录的 .cairn 状态，并展示可操作的知识摄入链路。</p>
    </section>
  `;
}

function statCard(label, value, hint) {
  return `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${value ?? 0}</strong>
      <p>${escapeHtml(hint)}</p>
    </article>
  `;
}

function docRow(doc) {
  return `
    <article class="doc-row">
      <span class="state ${doc.state}">${escapeHtml(doc.state)}</span>
      <div>
        <strong>${escapeHtml(doc.id)}</strong>
        <p>${escapeHtml(doc.source)}</p>
      </div>
      <em>${doc.section_count ?? '-'}</em>
    </article>
  `;
}

function stageCard(stage, index) {
  const hot = index >= 2 && index <= 6;
  return `
    <article class="stage-card ${hot ? 'hot' : ''}">
      <span>${String(index + 1).padStart(2, '0')} / ${stage[0]}</span>
      <h3>${stage[1]}</h3>
      <p>${stage[2]}</p>
    </article>
  `;
}

function graphStats() {
  const stats = state.graph?.stats;
  if (!stats) return 'not loaded';
  return `${stats.documents || 0} docs / ${stats.sections || 0} sections / ${stats.entities || 0} entities`;
}

function graphMap() {
  const labels = [
    ['Tree', '章节路径'],
    ['Summaries', '多级摘要'],
    ['Entities', '业务实体'],
    ['XRefs', '引用关系'],
    ['Vectors', '语义召回'],
    ['MCP', 'AI 工具'],
  ];
  return `
    <div class="graph-map">
      <div class="map-center">Cairn<br /><span>DocsGraph</span></div>
      ${labels.map((item, index) => `<div class="map-node n${index}"><strong>${item[0]}</strong><span>${item[1]}</span></div>`).join('')}
      <svg viewBox="0 0 520 300" aria-hidden="true">
        <path d="M260 150 C210 72 156 54 92 64" />
        <path d="M260 150 C278 74 338 42 428 70" />
        <path d="M260 150 C350 134 420 152 470 210" />
        <path d="M260 150 C282 230 342 266 426 250" />
        <path d="M260 150 C192 224 142 252 76 232" />
        <path d="M260 150 C172 136 104 140 52 164" />
      </svg>
    </div>
  `;
}

function contextResults(ctx) {
  const sections = ctx.context_sections || [];
  return `
    <div class="context-list">
      ${sections.map(section => `
        <article class="context-item">
          <div>
            <strong>${escapeHtml(section.title)}</strong>
            <span>${escapeHtml(section.doc)} / ${escapeHtml(section.id)}</span>
          </div>
          <p>${escapeHtml(trim(section.content || '', 360))}</p>
          <code>${escapeHtml(section.anchor)}</code>
        </article>
      `).join('')}
    </div>
  `;
}

function bindActions() {
  document.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => {
      state.view = button.dataset.view;
      state.notice = '';
      if (state.view === 'graph' && !state.graph && state.snapshot?.repo?.configured) {
        loadGraph();
      } else if (state.view === 'publish' && state.snapshot?.repo?.configured) {
        refreshMcpPreview();
      } else {
        render();
      }
    });
  });

  document.querySelector('#refresh-btn')?.addEventListener('click', loadSnapshot);
  document.querySelector('#top-sync-btn')?.addEventListener('click', () => runSync(false));
  document.querySelector('#sync-btn')?.addEventListener('click', () => runSync(false));
  document.querySelector('#force-sync-btn')?.addEventListener('click', () => runSync(true));
  document.querySelector('#init-btn')?.addEventListener('click', initRepo);
  document.querySelector('#query-btn')?.addEventListener('click', runContext);
  document.querySelector('#load-graph-btn')?.addEventListener('click', loadGraph);
  document.querySelector('#install-btn')?.addEventListener('click', installClient);

  document.querySelector('#query-input')?.addEventListener('input', event => {
    state.query = event.target.value;
  });
  document.querySelector('#fake-toggle')?.addEventListener('change', event => {
    state.fake = event.target.checked;
    state.mcpPreview = null;
    loadSnapshot();
  });
  document.querySelector('#fake-toggle-inner')?.addEventListener('change', event => {
    state.fake = event.target.checked;
    state.mcpPreview = null;
    refreshMcpPreview();
  });
  document.querySelector('#markitdown-toggle')?.addEventListener('change', event => {
    state.markitdown = event.target.checked;
  });
  document.querySelector('#fixed-toggle')?.addEventListener('change', event => {
    state.fixedRepo = event.target.checked;
    refreshMcpPreview();
  });
  document.querySelectorAll('[data-client]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeClient = button.dataset.client;
      refreshMcpPreview();
    });
  });
}

function shortPath(path) {
  if (!path) return '';
  const parts = path.split('/');
  if (parts.length <= 4) return path;
  return `.../${parts.slice(-3).join('/')}`;
}

function trim(value, max) {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('\n', ' ');
}

loadSnapshot();
