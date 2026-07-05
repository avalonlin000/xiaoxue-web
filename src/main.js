/* ==========================================================
   小雪工作台 · main.js v6 — 对话驱动
   ========================================================== */

const API = (path, opts) => fetch('/api' + path, opts).then(r => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
});

// ─── State ───────────────────────────────────────
const state = {
  team: null,
  teams: [],
  _3d: null,
  dirty: false,
  tradeGame: 'lol',
  trades: [],
  page: 'fundamentals',
  fundScope: 'msi',
};

// ─── Clock ───────────────────────────────────────
function tick() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  document.getElementById('clock').textContent = p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}
tick();
setInterval(tick, 1000);

// ─── Init ───────────────────────────────────────
async function init() {
  state.teams = await API('/teams');
  // Auto-select first team or use saved
  if (state.teams.length > 0) {
    await selectTeam(state.teams[0].short_name);
  }
  setPage('fundamentals');
  loadFundamentals('msi');
  loadDailyContent();
  loadTrades();
}
init();

// ─── Team Selection ────────────────────────────
async function selectTeam(code) {
  if (state.team === code) return;
  state.team = code;
  state.dirty = false;
  updateTopBar();
  showContent();

  // Load everything in parallel
  try {
    const [profile, wiki, d3] = await Promise.all([
      API('/profile-full/' + code).catch(() => ({ found: false, html: '' })),
      API('/wiki/team/' + code).catch(() => ({ found: false, html: '' })),
      API('/team-3d/' + code).catch(() => null),
    ]);

    state._3d = d3;
    renderProfile(wiki && wiki.found ? { ...wiki, source: 'wiki' } : profile);
    render3D(d3);
    // Auto-search TK with team name
    searchTK(code);
  } catch (e) {
    console.error('Load error:', e);
  }
}

function updateTopBar() {
  document.getElementById('sel-team-label').textContent = state.team || '选择队伍…';
  document.getElementById('sel-team-code').textContent = state.team ? state.team : '';
  const display = state.team ? 'flex' : 'none';
  document.getElementById('btn-graph').style.display = display;
  document.getElementById('btn-analyst').style.display = display;
}

function showContent() {
  document.getElementById('empty-state').style.display = 'none';
  const ca = document.getElementById('content-area');
  ca.style.display = 'flex';
  ca.classList.toggle('page-fundamentals', state.page === 'fundamentals');
  ca.classList.toggle('page-market', state.page === 'market');
}

function setPage(page) {
  state.page = page === 'market' ? 'market' : 'fundamentals';
  document.querySelectorAll('.workspace-tab').forEach(btn => btn.classList.remove('active'));
  document.getElementById('tab-' + state.page)?.classList.add('active');
  showContent();
  if (state.page === 'market') loadTrades();
  if (state.page === 'fundamentals') loadFundamentals(state.fundScope || 'msi');
}

