export function createCurrentEventView(root) {
  if (!root) throw new Error('当前赛事入口不存在');
  const results = root.querySelector('#event-knowledge-results');
  const plan = root.querySelector('#event-plan-status');
  const matchList = root.querySelector('#event-match-list');
  const recentList = root.querySelector('#event-recent-runs');
  const matchDesk = root.querySelector('#event-match-desk');
  return {
    loading() {
      if (results) results.innerHTML = '<div class="tk-empty">正在读取赛事资料…</div>';
      if (matchList) matchList.innerHTML = '<div class="tk-empty">正在读取今日比赛…</div>';
      if (recentList) recentList.innerHTML = '<div class="tk-empty">正在读取最近推演…</div>';
      if (matchDesk) matchDesk.innerHTML = '<div class="tk-empty">选择一场比赛后汇总单场底稿。</div>';
    },
    render(payload) {
      const { context = {}, items = [], matches = [], recentMatches = [] } = payload || {};
      setText(root, '#event-name', context.event || '当前赛事');
      setText(root, '#event-phase', context.phase || '');
      if (plan) {
        plan.classList.toggle('exists', context.plan_status === 'ready');
        plan.innerHTML = context.plan_status === 'ready'
          ? `<b>${escapeHtml(context.plan_title || '当前交易预案')}</b><span>${escapeHtml(context.plan_content || '')}</span><em>${escapeHtml(context.plan_updated_at ? `更新于 ${context.plan_updated_at}` : '')}</em>`
          : '<b>大周期交易预案：尚未制定</b><span>先与小雪讨论并确认完整预案；工作台不会自动编造。</span>';
      }
      if (matchList) {
        matchList.innerHTML = matches.length
          ? matches.map((item, index) => renderMatchButton(item, index)).join('')
          : '<div class="tk-empty">今天没有已确认比赛。</div>';
      }
      if (recentList) {
        renderRecentList(recentList, recentMatches);
      }
      if (!results) return;
      results.innerHTML = items.length
        ? items.map((item) => `<article class="today-entry exists"><b>${escapeHtml(item.title)}</b><span class="today-summary">${escapeHtml(item.summary.slice(0, 240))}</span><em>${escapeHtml(item.date)}</em></article>`).join('')
        : '<div class="tk-empty">暂无相关 TK。</div>';
    },
    renderRecentMatches(recentMatches = []) {
      if (recentList) renderRecentList(recentList, recentMatches);
    },
    renderMatchLoading() {
      if (matchDesk) matchDesk.innerHTML = '<div class="tk-empty">正在汇总这场比赛…</div>';
    },
    renderMatch(desk, schedule = {}) {
      if (!matchDesk) return;
      const quantitative = desk?.quantitative || {};
      const teamA = quantitative.team_a || {};
      const teamB = quantitative.team_b || {};
      const compare = quantitative.compare || {};
      const rawTsLine = teamA.team && teamB.team
        ? `TS：${escapeHtml(teamA.team)} ${renderTs(teamA)}；${escapeHtml(teamB.team)} ${renderTs(teamB)}`
        : `TS：${escapeHtml(quantitative.reason || '当前没有两队 TS 底表。')}`;
      const virtualPre = desk?.match_run?.exists && desk.match_run.mode === 'virtual_pre';
      const tsLine = virtualPre
        ? '当前 TS：已放入依据账本，虚拟赛前不采用（可能含赛后更新）。'
        : rawTsLine;
      const compareLine = compare.power_note || compare.volatility_note || '';
      const teamEvidence = [
        renderTeamEvidence(desk?.team_a),
        renderTeamEvidence(desk?.team_b),
      ].filter(Boolean).join('');
      const framework = renderTradingFramework(desk?.trading_framework);
      const run = renderMatchRun(desk?.match_run);
      const workspace = renderMatchWorkspace(desk?.workspace);
      matchDesk.innerHTML = `
        <div class="match-desk-head">
          <b>${escapeHtml(schedule.team_a || desk?.match?.team_a || '')} vs ${escapeHtml(schedule.team_b || desk?.match?.team_b || '')}</b>
          <span>${escapeHtml([schedule.time, schedule.stage, schedule.format].filter(Boolean).join(' · '))}</span>
        </div>
        <div class="match-desk-line">${tsLine}</div>
        ${compareLine ? `<div class="match-desk-line">${escapeHtml(compareLine)}</div>` : ''}
        <div class="match-desk-evidence">${teamEvidence}</div>
        ${framework}
        ${run}
        ${workspace}
        <div class="match-desk-actions">
          <button class="btn-tk-new" data-event-action="copy-match">复制给小雪</button>
          <button class="compare-close" data-shell-action="open-market-helper">记录盘口</button>
          <span>BP 出来后直接把十英雄发给小雪。</span>
        </div>`;
    },
    readJudgment() {
      return root.querySelector('#event-match-judgment')?.value || '';
    },
    readChange() {
      return {
        source: root.querySelector('#event-change-source')?.value || '与小雪讨论',
        impact: root.querySelector('#event-change-impact')?.value || '观察',
        detail: root.querySelector('#event-change-detail')?.value || '',
      };
    },
    readTradeEntry() {
      return {
        section: root.querySelector('#event-trade-section')?.value || 'version',
        content: root.querySelector('#event-trade-content')?.value || '',
      };
    },
    selectMatch(index) {
      root.querySelectorAll('[data-event-match]').forEach((button) => {
        button.classList.toggle('active', Number(button.dataset.eventMatch) === Number(index));
      });
      root.querySelectorAll('[data-event-recent-match]').forEach((button) => button.classList.remove('active'));
    },
    selectRecentMatch(index) {
      root.querySelectorAll('[data-event-recent-match]').forEach((button) => {
        button.classList.toggle('active', Number(button.dataset.eventRecentMatch) === Number(index));
      });
      root.querySelectorAll('[data-event-match]').forEach((button) => button.classList.remove('active'));
    },
    setMessage(message, kind = '') {
      const target = root.querySelector('#event-match-message');
      if (!target) return;
      target.textContent = message || '';
      target.dataset.kind = kind;
    },
    bind(actions) {
      const onClick = (event) => {
        const button = event.target.closest('[data-event-action], [data-event-match], [data-event-recent-match]');
        if (!button) return;
        if (button.dataset.eventMatch !== undefined) actions.selectMatch(Number(button.dataset.eventMatch));
        if (button.dataset.eventRecentMatch !== undefined) actions.selectRecentMatch(Number(button.dataset.eventRecentMatch));
        if (button.dataset.eventAction === 'copy-match') actions.copyMatch();
        if (button.dataset.eventAction === 'save-judgment') actions.saveJudgment();
        if (button.dataset.eventAction === 'save-change') actions.saveChange();
        if (button.dataset.eventAction === 'start-run') actions.startRun();
        if (button.dataset.eventAction === 'focus-run') actions.focusRun();
        if (button.dataset.eventAction === 'pause-run') actions.pauseRun();
        if (button.dataset.eventAction === 'save-trade-entry') actions.saveTradeEntry();
      };
      root.addEventListener('click', onClick);
      return () => root.removeEventListener('click', onClick);
    },
    error() {
      if (results) results.innerHTML = '<div class="tk-empty" style="color:var(--red)">当前赛事资料暂时不可用。</div>';
      root.dataset.moduleStatus = 'broken';
    },
  };
}

