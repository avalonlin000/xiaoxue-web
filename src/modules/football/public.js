import { apiRequest } from '../../shared/api/client.js';

const PLAY_KEYS = ['half_break', 'late_over'];
const PLAY_LABELS = { all: '全部符合', half_break: '半破', late_over: '75分钟后' };
const VIEW_LABELS = { candidates: '观察清单', all: '核对全部' };
const DECISION_LABELS = { keep: '保留', exclude: '排除', pending: '待补', outside: '不在圈池' };
const READINESS_LABELS = {
  outside_pool: '初盘低于圈池线且未命中名单', opening_below_pool: '初盘低于圈池线',
  missing_opening_total: '初盘资料未取得', missing_late_history: '晚段历史未取得',
  thin_late_history: '晚段历史样本不足',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function formatKickoff(value) {
  if (!value) return '时间待更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间待更新';
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const part = type => parts.find(item => item.type === type)?.value || '';
  return `${part('month')}月${part('day')}日 ${part('hour')}:${part('minute')}`;
}

function statusLabel(row) {
  if (row.status === 'in') return '进行中';
  if (row.status === 'post' || row.status === 'completed') return '已结束';
  if (row.status === 'pre') return '未开赛';
  return '状态待更新';
}

function bucketOf(play) {
  const item = play || {};
  if (item.decision === 'keep') return 'keep';
  if (item.decision === 'exclude') return 'exclude';
  if (['outside_pool', 'opening_below_pool'].includes(item.readiness)) return 'outside';
  return 'pending';
}

function keptPlays(row) {
  return PLAY_KEYS.filter(key => bucketOf(row.plays?.[key]) === 'keep');
}

function displayPlays(row, state) {
  if (state.play !== 'all') return [state.play];
  return state.view === 'candidates' ? keptPlays(row) : PLAY_KEYS;
}

function firstReason(play) {
  return ((play || {}).reasons || [])[0] || '';
}

function playBadge(play, label) {
  const bucket = bucketOf(play);
  return `<span class="football-play-result ${bucket}"><b>${escapeHtml(label)}</b>${DECISION_LABELS[bucket]}</span>`;
}

function playTag(key) {
  return `<span class="football-fit-tag ${key}">${escapeHtml(PLAY_LABELS[key])}</span>`;
}

function teamPair(row) {
  if (row.display_name) return row.display_name;
  const home = row.home?.display_name || row.home?.short_name || row.home?.name;
  const away = row.away?.display_name || row.away?.short_name || row.away?.name;
  if (home && away) return `${home} vs ${away}`;
  return row.name || '对阵待更新';
}

function marketText(row) {
  if (row.opening_total == null) return '初盘待补';
  const provider = row.opening_market?.provider ? ` · ${row.opening_market.provider}` : '';
  return `初盘 ${row.opening_total}${provider}`;
}

function safeSourceUrl(value) {
  try {
    const url = new URL(String(value || ''));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function sourceLink(row) {
  const href = safeSourceUrl(row.summary_source || row.source_url);
  return href
    ? `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">ESPN 赛程与比赛摘要</a>`
    : 'ESPN 公开赛程与比赛摘要';
}

function sourceBlock(row, state) {
  const gaps = PLAY_KEYS.map(key => READINESS_LABELS[row.plays?.[key]?.readiness]).filter(Boolean);
  const openingGap = row.opening_total_error ? ['初盘读取失败'] : [];
  const uniqueGaps = [...new Set([...gaps, ...openingGap])];
  const provider = row.opening_market?.provider ? ` · ${escapeHtml(row.opening_market.provider)}` : '';
  const updated = state.updatedAt ? ` · 赛程缓存更新 ${escapeHtml(formatKickoff(state.updatedAt))}` : '';
  return `<div class="football-detail-block"><b>完整来源</b><ul>
    <li>${sourceLink(row)}${provider}${updated}</li>
    <li>筛选只使用公开赛程、初盘和近期比赛事件；临场盘口与水位没有接入。</li>
    <li>资料缺口：${uniqueGaps.length ? escapeHtml(uniqueGaps.join('；')) : '本场当前玩法资料完整'}</li>
  </ul></div>`;
}

function playBlock(play, label) {
  const item = play || {};
  const reasons = (item.reasons || []).map(reason => `<li>${escapeHtml(reason)}</li>`).join('');
  return `<div class="football-detail-block"><div class="football-detail-row"><b>${escapeHtml(label)}</b>${playBadge(item, '')}</div>${reasons ? `<ul>${reasons}</ul>` : '<p>暂无筛选依据。</p>'}</div>`;
}

function detailView(row, state) {
  const facts = (row.facts || []).map(fact => `<li>${escapeHtml(fact.text || fact.type || '资料')}${fact.clock ? ` · ${escapeHtml(fact.clock)}` : ''}</li>`).join('');
  return `<section class="football-detail football-inline-detail">
    <div class="football-detail-head"><div><small>本场完整依据</small><h3>${escapeHtml(teamPair(row))}</h3></div><button type="button" data-football-action="details" data-match-id="${escapeHtml(row.id)}">收起</button></div>
    <div class="football-match-meta"><span>${escapeHtml(formatKickoff(row.kickoff))}</span><span>${escapeHtml(row.league_name || row.league || '')}</span><span>${escapeHtml(marketText(row))}</span></div>
    ${playBlock(row.plays?.half_break, '半破')}
    ${playBlock(row.plays?.late_over, '75分钟后')}
    ${sourceBlock(row, state)}
    <div class="football-detail-block"><b>已取得资料</b>${facts ? `<ul>${facts}</ul>` : '<p>暂未取得比赛事件资料；开赛后会单独补充。</p>'}</div>
    <div class="football-detail-block"><b>临场复核</b><p>第25分钟盘口、半场角球和射门、75分钟比分与盘口由你现场查看。</p></div>
  </section>`;
}

function selectionRows(row, mode, selectedPlay) {
  const keys = displayPlays(row, { view: mode, play: selectedPlay });
  return keys.map(key => {
    const reason = firstReason(row.plays?.[key]);
    if (!reason) return '';
    return `<div class="football-selection-row"><span>${escapeHtml(PLAY_LABELS[key])}</span><p>${escapeHtml(reason)}</p></div>`;
  }).filter(Boolean).join('');
}

function matchCard(row, state) {
  const isDetailOpen = state.detail?.id === row.id;
  const playTags = state.view === 'candidates'
    ? displayPlays(row, state).map(playTag).join('')
    : '';
  const resultBadges = state.view === 'all'
    ? PLAY_KEYS.map(key => playBadge(row.plays?.[key], PLAY_LABELS[key])).join('')
    : '';
  const rows = selectionRows(row, state.view, state.play);
  const emptySelection = state.view === 'candidates'
    ? '该场已保留，具体依据请在详情查看。'
    : '完整筛选结论请在详情查看。';
  return `<article class="football-match-card${isDetailOpen ? ' is-open' : ''}" data-match-id="${escapeHtml(row.id)}">
    <div class="football-match-head">
      <div class="football-match-title"><small>${escapeHtml(row.league_name || row.league || '足球')}</small><h3>${escapeHtml(teamPair(row))}</h3></div>
      <div class="football-kickoff"><small>北京时间</small><strong>${escapeHtml(formatKickoff(row.kickoff))}</strong></div>
    </div>
    <div class="football-fit-row"><span class="football-status">${escapeHtml(statusLabel(row))}</span>${state.view === 'candidates' ? '<span class="football-fit-label">符合</span>' : ''}${playTags}<span class="football-opening">${escapeHtml(marketText(row))}</span></div>
    ${resultBadges ? `<div class="football-results">${resultBadges}</div>` : ''}
    <div class="football-selection">${rows || `<p>${emptySelection}</p>`}</div>
    <div class="football-actions"><button type="button" data-football-action="details" data-match-id="${escapeHtml(row.id)}">${isDetailOpen ? '收起详情' : '查看依据'}</button><button type="button" data-football-action="tk" data-match-id="${escapeHtml(row.id)}">记交易TK</button></div>
    ${isDetailOpen ? detailView(row, state) : ''}
  </article>`;
}

export default {
  id: 'football',
  name: '足球观察台',
  async mount(context = {}) {
    const root = document.getElementById('card-football');
    if (!root) throw new Error('足球观察台入口不存在');
    const body = root.querySelector('[data-football-body]');
    const state = {
      view: 'candidates', play: 'all', keyword: '', rows: [], counts: null,
      updatedAt: null, readiness: null, errors: [], detail: null, loading: false,
    };

    const summaryText = () => {
      if (state.loading) return '正在整理符合条件的比赛…';
      if (state.errors.length && state.readiness === 'unavailable') {
        return '资料读取失败 · 没有当成没有比赛';
      }
      if (!state.counts) return '等待第一次读取';
      const half = state.counts.half_break?.keep || 0;
      const late = state.counts.late_over?.keep || 0;
      if (state.keyword.trim()) {
        return `搜索「${state.keyword.trim()}」：${state.rows.length} 场`;
      }
      if (state.play === 'all') {
        const scope = state.view === 'candidates' ? '场符合' : '场比赛';
        return `${state.rows.length} ${scope} · 半破保留 ${half} · 75分钟后保留 ${late}`;
      }
      const scope = state.view === 'candidates' ? '观察清单共' : '核对范围共';
      return `「${PLAY_LABELS[state.play]}」${state.rows.length} 场 · ${scope} ${state.counts.all || 0} 场`;
    };

    const freshnessText = () => {
      if (state.loading) return '';
      const updated = state.updatedAt ? `赛程更新 ${formatKickoff(state.updatedAt)}` : '';
      const partial = state.errors.length || state.readiness === 'partial' ? '部分来源暂未更新' : '';
      return [partial, updated].filter(Boolean).join(' · ');
    };

    const updateSummary = () => {
      const summary = body.querySelector('[data-football-summary]');
      const freshness = body.querySelector('[data-football-freshness]');
      if (summary) summary.textContent = summaryText();
      if (freshness) freshness.textContent = freshnessText();
    };

    const bindControls = () => {
      body.querySelectorAll('[data-football-view]').forEach(button => button.addEventListener('click', () => {
        state.view = button.dataset.footballView;
        state.detail = null;
        actions.load();
      }));
      body.querySelectorAll('[data-football-play]').forEach(button => button.addEventListener('click', () => {
        state.play = button.dataset.footballPlay;
        state.detail = null;
        actions.load();
      }));
      const search = body.querySelector('[data-football-search]');
      if (search) {
        search.addEventListener('input', event => { state.keyword = event.target.value; });
        search.addEventListener('change', () => { state.detail = null; actions.load(); });
        search.addEventListener('keydown', event => { if (event.key === 'Enter') { state.keyword = event.target.value; state.detail = null; actions.load(); } });
      }
      body.querySelector('[data-football-action="refresh"]')?.addEventListener('click', () => actions.load());
    };

    const bindRows = () => {
      body.querySelectorAll('.football-list [data-football-action]').forEach(button => button.addEventListener('click', () => actions.handle(button.dataset.footballAction, button.dataset.matchId)));
    };

    const emptyView = () => {
      if (state.play === 'all') {
        return `<div class="football-empty"><b>现在没有符合现有玩法的比赛</b><span>待补和排除的场次没有放进观察清单。需要核对原因时可切到“核对全部”。</span></div>`;
      }
      return `<div class="football-empty"><b>「${escapeHtml(PLAY_LABELS[state.play])}」暂无保留场次</b><span>这里只显示已经满足该玩法的比赛。</span></div>`;
    };

    const renderRows = () => {
      const list = body.querySelector('[data-football-list]');
      if (!list) return;
      if (state.loading) {
        list.innerHTML = '<div class="football-empty"><b>正在整理比赛</b><span>只显示符合玩法且资料明确的场次。</span></div>';
        bindRows();
        return;
      }
      if (!state.rows.length) {
        list.innerHTML = emptyView();
        bindRows();
        return;
      }
      list.innerHTML = state.rows.map(row => matchCard(row, state)).join('');
      bindRows();
    };

    const render = () => {
      body.innerHTML = `<div class="football-toolbar">
        <div class="football-segments football-view-switch" role="group" aria-label="查看范围">${Object.entries(VIEW_LABELS).map(([key, label]) => `<button type="button" class="${state.view === key ? 'active' : ''}" aria-pressed="${state.view === key}" data-football-view="${key}">${label}</button>`).join('')}</div>
        <div class="football-segments" role="group" aria-label="玩法">${Object.entries(PLAY_LABELS).map(([key, label]) => `<button type="button" class="${state.play === key ? 'active' : ''}" aria-pressed="${state.play === key}" data-football-play="${key}">${label}</button>`).join('')}</div>
        <label class="football-search" aria-label="搜索队伍或联赛"><input data-football-search value="${escapeHtml(state.keyword)}" placeholder="搜队伍或联赛"></label>
        <button type="button" class="football-refresh" data-football-action="refresh">刷新</button>
      </div>
      <div class="football-summary"><strong data-football-summary>${escapeHtml(summaryText())}</strong><span data-football-freshness>${escapeHtml(freshnessText())}</span></div>
      <div class="football-list" data-football-list></div>`;
      bindControls();
      renderRows();
    };

    const actions = {
      async load() {
        state.loading = true;
        updateSummary();
        renderRows();
        try {
          const payload = await apiRequest(`/football/matches?view=${state.view}&play=${state.play}&keyword=${encodeURIComponent(state.keyword)}`, { timeoutMs: 30000 });
          state.rows = payload.matches || [];
          state.counts = payload.counts || null;
          state.updatedAt = payload.updated_at || null;
          state.readiness = payload.readiness || null;
          state.errors = payload.errors || [];
          state.loading = false;
          if (state.detail && !state.rows.some(row => row.id === state.detail.id)) state.detail = null;
          updateSummary();
          renderRows();
          root.dataset.moduleStatus = payload.ok ? 'healthy' : 'partial';
          return payload;
        } catch (error) {
          state.loading = false;
          state.rows = [];
          state.errors = [error.message || '读取失败'];
          state.readiness = 'unavailable';
          updateSummary();
          body.querySelector('[data-football-list]').innerHTML = `<div class="football-empty football-error"><b>足球资料暂时无法读取</b><span>${escapeHtml(error.message || '请稍后重试')}。不会把读取失败当成“没有比赛”。</span></div>`;
          root.dataset.moduleStatus = 'broken';
          return null;
        }
      },
      async handle(action, matchId) {
        const row = state.rows.find(item => item.id === matchId);
        if (!row) return null;
        if (action === 'tk') {
          const applicable = keptPlays(row).map(key => PLAY_LABELS[key]);
          const playLabel = state.play === 'all' ? (applicable.join('、') || '待判断') : PLAY_LABELS[state.play];
          context.football?.onTkDraft?.({ matchName: teamPair(row), matchTime: row.kickoff, reason: `玩法：${playLabel}\n比赛ID：${row.id}\n我的判断：` });
          return null;
        }
        if (action !== 'details') return null;
        if (state.detail?.id === matchId) {
          state.detail = null;
          renderRows();
          return null;
        }
        state.detail = row;
        renderRows();
        try {
          const detail = (await apiRequest(`/football/matches/${encodeURIComponent(matchId)}`, { timeoutMs: 20000 })).match;
          if (state.detail?.id === matchId) {
            state.detail = detail?.plays?.half_break ? detail : row;
            renderRows();
          }
        } catch {
          // 已用列表中的依据打开详情；网络失败时保留可读内容，不伪装成完整详情。
        }
        return state.detail;
      },
    };

    render();
    await actions.load();
    context.events?.on('page:changed', ({ page }) => { if (page === 'football') actions.load(); });
    root.dataset.moduleId = 'football';
    return { actions, state };
  },
};
