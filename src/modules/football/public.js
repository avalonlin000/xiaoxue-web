import { apiRequest } from '../../shared/api/client.js';

const PLAY_LABELS = { all: '全部', half_break: '半破', late_over: '75分钟后' };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function formatKickoff(value) {
  if (!value) return '时间待更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间待更新';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}

function statusLabel(row) {
  if (row.status === 'in') return '进行中';
  if (row.status === 'post' || row.status === 'completed') return '已结束';
  if (row.status === 'pre') return '未开赛';
  return '状态待更新';
}

function playResult(play, label) {
  const item = play || {};
  const decision = item.decision === 'keep' ? '保留' : item.decision === 'exclude' ? '排除' : '资料待补';
  const klass = item.decision || 'pending';
  return `<span class="football-play-result ${klass}"><b>${escapeHtml(label)}</b>${decision}</span>`;
}

function matchCard(row) {
  const name = row.name || `${row.home?.name || '未知'} vs ${row.away?.name || '未知'}`;
  const reasons = (row.plays?.half_break?.reasons || []).concat(row.plays?.late_over?.reasons || []).slice(0, 2);
  return `<article class="football-match-card" data-match-id="${escapeHtml(row.id)}">
    <div class="football-match-head"><div><small>${escapeHtml(row.league_name || row.league || '足球')}</small><h3>${escapeHtml(name)}</h3></div><span class="football-status">${escapeHtml(statusLabel(row))}</span></div>
    <div class="football-match-meta"><span>${escapeHtml(formatKickoff(row.kickoff))}</span><span>${row.opening_total == null ? '初盘待补' : `初盘 ${escapeHtml(row.opening_total)}`}</span></div>
    <div class="football-results">${playResult(row.plays?.half_break, '半破')}${playResult(row.plays?.late_over, '75分钟后')}</div>
    <p class="football-reasons">${reasons.length ? reasons.map(escapeHtml).join(' · ') : '等待真实初盘和历史资料，缺资料不直接排除'}</p>
    <div class="football-actions"><button type="button" data-football-action="details" data-match-id="${escapeHtml(row.id)}">查看详情</button><button type="button" data-football-action="tk" data-match-id="${escapeHtml(row.id)}">记交易TK</button></div>
  </article>`;
}

function detailView(row) {
  if (!row) return '<div class="football-empty">选择一场比赛查看详情。</div>';
  const facts = (row.facts || []).map(fact => `<li>${escapeHtml(fact.text || fact.type || '资料')} ${fact.clock ? `· ${escapeHtml(fact.clock)}` : ''}</li>`).join('');
  return `<section class="football-detail"><div class="football-detail-head"><div><small>比赛详情</small><h3>${escapeHtml(row.name)}</h3></div><button type="button" data-football-action="close-details">收起</button></div>
    <div class="football-detail-grid"><div><b>半破</b><p>${playResult(row.plays?.half_break, '')}</p></div><div><b>75分钟后</b><p>${playResult(row.plays?.late_over, '')}</p></div></div>
    <div class="football-detail-block"><b>已取得资料</b>${facts ? `<ul>${facts}</ul>` : '<p>暂未取得比赛事件资料；开赛后补充资料会单独标明。</p>'}</div>
    <div class="football-detail-block"><b>临场复核</b><p>第25分钟盘口、半场角球/射门、75分钟比分与盘口由你现场查看。</p></div>
  </section>`;
}

export default {
  id: 'football',
  name: '足球观察台',
  async mount(context = {}) {
    const root = document.getElementById('card-football');
    if (!root) throw new Error('足球观察台入口不存在');
    const body = root.querySelector('[data-football-body]');
    const state = { play: 'all', view: 'candidates', keyword: '', rows: [], detail: null };
    const render = () => {
      body.innerHTML = `<div class="football-toolbar"><div class="football-segments">${Object.entries(PLAY_LABELS).map(([key, label]) => `<button type="button" class="${state.play === key ? 'active' : ''}" data-football-play="${key}">${label}</button>`).join('')}</div><input data-football-search value="${escapeHtml(state.keyword)}" placeholder="搜队伍或联赛"><button type="button" data-football-action="refresh">刷新</button></div><div class="football-summary" data-football-summary>读取中…</div><div class="football-list" data-football-list></div><div data-football-detail></div>`;
      body.querySelector('[data-football-detail]').innerHTML = detailView(state.detail);
      body.querySelectorAll('[data-football-play]').forEach(button => button.addEventListener('click', () => { state.play = button.dataset.footballPlay; actions.load(); }));
      body.querySelector('[data-football-search]').addEventListener('change', event => { state.keyword = event.target.value; actions.load(); });
      body.querySelectorAll('[data-football-action]').forEach(button => button.addEventListener('click', () => actions.handle(button.dataset.footballAction, button.dataset.matchId)));
    };
    const actions = {
      async load() {
        render();
        const summary = body.querySelector('[data-football-summary]');
        const list = body.querySelector('[data-football-list]');
        try {
          const payload = await apiRequest(`/football/matches?view=${state.view}&play=${state.play}&keyword=${encodeURIComponent(state.keyword)}`, { timeoutMs: 15000 });
          state.rows = payload.matches || [];
          summary.textContent = payload.readiness === 'ready' ? `${state.rows.length} 场 · ${payload.coverage?.source || '公开资料'} · 更新时间 ${formatKickoff(payload.updated_at)}` : '资料正在补齐，已有内容会保留';
          list.innerHTML = state.rows.length ? state.rows.map(matchCard).join('') : '<div class="football-empty">暂无已取得比赛；来源暂时不可用时不会把比赛当成无候选。</div>';
          body.querySelector('[data-football-detail]').innerHTML = detailView(state.detail && state.rows.find(row => row.id === state.detail.id) ? state.detail : null);
          body.querySelectorAll('[data-football-action]').forEach(button => button.addEventListener('click', () => actions.handle(button.dataset.footballAction, button.dataset.matchId)));
          root.dataset.moduleStatus = payload.ok ? 'healthy' : 'partial';
          return payload;
        } catch (error) {
          summary.textContent = '足球资料暂时无法读取';
          list.innerHTML = `<div class="football-empty">${escapeHtml(error.message || '请稍后重试')}<br>不会因为这次失败生成“无候选”。</div>`;
          root.dataset.moduleStatus = 'broken';
          return null;
        }
      },
      async handle(action, matchId) {
        if (action === 'refresh') return actions.load();
        if (action === 'close-details') { state.detail = null; render(); return null; }
        const row = state.rows.find(item => item.id === matchId);
        if (!row) return null;
        if (action === 'tk') {
          const playLabel = state.play === 'half_break' ? '半破' : state.play === 'late_over' ? '75分钟后' : '待判断';
          context.football?.onTkDraft?.({ matchName: row.name, matchTime: row.kickoff, reason: `玩法：${playLabel}\n比赛ID：${row.id}\n我的判断：` });
          return null;
        }
        if (action === 'details') {
          try { state.detail = (await apiRequest(`/football/matches/${encodeURIComponent(matchId)}`, { timeoutMs: 15000 })).match; } catch { state.detail = row; }
          body.querySelector('[data-football-detail]').innerHTML = detailView(state.detail);
          body.querySelectorAll('[data-football-action="close-details"]').forEach(button => button.addEventListener('click', () => actions.handle('close-details')));
          return state.detail;
        }
        return null;
      },
    };
    render();
    context.events?.on('page:changed', ({ page }) => { if (page === 'football') actions.load(); });
    root.dataset.moduleId = 'football';
    root.dataset.moduleStatus = 'healthy';
    return { actions, state };
  },
};