function renderRecentList(target, recentMatches) {
  target.innerHTML = recentMatches.length
    ? recentMatches.map((item, index) => renderRecentMatchButton(item, index)).join('')
    : '<div class="tk-empty">还没有打开过单场交易推演。</div>';
}

function renderMatchButton(item, index) {
  const match = item.match || {};
  const ts = item.ts || {};
  const compare = ts.compare || {};
  const line = ts.available
    ? `${compare.stronger || '双方'} · TS 差 ${format(compare.ts_diff)}`
    : ts.reason || '未能读取两队 TS';
  return `<button class="event-match-button" data-event-match="${index}">
    <b>${escapeHtml(match.team_a || '')} vs ${escapeHtml(match.team_b || '')}</b>
    <span>${escapeHtml([match.time, match.stage, match.format].filter(Boolean).join(' · '))}</span>
    <em>${escapeHtml(line)}</em>
  </button>`;
}

function renderRecentMatchButton(item, index) {
  const match = item.match || {};
  const state = item.activity_status === 'active' ? '正在聊' : '已暂存';
  return `<button class="event-match-button" data-event-recent-match="${index}">
    <b>${escapeHtml(match.team_a || '')} vs ${escapeHtml(match.team_b || '')}</b>
    <span>${escapeHtml([match.match_date, match.match_time, match.event].filter(Boolean).join(' · '))}</span>
    <em>${escapeHtml(state)} · 停在 ${escapeHtml(item.focus_label || '单场底稿')}</em>
  </button>`;
}