async function loadFundamentals(scope = 'msi') {
  state.fundScope = scope;
  document.querySelectorAll('.scope-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.scope === scope));
  const table = document.getElementById('fundamentals-table');
  if (table) table.innerHTML = '<div class="tk-empty">加载横向基本面中…</div>';
  try {
    const [teamsData, msiData] = await Promise.all([
      API('/fundamentals/teams?scope=' + encodeURIComponent(scope) + '&limit=80'),
      API('/fundamentals/msi').catch(() => null),
    ]);
    if (msiData) renderMsiSummary(msiData);
    renderFundamentalsTable(teamsData.teams || []);
  } catch (e) {
    if (table) table.innerHTML = '<div class="tk-empty" style="color:var(--red)">横向基本面加载失败</div>';
  }
}

async function loadDailyContent() {
  const status = document.getElementById('today-content-status');
  try {
    const data = await API('/daily-content');
    const items = data.items || [];
    items.forEach(renderDailyContentItem);
    if (status) status.textContent = `2026-07-05 MSI 日报、赛前卡、分析师入口可见层；已读取 /api/daily-content（${items.length} 个白名单文件）`;
  } catch (e) {
    console.warn('daily content API failed, keeping static fallback:', e);
    if (status) status.textContent = '2026-07-05 MSI 日报、赛前卡、分析师入口可见层；/api/daily-content 失败，保留静态 fallback';
  }
}

function renderDailyContentItem(item) {
  const el = document.querySelector(`[data-content-id="${escAttr(item.id || '')}"]`);
  if (!el) return;
  el.classList.toggle('exists', !!item.exists);
  el.classList.toggle('missing', !item.exists);
  const title = el.querySelector('b');
  const summary = el.querySelector('.today-summary');
  const meta = el.querySelector('.today-meta');
  const path = el.querySelector('.today-path');
  if (title && item.title) title.textContent = item.title;
  if (summary && item.summary) summary.textContent = item.summary;
  if (meta) {
    meta.textContent = item.exists
      ? `已读取本地文件 · 更新时间 ${item.updated_at || '-'} · ${item.size_bytes || 0} bytes`
      : '本地文件不存在；当前显示静态 fallback 文案';
  }
  if (path && item.path) path.textContent = item.path;
}

function renderMsiSummary(data) {
  const el = document.getElementById('msi-summary');
  if (!el) return;
  const teamCount = (data.teams || []).length;
  const missing = (data.missing_profiles || []).length + (data.missing_3d || []).length;
  const regionText = Object.entries(data.regions || {}).map(([k, v]) => `${k}:${v}`).join(' · ') || '暂无';
  el.innerHTML = `
    <div class="fund-tile"><b>${teamCount}</b><span>MSI 队伍池</span></div>
    <div class="fund-tile"><b>${missing}</b><span>资料缺口（画像/三维）</span></div>
    <div class="fund-tile"><b>MSI</b><span>${escHtml(regionText)} · 国际赛环境研究</span></div>`;
}

function toggleGraphEmbed() {
  const el = document.getElementById('graph-embed');
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function renderFundamentalsTable(rows) {
  const el = document.getElementById('fundamentals-table');
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = '<div class="tk-empty">暂无横向基本面数据</div>';
    return;
  }
  const head = `<div class="fund-row fund-head"><span>队伍</span><span>赛区</span><span>赔率</span><span>mu</span><span>σ</span><span>TS</span><span>版本/风格摘要</span><span>首发/关键选手</span><span>资料</span></div>`;
  const body = rows.map(t => {
    const q = t.data_quality === '完整' ? 'good' : (t.data_quality === '部分' ? 'mid' : 'low');
    const summary = t.version_summary || t.notes_summary || '暂无摘要，待补画像/TK';
    const mu = Number(t.seed_mu ?? t.mu ?? 0).toFixed(1);
    const sigma = Number(t.seed_sigma ?? t.sigma ?? 0).toFixed(1);
    const ts = Number(t.seed_ts ?? t.ts_score ?? 0).toFixed(1);
    const odds = t.odds ? Number(t.odds).toFixed(1) : '-';
    const players = renderPlayerCards(t.players || [], t.players_note);
    return `<div class="fund-row" onclick="selectTeam('${escAttr(t.short_name)}')">
      <span class="fund-team">${escHtml(t.short_name)}</span>
      <span>${escHtml(t.region || '-')}</span>
      <span>${escHtml(odds)}</span>
      <span>${escHtml(mu)}</span>
      <span>${escHtml(sigma)}</span>
      <span>${escHtml(ts)}</span>
      <span>${escHtml(summary)}</span>
      <span class="player-cards">${players}</span>
      <span class="quality ${q}">${escHtml(t.data_quality || '资料不足')}</span>
    </div>`;
  }).join('');
  el.innerHTML = head + body;
}

function renderPlayerCards(players, note) {
  if (!players.length) {
    return `<span class="player-card gap">${escHtml(note || '资料缺口/暂无数据')}</span>`;
  }
  return players.map(p => {
    const role = p.role || '位置暂无数据';
    const name = p.name || '暂无数据';
    const status = p.status || '资料缺口';
    return `<span class="player-card" title="${escAttr(status)}"><b>${escHtml(role)}</b>${escHtml(name)}</span>`;
  }).join('');
}

function generateAnalystPrompt() {
  setPage('fundamentals');
  const input = document.getElementById('analyst-bp-input');
  const output = document.getElementById('analyst-output');
  if (!output) return;
  const raw = (input?.value || '').trim();
  const lineup = raw || '未粘贴 BP/阵容，先补：蓝色方 / 红色方 / 五个位置 / 关键 ban pick。';
  const teamLine = state.team ? `当前选择队伍：${state.team}` : '当前选择队伍：未选择';
  const normalized = normalizeLineupText(lineup);
  output.textContent = [
    '【复制这段去问小雪/分析师】',
    '',
    '请按小雪单场分析框架处理这场 BP/阵容，不要直接下交易结论，先补齐判断链：',
    '',
    '1. 阵容确认',
    teamLine,
    normalized,
    '',
    '2. 控制量化待算',
    '- 硬控 / 软控 / 开团 / 反开 / 留人 / 保护分别列数。',
    '- 标出关键控制链是否稳定、是否依赖闪现或先手视野。',
    '',
    '3. 基本面/TS待带入',
    '- 带入两队 mu / σ / TS / risk_gap / 样本置信度。',
    '- 对照当前版本理解、队伍风格和 BO 场景。',
    '',
    '4. 线权时间边界待判断',
    '- 1-6级、首巢虫/小龙、14分钟前镀层、一先锋/二龙团分别判断线权。',
    '- 写清哪一路是阵容发动机，哪一路只要不炸就行。',
    '',
    '5. 核心链/24场景待定位',
    '- 定位主要赢法：开团链、单带链、poke/消耗链、保护后排链或前中期滚雪球链。',
    '- 拆 2-4 个关键场景：一级设计、第一波资源团、中期转线、远古资源团。',
    '',
    '明确：复制这段去问小雪/分析师；本页面只整理提示，不调用 LLM、不保存。',
  ].join('\n');
  document.getElementById('card-analyst')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function normalizeLineupText(text) {
  return text
    .replace(/；/g, '\n')
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => `- ${s}`)
    .join('\n');
}

async function loadAnalyst(analyst = '中年电竞人') {
  if (!state.team) return;
  setPage('fundamentals');
  const output = document.getElementById('analyst-output');
  if (!output) return;
  const url = '/analyst/' + encodeURIComponent(state.team) + '?analyst=' + encodeURIComponent(analyst);
  output.textContent = `正在调用 /api${url} ...`;
  document.getElementById('card-analyst')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  try {
    const data = await API(url);
    if (!data || data.found === false) {
      output.textContent = `暂无 ${state.team} 的分析师结果。调用链：/api${url}`;
      return;
    }
    const content = data.content || '';
    if (typeof content === 'string') {
      output.textContent = `【${data.analyst || analyst}】\n${content}`;
    } else {
      output.textContent = Object.entries(content).map(([name, text]) => `【${name}】\n${text}`).join('\n\n');
    }
  } catch (e) {
    output.textContent = `分析师接口调用失败：/api${url}\n接口依赖后端 LLM 配置；基本面、TK、盘口页不受影响。`;
  }
}

// ─── Team Dropdown ──────────────────────────────
function toggleTeamDropdown() {
  const dd = document.getElementById('team-dropdown');
  if (dd.style.display === 'block') {
    dd.style.display = 'none';
    return;
  }

  const lpl = state.teams.filter(t => t.region === 'LPL');
  const lck = state.teams.filter(t => t.region === 'LCK');

  let html = '<div style="padding:8px 16px;font-size:11px;color:var(--ink-3);font-weight:600">LPL</div>';
  lpl.forEach(t => {
    html += `<div class="dd-item" onclick="selectTeam('${t.short_name}');document.getElementById('team-dropdown').style.display='none'"
      style="padding:8px 16px;cursor:pointer;font-size:14px;font-weight:600;transition:background 100ms"
      onmouseover="this.style.background='var(--pink-light)'"
      onmouseout="this.style.background=''">
      <span style="font-family:var(--mono);font-size:12px;color:var(--ink-2);margin-right:8px">${t.short_name}</span>${t.name}
    </div>`;
  });

  html += '<div style="padding:8px 16px;font-size:11px;color:var(--ink-3);font-weight:600;border-top:1px solid var(--line)">LCK</div>';
  lck.forEach(t => {
    html += `<div class="dd-item" onclick="selectTeam('${t.short_name}');document.getElementById('team-dropdown').style.display='none'"
      style="padding:8px 16px;cursor:pointer;font-size:14px;font-weight:600;transition:background 100ms"
      onmouseover="this.style.background='var(--blue-light)'"
      onmouseout="this.style.background=''">
      <span style="font-family:var(--mono);font-size:12px;color:var(--ink-2);margin-right:8px">${t.short_name}</span>${t.name}
    </div>`;
  });

  dd.innerHTML = html;
  dd.style.display = 'block';

  // Position near the button
  const btn = document.getElementById('sel-team');
  const rect = btn.getBoundingClientRect();
  dd.style.top = rect.bottom + 4 + 'px';
  dd.style.left = rect.left + 'px';

  // Click outside to close
  setTimeout(() => {
    document.addEventListener('click', function closeDD(e) {
      if (!dd.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        dd.style.display = 'none';
        document.removeEventListener('click', closeDD);
      }
    });
  }, 10);
}

// ─── Command Parser ─────────────────────────────
function runCommand() {
  const input = document.getElementById('cmd-input');
  const cmd = input.value.trim();
  if (!cmd) return;
  input.value = '';

  // "MSI" → focus MSI workspace
  if (/交易|盘口|记录/i.test(cmd)) {
    setPage('market');
    loadTrades();
    setTimeout(() => document.getElementById('card-trades')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    return;
  }

  if (/今日内容|日报|赛前卡|内容卡/i.test(cmd)) {
    scrollToTodayContent();
    return;
  }

  if (/分析师|单场分析|BP分析|bp分析/i.test(cmd)) {
    loadAnalyst();
    return;
  }

  if (/^MSI|季中赛|国际赛事/i.test(cmd)) {
    setPage('fundamentals');
    loadFundamentals('msi');
    document.getElementById('tk-search').value = 'MSI';
    searchTK('MSI');
    setTimeout(() => document.getElementById('card-fundamentals')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    return;
  }

  // "看X" pattern
  let m = cmd.match(/^看\s*(\w+)/);
  if (m) { selectTeam(m[1].toUpperCase()); return; }

  // "改XXX" → focus the right field
  m = cmd.match(/改\s*(\S+)\s*(.+)/);
  if (m) {
    const field = m[1]; const val = m[2];
    if (field.includes('操稳') || field.includes('运营') || field.includes('血腥')) {
      // Map to dim field
      if (state._3d) {
        const map = {
          '操稳': 'd1-val', '血腥': 'd1-val',
          '运营': 'd2-val',
        };
        // Try matching labels
        const labels = {
          [state._3d.dim_1_name]: 'd1-val',
          [state._3d.dim_2_name]: 'd2-val',
          [state._3d.dim_3_name]: 'd3-val',
        };
        for (const [k, id] of Object.entries(labels)) {
          if (field.includes(k)) {
            const el = document.getElementById(id);
            el.value = val;
            el.focus();
            markDirty();
            return;
          }
        }
      }
    }
    // Default: treat as notes append
    const na = document.getElementById('notes-area');
    na.value += (na.value ? '\n' : '') + cmd.replace(/^改\s*/, '');
    na.focus();
    markDirty();
    return;
  }

  // "TK XXX" → search
  m = cmd.match(/^TK\s+(.+)/i);
  if (m) { document.getElementById('tk-search').value = m[1]; searchTK(m[1]); return; }

  // "XXX三维" → select team then scroll to 3D
  m = cmd.match(/^(\w+)三维/);
  if (m) { selectTeam(m[1].toUpperCase()); setTimeout(() => document.getElementById('card-3d').scrollIntoView({ behavior: 'smooth' }), 500); return; }

  // Fallback: treat as TK search
  document.getElementById('tk-search').value = cmd;
  searchTK(cmd);
}

function quickCmd(cmd) {
  document.getElementById('cmd-input').value = cmd;
  runCommand();
}

function scrollToTodayContent() {
  setPage('fundamentals');
  loadDailyContent();
  setTimeout(() => {
    document.getElementById('card-today-content')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 80);
}

async function prefillTodayMatch(matchName, opts = {}) {
  const match = parseTodayMatch(matchName);
  if (!match) return;
  setPage('market');
  state.tradeGame = 'lol';
  document.querySelectorAll('.trade-game').forEach(btn => btn.classList.toggle('active', btn.dataset.game === 'lol'));

  const matchEl = document.getElementById('trade-match');
  const reasonEl = document.getElementById('trade-reason');
  const msg = document.getElementById('trade-msg');
  if (matchEl) matchEl.value = match.name;
  if (msg) msg.textContent = '正在带入今日内容卡模板…';

  const tsContext = await loadMsiMatchContext(match.teamA, match.teamB);
  if (reasonEl) reasonEl.value = buildTodayMatchDraft(match.name, tsContext);
  if (msg) msg.textContent = `已带入 ${match.name}：只填前端草稿，不保存`;

  if (opts.analyst) {
    prefillAnalystPromptFromToday(match.name, tsContext);
    setTimeout(() => document.getElementById('card-analyst')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  } else {
    setTimeout(() => document.getElementById('card-trades')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  }
}

function parseTodayMatch(matchName) {
  const parts = String(matchName || '').split(/\s+vs\s+/i).map(s => s.trim()).filter(Boolean);
  if (parts.length !== 2) return null;
  return { name: `${parts[0]} vs ${parts[1]}`, teamA: parts[0], teamB: parts[1] };
}

function buildTodayMatchDraft(matchName, tsContext) {
  const lines = [
    `对象：${matchName}`,
    '来源：今日内容卡前端带入；不保存、不自动下结论。',
  ];
  if (tsContext && tsContext.compare) {
    const a = tsContext.team_a;
    const b = tsContext.team_b;
    lines.push(`TS底表：${a.team} mu ${fmt1(a.mu)} / σ ${fmt1(a.sigma)} / TS ${fmt1(a.ts)}（${a.sample_confidence}，${a.volatility_tier}）；${b.team} mu ${fmt1(b.mu)} / σ ${fmt1(b.sigma)} / TS ${fmt1(b.ts)}（${b.sample_confidence}，${b.volatility_tier}）`);
    lines.push(`观察顺序：${tsContext.compare.risk_note || '先看实力差、波动差、TS 下界，再等 BP/首发/盘口变化确认。'}`);
    lines.push(tsContext.compare.market_note || '赔率只作市场位置参考，重点看市场是否把强队热度或弱队爆冷空间打满。');
    lines.push(tsContext.compare.daily_summary || '');
  } else {
    lines.push('TS底表：只读 GET /api/fundamentals/msi-match-context 未返回，保留静态模板；手动核对 mu / σ / TS。');
    lines.push('观察顺序：先看实力差与波动差，再看 BP/首发/蓝红方，最后核对盘口/水位是否同向。');
  }
  lines.push('当前盘口 / 赔率 / 水位：');
  lines.push('我的判断：');
  lines.push('市场分歧点：');
  lines.push('破相条件：');
  lines.push('边界：本按钮只在前端填草稿，不保存，不 POST/PUT/DELETE；最终交易判断由钧钧自己定。');
  return lines.filter(Boolean).join('\n');
}

function prefillAnalystPromptFromToday(matchName, tsContext) {
  const input = document.getElementById('analyst-bp-input');
  const output = document.getElementById('analyst-output');
  const tsLine = tsContext && tsContext.compare
    ? `${tsContext.compare.daily_summary}\n${tsContext.compare.risk_note}\n${tsContext.compare.market_note}`
    : 'TS底表暂未从只读 GET 取回，使用今日内容卡静态模板，后续手动补 mu / σ / TS。';
  const prompt = [
    `今日对局：${matchName}`,
    '请按小雪单场分析框架处理：先看基本面/TS，再等 BP、首发、蓝红方、每局阵容和盘口变化。',
    tsLine,
    'TS / TK / 盘口依据：TS = mu - 3σ，是保守实力下界；TK 正源走 Wiki / knowledge-rag；盘口只做观察顺序、市场分歧点、风险和破相条件，不自动交易。',
    '输出只要：观察顺序、待补字段、市场分歧点、破相条件；不要给自动交易结论。',
    '明确：本提示由前端生成，不调用 LLM、不保存。',
  ].join('\n');
  if (input) input.value = prompt;
  if (output) output.textContent = '【复制这段去问小雪/分析师】\n\n' + prompt;
}

async function copyTodayBasisPrompt() {
  const text = [
    'TS / TK / 盘口依据',
    'TS = mu - 3σ：TS 是保守实力下界，用来和 mu、σ 一起看稳定性，不是单独的绝对实力排名。',
    'TK 正源：Wiki / knowledge-rag，只做战术、版本、队伍风格依据，不恢复旧 tk_library。',
    '盘口边界：盘口只做观察顺序、市场位置、分歧点、风险和破相条件；不自动交易、不替钧钧下结论。',
    'D121：本按钮只复制前端提示，不保存、不 POST/PUT/DELETE。',
  ].join('\n');
  const status = document.getElementById('today-content-status');
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    if (status) status.textContent = '已复制 TS / TK / 盘口依据说明；只复制，不保存';
  } catch (e) {
    const output = document.getElementById('analyst-output');
    if (output) output.textContent = text;
    if (status) status.textContent = '复制失败，已把依据说明填到分析师输出区；不保存';
  }
}

// ─── Render Profile ─────────────────────────────
function renderProfile(profile) {
  const el = document.getElementById('profile-content');
  if (!profile || !profile.found) {
    el.innerHTML = `<div style="padding:20px;color:var(--ink-3);text-align:center">
      <div style="font-size:32px;margin-bottom:8px">📄</div>
      暂无 ${state.team} 的完整画像<br>
      <span style="font-size:12px">（SKILL.md 不存在）</span>
    </div>`;
    return;
  }
  el.innerHTML = profile.html;
}

// ─── Render 3D ──────────────────────────────────
function render3D(d3) {
  if (!d3) {
    document.getElementById('d1-label').textContent = '---';
    document.getElementById('d1-val').value = '-';
    document.getElementById('d2-label').textContent = '---';
    document.getElementById('d2-val').value = '-';
    document.getElementById('d3-label').textContent = '---';
    document.getElementById('d3-val').value = '-';
    document.getElementById('notes-area').value = '';
    document.getElementById('version-area').value = '';
    document.getElementById('dim-updated').textContent = '';
    return;
  }

  document.getElementById('d1-label').textContent = d3.dim_1_name || '---';
  document.getElementById('d1-val').value = d3.dim_1_value || '-';
  document.getElementById('d2-label').textContent = d3.dim_2_name || '---';
  document.getElementById('d2-val').value = d3.dim_2_value || '-';
  document.getElementById('d3-label').textContent = d3.dim_3_name || '---';
  document.getElementById('d3-val').value = d3.dim_3_value || '-';
  document.getElementById('notes-area').value = d3.notes || '';
  document.getElementById('version-area').value = d3.version_understanding || '';
  document.getElementById('dim-updated').textContent = d3.updated_at ? ' · 更新于 ' + d3.updated_at : '';

  state.dirty = false;
  updateSaveButton();
}

// ─── Dirty tracking ─────────────────────────────
function markDirty() { state.dirty = true; updateSaveButton(); }

function updateSaveButton() {
  const btn = document.getElementById('btn-save');
  if (state.dirty) {
    btn.classList.remove('saved');
    btn.disabled = false;
  } else {
    btn.classList.add('saved');
    btn.disabled = true;
  }
}

// ─── Save 3D ────────────────────────────────────
async function save3D() {
  if (!state.team || !state.dirty) return;

  const btn = document.getElementById('btn-save');
  const msg = document.getElementById('save-msg');
  btn.disabled = true;
  msg.className = 'save-msg';
  msg.textContent = '保存中…';
  msg.classList.add('show');

  try {
    const body = {
      dim_1_value: document.getElementById('d1-val').value,
      dim_2_value: document.getElementById('d2-val').value,
      dim_3_value: document.getElementById('d3-val').value,
      notes: document.getElementById('notes-area').value,
      version_understanding: document.getElementById('version-area').value,
    };
    await fetch('/api/team-3d/' + state.team, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    state.dirty = false;
    state._3d = { ...state._3d, ...body, updated_at: new Date().toLocaleString() };
    updateSaveButton();
    msg.textContent = '✅ 已保存';
    msg.className = 'save-msg show';
    setTimeout(() => msg.classList.remove('show'), 2000);
  } catch (e) {
    msg.textContent = '❌ 保存失败';
    msg.className = 'save-msg show err';
    btn.disabled = false;
  }
}

// ─── TK Search (redesigned: expand, full content, edit) ───
async function searchTK(q) {
  if (!q) q = document.getElementById('tk-search').value.trim();
  if (!q) { q = state.team || ''; }
  if (!q) return;

  const el = document.getElementById('tk-results');
  el.innerHTML = '<div class="tk-empty">搜索中…</div>';

  try {
    const data = await API('/tk/search?q=' + encodeURIComponent(q) + '&team=' + (state.team || '') + '&limit=15');
    const results = data.results || [];

    if (results.length === 0) {
      el.innerHTML = '<div class="tk-empty">未找到相关TK条目</div>';
    } else {
      el.innerHTML = results.map((r, i) => {
        const content = r.content || '';
        const preview = content.slice(0, 200);
        const hasMore = content.length > 200;
        const tags = (r.tags || []).map(t => `<span class="tk-tag">${t}</span>`).join(' ');
        const isShell = content.trim().length < 50;
        const shellClass = isShell ? ' tk-empty-shell' : '';
        return `<div class="tk-item${shellClass}" id="tk-${i}">
          <div class="tk-title" onclick="toggleTK(${i})">
            <span class="tk-expand-icon">▸</span>
            <span>${escHtml(r.concept || r.id)}</span>
          </div>
          <div class="tk-preview">${escHtml(preview)}${hasMore ? '…' : ''}</div>
          <div class="tk-full">${escHtml(content)}</div>
          <div class="tk-meta">
            <span>${r.date || ''}</span>
            <span>${r.source || ''}</span>
            ${isShell ? '<span style="color:var(--ink-3)">⚠ 内容较少</span>' : ''}
          </div>
          ${tags ? '<div style="margin-top:4px">' + tags + '</div>' : ''}
          <div class="tk-actions">
            <button onclick="event.stopPropagation();editTKEntry(${i})">✏️ 编辑</button>
            <button class="danger" onclick="event.stopPropagation();deleteTKEntry(${i})">🗑 删除</button>
          </div>
        </div>`;
      }).join('');
      // Store results for edit/delete
      state._tkResults = results;
    }
  } catch (e) {
    el.innerHTML = '<div class="tk-empty" style="color:var(--red)">搜索失败</div>';
  }
}

function toggleTK(i) {
  const el = document.getElementById('tk-' + i);
  if (!el) return;
  el.classList.toggle('expanded');
}

// ─── TK Editor ──────────────────────────────────
function openTKEditor(filename) {
  const overlay = document.getElementById('tk-editor-overlay');
  overlay.classList.add('open');
  if (filename) {
    document.getElementById('tk-editor-title').textContent = '编辑 TK 条目';
    document.getElementById('tk-editor-filename').value = filename;
    // Pre-fill from results
    const r = state._tkResults?.find(r => r.filename === filename);
    if (r) {
      document.getElementById('tk-editor-content').value = r.content || '';
      document.getElementById('tk-editor-tags').value = (r.tags || []).join(', ');
      document.getElementById('tk-editor-team').value = state.team || '';
    }
  } else {
    document.getElementById('tk-editor-title').textContent = '新建 TK 条目';
    document.getElementById('tk-editor-filename').value = '';
    document.getElementById('tk-editor-content').value = '';
    document.getElementById('tk-editor-tags').value = '';
    document.getElementById('tk-editor-team').value = state.team || '';
  }
  document.getElementById('tk-editor-msg').textContent = '';
  setTimeout(() => document.getElementById('tk-editor-content').focus(), 100);
}

function closeTKEditor() {
  document.getElementById('tk-editor-overlay').classList.remove('open');
}

function editTKEntry(i) {
  const r = state._tkResults?.[i];
  if (!r || !r.filename) return;
  openTKEditor(r.filename);
}

async function deleteTKEntry(i) {
  const r = state._tkResults?.[i];
  if (!r || !r.filename) return;
  if (!confirm('删除 TK 条目：' + (r.concept || r.filename) + '？')) return;
  try {
    await fetch('/api/tk/' + encodeURIComponent(r.filename), { method: 'DELETE' });
    // Refresh search
    searchTK();
  } catch (e) {
    alert('删除失败');
  }
}

async function saveTKEntry() {
  const content = document.getElementById('tk-editor-content').value.trim();
  if (!content || content.length < 10) {
    document.getElementById('tk-editor-msg').textContent = '内容太短（至少10字）';
    return;
  }
  const msg = document.getElementById('tk-editor-msg');
  msg.textContent = '保存中…';
  try {
    const filename = document.getElementById('tk-editor-filename').value.trim();
    const body = {
      content: content,
      source: '手动录入',
      tags: document.getElementById('tk-editor-tags').value,
      team: document.getElementById('tk-editor-team').value || state.team || '',
      player: '',
    };
    const resp = await fetch(filename ? '/api/tk/' + encodeURIComponent(filename) : '/api/tk', {
      method: filename ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(String(resp.status));
    msg.textContent = filename ? '✅ 已更新' : '✅ 已保存';
    setTimeout(() => { closeTKEditor(); searchTK(); }, 800);
  } catch (e) {
    msg.textContent = '❌ 保存失败';
  }
}

// ─── MSI Workspace ──────────────────────────────
async function loadMsiSchedules() {
  const list = document.getElementById('msi-schedules');
  const updated = document.getElementById('msi-updated');
  if (!list) return;
  list.innerHTML = '<div class="msi-empty">加载 MSI 赛程中…</div>';
  if (updated) updated.textContent = '同步中…';

  try {
    const data = await API('/schedules?event=MSI&limit=30').catch(() => API('/schedules?region=国际&limit=30'));
    const rows = Array.isArray(data) ? data : (data.schedules || data.results || []);
    const msiRows = rows.filter(r => {
      const hay = `${r.tournament || ''} ${r.stage || ''} ${r.region || ''} ${r.league_id || ''}`.toLowerCase();
      return hay.includes('msi') || hay.includes('季中赛') || hay.includes('国际');
    });
    const shown = msiRows.length ? msiRows : rows.slice(0, 8);
    renderMsiSchedules(shown);
    if (updated) updated.textContent = shown.length ? '已接入 /api/schedules · 实时赛程' : '已接入 /api/schedules · 暂无数据';
  } catch (e) {
    renderMsiSchedules([
      { date: '2026-06-28', time_bjt: '待定', team_a: 'T1', team_b: 'TLAW', stage: 'Play-In R1', format: 'BO5' },
      { date: '2026-06-28', time_bjt: '待定', team_a: 'KC', team_b: 'DCG', stage: 'Play-In R1', format: 'BO5' },
      { date: '2026-07-03', time_bjt: '待定', team_a: 'TBD', team_b: 'TBD', stage: '正赛', format: 'BO5' },
    ], true);
    if (updated) updated.textContent = '赛程 API 未就绪 · 使用占位';
  }
}

function renderMsiSchedules(rows, fallback = false) {
  const list = document.getElementById('msi-schedules');
  if (!list) return;
  if (!rows || rows.length === 0) {
    list.innerHTML = '<div class="msi-empty">暂无 MSI 赛程</div>';
    return;
  }
  list.innerHTML = rows.map(r => {
    const date = r.date || (r.match_time || '').slice(0, 10) || '--';
    const time = r.time || r.time_bjt || (r.match_time || '').slice(11, 16) || '--:--';
    const teamA = r.team_a || r.team_a_id || 'TBD';
    const teamB = r.team_b || r.team_b_id || 'TBD';
    const meta = [r.stage, r.format || r.game_format, fallback ? '占位' : (r.source || '')].filter(Boolean).join(' · ');
    return `<div class="msi-match">
      <div class="msi-match-time">${escHtml(date.slice(5))}<br>${escHtml(time)}</div>
      <div class="msi-match-teams">${escHtml(teamA)} <span style="color:var(--ink-3);font-size:12px">vs</span> ${escHtml(teamB)}</div>
      <div class="msi-match-meta">${escHtml(meta)}</div>
    </div>`;
  }).join('');
}

function setMsiRegion(region) {
  document.querySelectorAll('.msi-region').forEach(btn => btn.classList.toggle('active', btn.dataset.region === region));
  const el = document.getElementById('msi-compare');
  if (!el) return;
  const copy = {
    ALL: [['观察口径', '赛区强度 / BO5 适配 / 版本理解'], ['Play-In', 'T1 / TLAW / KC / DCG'], ['入口', '赛程、TK、概念图联动']],
    LPL: [['重点', 'LPL 队伍国际版本适配'], ['对比', '前期节奏 vs 中后期团战'], ['入口', '复用三维画像']],
    LCK: [['重点', 'LCK 运营纪律与 BO5 稳定性'], ['对比', '资源置换 / 中野控制'], ['入口', '复用三维画像']],
    INTL: [['重点', '欧美/PCS 外卡未知量'], ['风险', '样本少，先用赛程+TK沉淀'], ['入口', '补 teams 基础信息后扩展']],
  }[region] || [];
  el.innerHTML = copy.map(([k, v]) => `<div><strong>${k}</strong><span>${v}</span></div>`).join('');
}



// ─── Trade Records ──────────────────────────────
function setTradeGame(game) {
  state.tradeGame = game || 'lol';
  document.querySelectorAll('.trade-game').forEach(btn => btn.classList.toggle('active', btn.dataset.game === state.tradeGame));
  loadTrades();
}

async function prefillTradeFromTeam() {
  const msg = document.getElementById('trade-msg');
  if (!state.team) {
    if (msg) msg.textContent = '先选择 LOL 队伍';
    return;
  }

  state.tradeGame = 'lol';
  document.querySelectorAll('.trade-game').forEach(btn => btn.classList.toggle('active', btn.dataset.game === 'lol'));
  if (msg) msg.textContent = '正在带入当前队伍对象…';

  const matchEl = document.getElementById('trade-match');
  const timeEl = document.getElementById('trade-time');
  const reasonEl = document.getElementById('trade-reason');
  const teamInfo = getTeamInfo(state.team);
  let matchName = state.team + ' vs ';
  let matchTime = '';
  let opponent = '';
  let tsContext = null;

  try {
    const rows = await API('/schedules?team=' + encodeURIComponent(state.team) + '&event=MSI&upcoming=true&limit=1');
    const next = Array.isArray(rows) && rows.length ? rows[0] : null;
    if (next) {
      const a = next.team_a || '';
      const b = next.team_b || '';
      opponent = a === state.team ? b : (b === state.team ? a : '');
      matchName = [a || state.team, b || 'TBD'].filter(Boolean).join(' vs ');
      matchTime = [next.date, next.time].filter(Boolean).join('T');
    }
  } catch (e) {
    // 赛程接口不可用时保留手动补全入口。
  }

  if (opponent) {
    tsContext = await loadMsiMatchContext(state.team, opponent);
  }

  if (matchEl) matchEl.value = matchName;
  if (timeEl && matchTime) timeEl.value = matchTime;
  if (reasonEl && !reasonEl.value) {
    const teamLine = `对象：${state.team}${teamInfo.region ? '（' + teamInfo.region + '）' : ''}${opponent ? ' vs ' + opponent : '，对手待补'}`;
    reasonEl.value = buildDailyTradeDraft(teamLine, tsContext);
  }
  if (msg) msg.textContent = opponent ? `已带入 MSI 日报底表：${state.team} vs ${opponent}` : `已带入对象：${state.team} · 待补对手`;
}

async function loadMsiMatchContext(teamA, teamB) {
  try {
    return await API('/fundamentals/msi-match-context?team_a=' + encodeURIComponent(teamA) + '&team_b=' + encodeURIComponent(teamB));
  } catch (e) {
    return null;
  }
}

function buildDailyTradeDraft(teamLine, tsContext) {
  const lines = [teamLine];
  if (tsContext && tsContext.compare) {
    const a = tsContext.team_a;
    const b = tsContext.team_b;
    lines.push(`TS底表：${a.team} mu ${fmt1(a.mu)} / σ ${fmt1(a.sigma)} / TS ${fmt1(a.ts)}（${a.sample_confidence}，${a.volatility_tier}）；${b.team} mu ${fmt1(b.mu)} / σ ${fmt1(b.sigma)} / TS ${fmt1(b.ts)}（${b.sample_confidence}，${b.volatility_tier}）`);
    lines.push(tsContext.compare.risk_note || '');
    lines.push(tsContext.compare.daily_summary || '');
    lines.push(tsContext.compare.market_note || '');
  } else {
    lines.push('TS底表：待补对手后自动带入 mu / σ / TS 对比');
  }
  lines.push('盘口：');
  lines.push('我的判断：');
  lines.push('分歧点：');
  lines.push('破相条件：');
  return lines.filter(Boolean).join('\n');
}

function fmt1(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(1) : '-';
}

function getTeamInfo(code) {
  return state.teams.find(t => t.short_name === code) || { short_name: code, name: code, region: '' };
}

async function loadTrades() {
  const list = document.getElementById('trade-list');
  if (!list) return;
  list.innerHTML = '<div class="tk-empty">加载盘口草稿中…</div>';
  try {
    const [recordsData, stats] = await Promise.all([
      API('/market-notes?game=' + encodeURIComponent(state.tradeGame) + '&limit=30'),
      Promise.resolve({}),
    ]);
    state.trades = recordsData.records || [];
    renderTradeStats(stats || {});
    renderTrades(state.trades);
  } catch (e) {
    list.innerHTML = '<div class="tk-empty" style="color:var(--red)">盘口草稿加载失败</div>';
  }
}

function renderTradeStats(stats) {
  // 盘口页不展示命中率/输赢统计，只保留钧钧自己的盘口分析草稿。
}

function renderTrades(rows) {
  const list = document.getElementById('trade-list');
  if (!list) return;
  if (!rows || rows.length === 0) {
    list.innerHTML = '<div class="tk-empty">暂无盘口草稿</div>';
    return;
  }
  list.innerHTML = rows.map(r => {
    const time = (r.match_time || r.created_at || '').replace('T', ' ').slice(0, 16);
    const reason = [r.reason, r.review ? '备注：' + r.review : ''].filter(Boolean).join('\n');
    return `<div class="trade-item" id="trade-${r.id}">
      <div class="trade-item-head">
        <div><div class="trade-match">${escHtml(r.match_name)}</div><div class="trade-meta">${escHtml(gameLabel(r.game))} · ${escHtml(time)}</div></div>
        <span class="trade-pill gray">盘口草稿</span>
      </div>
      <div class="trade-picks">
        <span class="trade-pill">方向：${escHtml(r.direction || '未写')}</span>
        <span class="trade-pill blue">大小：${escHtml(r.total_lean || '放弃')}</span>
        <span class="trade-pill gray">比分：${escHtml(r.score_note || '-')}</span>
        <span class="trade-pill gray">信心：${escHtml(r.confidence || '中')}</span>
      </div>
      <div class="trade-reason">${escHtml(reason || '无备注')}</div>
      <div class="trade-item-actions">
        <button onclick="tradeToTK(${r.id})">沉淀TK</button>
        <button class="danger" onclick="deleteTrade(${r.id})">删除</button>
      </div>
    </div>`;
  }).join('');
}

function gameLabel(game) {
  return { lol: 'LOL', cs: 'CS', valorant: '无畏', football: '足球' }[game] || game || 'LOL';
}

async function saveTradeRecord() {
  const msg = document.getElementById('trade-msg');
  const match = document.getElementById('trade-match').value.trim();
  if (!match) { if (msg) msg.textContent = '先填比赛'; return; }
  const body = {
    game: state.tradeGame,
    match_name: match,
    match_time: document.getElementById('trade-time').value,
    direction: document.getElementById('trade-winner').value || '',
    total_lean: document.getElementById('trade-total').value || '放弃',
    score_note: document.getElementById('trade-score').value,
    reason: document.getElementById('trade-reason').value,
    confidence: document.getElementById('trade-confidence').value,
    review: document.getElementById('trade-review').value,
    linked_team: state.team || '',
  };
  if (msg) msg.textContent = '保存中…';
  try {
    await fetch('/api/market-notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    ['trade-match','trade-winner','trade-score','trade-reason','trade-review'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    document.getElementById('trade-total').value = '放弃';
    document.getElementById('trade-result').value = '未结算';
    if (msg) msg.textContent = '已保存';
    loadTrades();
  } catch (e) {
    if (msg) msg.textContent = '保存失败';
  }
}

async function deleteTrade(id) {
  if (!confirm('删除这条盘口草稿？')) return;
  const msg = document.getElementById('trade-msg');
  if (msg) msg.textContent = '删除中…';
  try {
    await fetch('/api/market-notes/' + id, { method: 'DELETE' });
    await loadTrades();
    if (msg) msg.textContent = '已删除';
  } catch (e) {
    if (msg) msg.textContent = '删除失败';
  }
}

function tradeToTK(id) {
  const r = state.trades.find(x => x.id === id);
  if (!r) return;
  openTKEditor();
  const linkedTeam = r.linked_team || state.team || '';
  const result = r.result || '未结算';
  const content = [
    `【结论】${gameLabel(r.game)} ${r.match_name}：盘口方向 ${r.direction || '未写'}，大小 ${r.total_lean || '放弃'}，比分判断 ${r.score_note || '-'}`,
    `【队伍】${linkedTeam || '未关联'}${linkedTeam ? '（盘口草稿队伍标签）' : ''}`,
    `【因果】${r.reason || '待补'}`,
    `【备注】${r.review || '未补'}`,
    `【来源】盘口草稿 #${r.id}`,
  ].join('\n');
  document.getElementById('tk-editor-content').value = content;
  document.getElementById('tk-editor-tags').value = ['盘口草稿', gameLabel(r.game), linkedTeam].filter(Boolean).join(',');
  document.getElementById('tk-editor-team').value = linkedTeam;
  document.getElementById('tk-editor-msg').textContent = linkedTeam ? `已带入队伍标签：${linkedTeam}` : '已生成TK草稿，未关联队伍';
}

// ─── Profile Toggle ──────────────────────────────
function toggleProfile() {
  const col = document.getElementById('col-profile');
  const btn = document.getElementById('profile-toggle');
  col.classList.toggle('collapsed');
  btn.textContent = col.classList.contains('collapsed') ? '▶' : '◀';
}

// ─── Helpers ────────────────────────────────────
function escHtml(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ─── Keyboard shortcuts ─────────────────────────
document.addEventListener('keydown', e => {
  // Ctrl+K or / → focus command input
  if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && document.activeElement === document.body)) {
    e.preventDefault();
    document.getElementById('cmd-input').focus();
  }
  // Ctrl+S → save
  if (e.ctrlKey && e.key === 's') {
    e.preventDefault();
    save3D();
  }
  // Escape → close overlays
  if (e.key === 'Escape') {
    closeTKEditor();
    document.getElementById('team-dropdown').style.display = 'none';
  }
});

// Expose to global scope for onclick handlers
window.selectTeam = selectTeam;
window.toggleTeamDropdown = toggleTeamDropdown;
window.setPage = setPage;
window.loadFundamentals = loadFundamentals;
window.toggleGraphEmbed = toggleGraphEmbed;
window.runCommand = runCommand;
window.quickCmd = quickCmd;
window.scrollToTodayContent = scrollToTodayContent;
window.prefillTodayMatch = prefillTodayMatch;
window.copyTodayBasisPrompt = copyTodayBasisPrompt;
window.save3D = save3D;
window.searchTK = searchTK;
window.markDirty = markDirty;
window.toggleTK = toggleTK;
window.openTKEditor = openTKEditor;
window.closeTKEditor = closeTKEditor;
window.editTKEntry = editTKEntry;
window.deleteTKEntry = deleteTKEntry;
window.saveTKEntry = saveTKEntry;
window.loadMsiSchedules = loadMsiSchedules;
window.setMsiRegion = setMsiRegion;
window.toggleProfile = toggleProfile;
window.loadAnalyst = loadAnalyst;
window.generateAnalystPrompt = generateAnalystPrompt;
window.setTradeGame = setTradeGame;
window.prefillTradeFromTeam = prefillTradeFromTeam;
window.loadTrades = loadTrades;
window.saveTradeRecord = saveTradeRecord;
window.deleteTrade = deleteTrade;
window.tradeToTK = tradeToTK;