function renderTs(team) {
  return `mu ${format(team.mu)} / σ ${format(team.sigma)} / TS ${format(team.ts)}`;
}

function renderTeamEvidence(team) {
  if (!team?.team) return '';
  const starters = (team.starters || []).map((player) => `${player.role || ''} ${player.name || ''}`.trim()).filter(Boolean).join(' / ');
  const threeDimensional = (team.three_dimensional?.items || [])
    .map((item) => [item.label, item.value].filter(Boolean).join('：'))
    .filter(Boolean).join('；');
  if (!starters && !threeDimensional) return '';
  return `<div class="match-desk-team"><b>${escapeHtml(team.team)}</b>${starters ? `<span>首发：${escapeHtml(starters)}</span>` : ''}${threeDimensional ? `<span>三维：${escapeHtml(threeDimensional)}</span>` : ''}</div>`;
}

function renderTradingNotes(notes) {
  return (notes || []).map((note) => {
    const text = note.hint || note.title || '';
    return text ? `<span>${escapeHtml(text)}</span>` : '';
  }).join('');
}

function renderTradingFramework(framework = {}) {
  const items = framework.items || [];
  if (!items.length) return '';
  return `<div class="match-desk-notes"><b>本场交易 TK</b>${items.map((item) => {
    const prefix = [item.scope_label, ({ candidate: '待验证', confirmed: '已确认' })[item.status]]
      .filter(Boolean).join(' · ');
    const text = [prefix, item.statement].filter(Boolean).join('：');
    return `<span>${escapeHtml(text)}</span>`;
  }).join('')}</div>`;
}

function renderMatchRun(run = {}) {
  if (!run?.exists) {
    return `<section class="match-run">
      <div class="match-workspace-head"><b>单场交易推演</b><span>比赛只是临时分析入口。</span></div>
      <div class="match-run-empty">打开后会调用双方队伍、选手、TS、三维和 TK；任何一项都能直接开始或跳过。</div>
      <div class="match-workspace-actions"><button class="compare-close" data-event-action="start-run">打开这场推演</button><span>长期更新仍归队伍、选手、版本和交易方法。</span></div>
    </section>`;
  }
  const facts = (run.facts || []).map((fact) => {
    const time = fact.as_of ? ` · ${fact.as_of}` : '';
    return `<li class="match-run-fact status-${escapeHtml(fact.status || 'needs_review')}">
      <b>${escapeHtml(fact.label)}</b>
      <span>${escapeHtml(fact.value)}</span>
      <em>${escapeHtml(fact.source || '')}${escapeHtml(time)}</em>
      <small>${escapeHtml(statusLabel(fact.status))}：${escapeHtml(fact.action || '')}</small>
    </li>`;
  }).join('');
  const entries = (run.entries || []).map((entry) => `
    <li><b>${escapeHtml(entry.label || '')}</b><span>${escapeHtml(entry.content || '')}</span><em>${escapeHtml(entry.updated_at || '')}</em></li>`).join('');
  const sectionOptions = Object.entries(tradeSections()).map(([value, label]) =>
    `<option value="${value}"${run.focus === value ? ' selected' : ''}>${escapeHtml(label)}</option>`).join('');
  const focused = (run.entries || []).find((entry) => entry.section === run.focus);
  const runAction = run.activity_status === 'active'
    ? '<button class="compare-close" data-event-action="pause-run">先放下这场</button>'
    : '<button class="compare-close" data-event-action="start-run">回到这场</button>';
  return `<section class="match-run">
    <div class="match-workspace-head"><b>单场交易推演</b><span>${run.activity_status === 'active' ? '当前正在聊' : '已暂存，可随时回来'}</span></div>
    <div class="match-run-next"><b>当前位置：</b>${escapeHtml(run.guide?.focus_label || '单场底稿')}　可直接切到任何一项；只有写下内容时才保存。</div>
    ${entries ? `<ul class="match-change-list">${entries}</ul>` : '<div class="match-run-empty">还没有保存交易判断；可以直接从任何一项开始。</div>'}
    <div class="match-change-form match-trade-entry-form">
      <select id="event-trade-section" aria-label="交易环节">${sectionOptions}</select>
      <textarea id="event-trade-content" maxlength="1200" placeholder="只写现在需要整理的这一项" aria-label="当前交易判断">${escapeHtml(focused?.content || '')}</textarea>
      <button class="compare-close" data-event-action="focus-run">切到这一项</button>
      <button class="compare-close" data-event-action="save-trade-entry">只更新这一项</button>
    </div>
    <div class="match-workspace-head match-change-head"><b>本场调用依据</b><span>时间只作来源信息，不会自动判定过时。</span></div>
    ${facts ? `<ul class="match-run-facts">${facts}</ul>` : '<div class="match-run-empty">还没有依据。</div>'}
    <div class="match-workspace-actions">${runAction}<span>有错误直接对小雪说具体内容，不需要记编号。</span></div>
  </section>`;
}

function statusLabel(status = '') {
  return ({ active: '已读取', excluded: '本场不用', needs_review: '待你核对', missing: '未找到', user_override: '已按你修正' })[status] || status;
}

function tradeSections() {
  return {
    version: '版本与环境', team: '队伍与选手', trend: '已采用规律', matchup: '本场适用性',
    lineup: '阵容条件', branches: '条件分支', market: '市场对照',
    plan: '当前交易计划', entry: '入场信号', exit: '退出条件', execution: '实际执行', review: '复盘结论',
  };
}

function renderMatchWorkspace(workspace = {}) {
  if (!workspace?.exists) return '';
  const current = workspace?.current;
  const judgment = current ? formatJudgment(current) : '方向：\n理由：\n处理：\n变化条件：';
  const changes = (workspace?.changes || []).map((item) => `
    <li><b>${escapeHtml(item.source || '')} · ${escapeHtml(item.impact || '')}</b><span>${escapeHtml(item.detail || '')}</span><em>${escapeHtml(item.created_at || '')}</em></li>`).join('');
  return `<section class="match-workspace">
    <div class="match-workspace-head"><b>原有单场记录</b><span>${current?.updated_at ? `更新于 ${escapeHtml(current.updated_at)}` : ''}</span></div>
    ${current ? `<div class="match-current-lines">${renderJudgmentLines(current)}</div>` : ''}
    <textarea id="event-match-judgment" class="match-workspace-input" rows="4" aria-label="原有四行判断">${escapeHtml(judgment)}</textarea>
    <div class="match-workspace-actions"><button class="compare-close" data-event-action="save-judgment">更新原有记录</button><span>兼容原来已经保存的内容。</span></div>
    <div class="match-workspace-head match-change-head"><b>变化记录</b><span>只写这次具体变了什么。</span></div>
    ${changes ? `<ul class="match-change-list">${changes}</ul>` : ''}
    <div class="match-change-form">
      <select id="event-change-source" aria-label="变化来源"><option>与小雪讨论</option><option>首发</option><option>BP</option><option>盘口</option><option>比赛</option><option>其他</option></select>
      <select id="event-change-impact" aria-label="对当前判断的影响"><option>观察</option><option>维持</option><option>加强</option><option>削弱</option><option>推翻</option></select>
      <input id="event-change-detail" maxlength="500" placeholder="例如：A 打野临时轮换" aria-label="具体变化">
      <button class="compare-close" data-event-action="save-change">记录变化</button>
    </div>
  </section>`;
}

function formatJudgment(current) {
  return [
    `方向：${current.direction || ''}`,
    `理由：${current.reasons || ''}`,
    `处理：${current.handling || ''}`,
    `变化条件：${current.change_conditions || ''}`,
  ].join('\n');
}

function renderJudgmentLines(current) {
  return [
    ['方向', current.direction], ['理由', current.reasons], ['处理', current.handling], ['变化条件', current.change_conditions],
  ].map(([label, value]) => `<span><b>${label}：</b>${escapeHtml(value || '')}</span>`).join('');
}

function format(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) : '-';
}

function setText(root, selector, value) {
  const element = root.querySelector(selector);
  if (element) element.textContent = value;
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}
