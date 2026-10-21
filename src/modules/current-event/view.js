import { matchMaterialsForDesk } from './service.js';

const FALLBACK_STAGES = {
  pre: {
    label: '赛前',
    purpose: '判断基础、主要矛盾、计划和不碰条件。',
    modules: [
      ['version', '版本与环境'], ['team', '队伍与选手'], ['trend', '已采用规律'],
      ['matchup', '本场适用性'], ['branches', '条件分支'], ['market', '市场对照'],
      ['plan', '当前交易计划'], ['entry', '入场信号'], ['exit', '退出条件'],
    ],
  },
  live: {
    label: '赛中',
    purpose: '对照 BP、首发、比赛和市场变化，记录实际执行。',
    modules: [['lineup', '阵容条件'], ['execution', '实际执行']],
  },
  post: {
    label: '赛后',
    purpose: '回看实际发生、判断与执行，并留下可复用候选。',
    modules: [['review', '复盘结论']],
  },
};

const SOURCE_LABELS = {
  scoregg_schedule: '已确认赛程', scoregg_form: '近期赛果', team_profile: '队伍资料',
  team_3d: '队伍风格资料', trading_note: '交易备注', team_ts: 'TS 对照',
};

export function createCurrentEventView(root) {
  if (!root) throw new Error('当前赛事入口不存在');
  const results = root.querySelector('#event-knowledge-results');
  const plan = root.querySelector('#event-plan-status');
  const methods = root.querySelector('#event-methods-list');
  const versionUnderstanding = root.querySelector('#event-version-understanding');
  const matchList = root.querySelector('#event-match-list');
  const recentList = root.querySelector('#event-recent-runs');
  const matchDesk = root.querySelector('#event-match-desk');
  const judgment = root.querySelector('#event-judgment-content');
  const judgmentReader = root.querySelector('#event-judgment-reader');
  const eventPrepared = root.querySelector('#event-prepared-content');
  let activeRunStage = 'pre';
  let activeSection = 'version';
  let renderedRunId = null;
  let tradePlanEditor = null;

  const selectRunStage = (stage) => {
    if (!FALLBACK_STAGES[stage]) return;
    activeRunStage = stage;
    const panel = root.querySelector(`[data-run-stage-panel="${stage}"]`);
    const first = panel?.querySelector('[data-entry-section]');
    if (first) {
      activeSection = first.dataset.entrySection || activeSection;
      const textarea = root.querySelector('#event-trade-content');
      if (textarea) textarea.value = first.dataset.entryContent || '';
      const legacySelect = root.querySelector('#event-trade-section');
      if (legacySelect) legacySelect.value = activeSection;
    }
    updateRunStageUi();
  };

  const selectTradeSection = (section, content = '') => {
    if (!section) return;
    activeSection = section;
    const button = root.querySelector(`[data-entry-section="${CSS.escape(section)}"]`);
    const stage = button?.closest('[data-run-stage-panel]')?.dataset.runStagePanel;
    if (stage) activeRunStage = stage;
    const textarea = root.querySelector('#event-trade-content');
    if (textarea && content !== undefined) textarea.value = content;
    const legacySelect = root.querySelector('#event-trade-section');
    if (legacySelect) legacySelect.value = activeSection;
    updateRunStageUi();
  };

  const updateRunStageUi = () => {
    root.querySelectorAll('[data-run-stage-tab]').forEach((button) => {
      button.classList.toggle('active', button.dataset.runStageTab === activeRunStage);
      button.setAttribute('aria-selected', button.dataset.runStageTab === activeRunStage ? 'true' : 'false');
    });
    root.querySelectorAll('[data-run-stage-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.runStagePanel !== activeRunStage;
    });
    root.querySelectorAll('[data-entry-section]').forEach((button) => {
      button.classList.toggle('active', button.dataset.entrySection === activeSection);
    });
  };

  const view = {
    loading() {
      if (eventPrepared) eventPrepared.innerHTML = '<p class="tk-empty">正在读取已准备的赛事内容…</p>';
      if (results) results.innerHTML = '<div class="tk-empty">正在读取赛事资料…</div>';
      if (methods) methods.innerHTML = '<div class="tk-empty">正在读取可用判断视角…</div>';
      if (versionUnderstanding) versionUnderstanding.innerHTML = '<div class="tk-empty">正在读取当前版本理解…</div>';
      if (matchList) matchList.innerHTML = '<div class="tk-empty">正在读取近期比赛…</div>';
      if (recentList) recentList.innerHTML = '<div class="tk-empty">正在读取最近查看…</div>';
      if (matchDesk) matchDesk.innerHTML = '<div class="tk-empty">选择一场比赛后，在这里查看资料和当前方案。</div>';
    },
    render(payload) {
      const { context = {}, items = [], matches = [], recentMatches = [], methods: methodCards = [], versionUnderstanding: versionData = null } = payload || {};
      setText(root, '#event-name', context.event || '当前赛事');
      setText(root, '#event-phase', context.phase || '');
      renderFramework(plan, context.stage_framework || context);
      renderVersionUnderstanding(versionUnderstanding, versionData);
      renderMethods(methods, methodCards);
      if (matchList) {
        const coverage = payload.preparation;
        const overview = coverage ? '<p class="tk-empty" data-preparation-summary>近期确认 ' + coverage.confirmed_total
          + ' 场 · 已整理 ' + coverage.prepared + ' · 部分整理 ' + coverage.partial
          + ' · 暂无正文 ' + coverage.not_started + (coverage.pending_total ? ' · 对阵待定 ' + coverage.pending_total : '') + '</p>' : '';
        matchList.innerHTML = matches.length
          ? overview + matches.map((item, index) => renderMatchButton(item, index)).join('')
          : overview + '<div class="tk-empty">所选范围暂没有赛程，仍可阅读赛事内容或选择队伍。</div>';
        if (payload.scheduleTruncated) matchList.innerHTML += '<p class="tk-empty">近期赛程较多，当前只显示部分比赛。</p>';
      }
      if (recentList) renderRecentList(recentList, recentMatches);
      if (results) {
        results.innerHTML = items.length
          ? items.map((item) => `<article class="today-entry exists"><b>${escapeHtml(item.title)}</b><span class="today-summary">${escapeHtml((item.summary || '').slice(0, 240))}</span><em>${escapeHtml(item.date || '')}</em></article>`).join('')
          : '<div class="tk-empty">暂无相关资料。</div>';
      }
    },
    renderEventMaterials(payload) {
      if (eventPrepared) {
        const hasDigest = payload.result?.sections?.some((section) => section.id === 'digest' && section.selection_status === 'screened');
        const sections = (payload.result?.sections || []).filter((section) => ['digest', 'analysis', 'comparison'].includes(section.id));
        const result = payload.result ? { ...payload.result, sections,
          summary: hasDigest ? payload.result.summary : '正在整理本届赛事公开分析，准备好后直接显示在这里。' } : null;
        eventPrepared.innerHTML = renderPreparedMaterials({ ...payload, result, title: '赛事资料' });
      }
    },
    watchReading(kind, onVisible) {
      const target = kind === 'event' ? eventPrepared : kind === 'judgment' ? judgment : matchDesk?.querySelector('[data-match-materials]');
      if (!target || typeof IntersectionObserver === 'undefined') return () => {};
      let observer;
      let done = false;
      const visiblePositions = () => [...target.querySelectorAll('[data-reading-position]')]
        .filter((row) => { const background = row.querySelector('[data-reading-background]'); return !background || background.open; })
        .map((row) => row.dataset.readingPosition);
      const receipt = () => {
        if (onVisible(visiblePositions()) !== false) return;
        const notice = target.querySelector('[data-reading-notice]');
        if (notice) { notice.hidden = false; notice.textContent = '本次浏览暂不能记住阅读位置。'; }
      };
      const check = () => {
        const rect = target.getBoundingClientRect();
        if (done || globalThis.document?.visibilityState !== 'visible' || !target.checkVisibility?.()
          || rect.bottom <= 0 || rect.top >= globalThis.innerHeight) return;
        done = true; observer?.disconnect();
        globalThis.document?.removeEventListener('visibilitychange', check);
        receipt();
      };
      const expanded = (event) => {
        if (done && event.target.matches?.('[data-reading-background]') && event.target.open
          && globalThis.document?.visibilityState === 'visible' && target.checkVisibility?.()) receipt();
      };
      observer = new IntersectionObserver(check, { threshold: 0 });
      observer.observe(target);
      globalThis.document?.addEventListener('visibilitychange', check);
      target.addEventListener('toggle', expanded, true);
      return () => { done = true; observer.disconnect(); globalThis.document?.removeEventListener('visibilitychange', check); target.removeEventListener('toggle', expanded, true); };
    },
    renderRecentMatches(recentMatches = []) {
      if (recentList) renderRecentList(recentList, recentMatches);
    },
    renderMatchLoading() {
      activeRunStage = 'pre';
      activeSection = 'version';
      renderedRunId = null;
      if (matchDesk) matchDesk.innerHTML = '<div class="tk-empty">正在整理这场比赛的资料…</div>';
    },
    renderMatch(desk, schedule = {}) {
      if (!matchDesk) return;
      const quantitative = desk?.quantitative || {};
      const teamA = quantitative.team_a || {};
      const teamB = quantitative.team_b || {};
      const compare = quantitative.compare || {};
      const rawTsLine = teamA.team && teamB.team
        ? `综合实力：${escapeHtml(teamA.team)} ${renderTs(teamA)}；${escapeHtml(teamB.team)} ${renderTs(teamB)}`
        : `综合实力：${escapeHtml(quantitative.reason || '当前没有两队展示数据。')}`;
      const virtualPre = desk?.match_run?.exists && desk.match_run.mode === 'virtual_pre';
      const tsLine = virtualPre
        ? '当前综合实力：已放入依据账本，虚拟赛前不采用（可能含赛后更新）。'
        : rawTsLine;
      const compareLine = compare.power_note || compare.volatility_note || '';
      const seriesContext = renderSeriesContext(desk?.series_context);
      const teamEvidence = [renderTeamEvidence(desk?.team_a), renderTeamEvidence(desk?.team_b)].filter(Boolean).join('');
      const framework = renderTradingFramework(desk?.trading_framework);
      const tradePlan = renderTradePlan(desk?.trade_plan, desk?.match || schedule, tradePlanEditor);
      const tradePlanReview = renderTradePlanReview(desk?.trade_plan_review);
      const matchRun = desk?.match_run;
      if (matchRun?.exists && matchRun.id !== renderedRunId) {
        renderedRunId = matchRun.id;
        activeSection = matchRun.focus && matchRun.focus !== 'overview' ? matchRun.focus : 'version';
        activeRunStage = stageForSection(activeSection, matchRun.guide?.stages);
      } else if (!matchRun?.exists) {
        renderedRunId = null;
      }
      const run = renderMatchRun(matchRun, { activeRunStage, activeSection });
      const deskMatch = desk?.match || {};
      const match = {
        team_a: deskMatch.team_a || schedule.team_a || '',
        team_b: deskMatch.team_b || schedule.team_b || '',
        time: deskMatch.time || schedule.time || '',
        stage: deskMatch.stage || schedule.stage || '',
        format: deskMatch.format || schedule.format || '',
      };
      const matchMeta = [formatMatchTime(match.time), match.stage, match.format].filter(Boolean);
      matchDesk.innerHTML = `
        <div class="match-desk-head">
          <div class="match-desk-title">
            <span>已选比赛</span>
            <h2>${escapeHtml(match.team_a || '')} <i>vs</i> ${escapeHtml(match.team_b || '')}</h2>
          </div>
          <div class="match-desk-meta" aria-label="比赛信息">${matchMeta.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}</div>
        </div>
        <div class="match-desk-line">${tsLine}</div>
        ${compareLine ? `<div class="match-desk-line">${escapeHtml(compareLine)}</div>` : ''}
        ${seriesContext}
        <div class="match-desk-evidence">${teamEvidence}</div>
        <section data-match-materials class="match-workspace" style="overflow-wrap:anywhere" aria-label="比赛资料" aria-live="polite">${renderPreparedMaterials(matchMaterialsForDesk(desk))}</section>
        ${framework}
        ${tradePlan}
        ${tradePlanReview}
        ${run}
        ${renderGolEvidence(desk?.gol_evidence)}
        <div class="match-desk-actions">
          <input id="event-gol-game-id" inputmode="numeric" placeholder="Gol.gg 局号（按需）" aria-label="Gol.gg 对局编号">
          <button class="compare-close" data-event-action="load-gol-evidence">查逐局事实</button>
          <button class="btn-tk-new" data-event-action="copy-match">复制给小雪</button>
          <button class="compare-close" data-shell-action="open-market-helper">记录盘口</button>
          <span>分析在聊天里完成，这里留下原始记录和回看线索。</span>
        </div>`;
      updateRunStageUi();
    },
    renderMaterials(payload) {
      const target = matchDesk?.querySelector('[data-match-materials]');
      if (target) target.innerHTML = renderPreparedMaterials(payload);
    },
    resetJudgment() {
      if (judgmentReader) judgmentReader.hidden = true;
      if (judgment) judgment.innerHTML = '';
      const messages = root.querySelector('#event-judgment-messages');
      if (messages) messages.innerHTML = '';
      const question = root.querySelector('#event-judgment-question');
      if (question) question.value = '';
      const team = root.querySelector('#event-judgment-team');
      if (team) team.value = '';
      const status = root.querySelector('#event-judgment-message');
      if (status) status.textContent = '';
      const form = root.querySelector('#event-judgment-form');
      if (form) form.hidden = true;
      root.querySelectorAll('[data-event-method]').forEach((button) => button.setAttribute('aria-pressed', 'false'));
    },
    renderJudgmentLoading(methodId) {
      if (judgmentReader) judgmentReader.hidden = false;
      if (judgment) judgment.innerHTML = '<p class="tk-empty">正在读取对应内容和依据…</p>';
      const form = root.querySelector('#event-judgment-form');
      if (form) form.hidden = true;
      const messages = root.querySelector('#event-judgment-messages');
      if (messages) messages.innerHTML = '';
      const status = root.querySelector('#event-judgment-message');
      if (status) status.textContent = '';
      root.querySelectorAll('[data-event-method]').forEach((button) => button.setAttribute('aria-pressed', button.dataset.eventMethod === methodId ? 'true' : 'false'));
    },
    renderJudgment(payload) {
      if (judgmentReader) judgmentReader.hidden = false;
      if (judgment) judgment.innerHTML = renderJudgmentContext(payload);
      const form = root.querySelector('#event-judgment-form');
      if (form) form.hidden = !payload?.discussion_available;
      const ask = root.querySelector('[data-event-action="ask-judgment"]');
      if (ask) ask.disabled = false;
    },
    restoreJudgmentSession(session = {}) {
      const messages = root.querySelector('#event-judgment-messages');
      if (messages) messages.innerHTML = (session.exchanges || []).map(renderJudgmentDiscussion).join('');
      const question = root.querySelector('#event-judgment-question');
      if (question) question.value = session.draft || '';
      const team = root.querySelector('#event-judgment-team');
      if (team) team.value = session.object?.team || '';
      const notices = [];
      if (session.basisChanged) notices.push('已有回答所用依据有更新；继续讨论会读取当前依据，旧回答不作为当前事实。');
      if (session.truncated) notices.push('本页与继续讨论仅保留最近8条问答消息；较长回答发送时会节选。');
      else if (session.exchanges?.some((item) => item.answer?.length > 3900)) notices.push('较长回答继续讨论时会节选，页面保留全文。');
      if (session.evicted) notices.push('之前这部分临时讨论已移出缓存，请重新提供必要信息。');
      const status = root.querySelector('#event-judgment-message');
      if (status) status.textContent = session.pending ? '正在结合当前内容讨论…' : notices.join(' ');
      const ask = root.querySelector('[data-event-action="ask-judgment"]');
      if (ask) ask.disabled = Boolean(session.pending);
    },
    readJudgmentTeam() { return root.querySelector('#event-judgment-team')?.value.trim() || ''; },
    readJudgmentQuestion() { return root.querySelector('#event-judgment-question')?.value || ''; },
    returnToMatch() {
      const target = matchDesk?.querySelector('.match-desk-head') ? matchDesk : matchList;
      target?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    },
    renderJudgmentDiscussion(payload) {
      const button = root.querySelector('[data-event-action="ask-judgment"]');
      const status = root.querySelector('#event-judgment-message');
      if (button) button.disabled = Boolean(payload?.pending);
      if (status) status.textContent = payload?.pending ? '正在结合当前内容讨论…' : payload?.error || '';
      if (!payload?.answer) return;
      const messages = root.querySelector('#event-judgment-messages');
      if (messages) messages.innerHTML += renderJudgmentDiscussion(payload);
      // Only clear the question that was actually sent, not a newer draft typed while waiting.
      const input = root.querySelector('#event-judgment-question');
      if (input && input.value.trim() === payload.question) input.value = '';
    },
    readGolGameId() {
      return root.querySelector('#event-gol-game-id')?.value || '';
    },
    readTradeEntry() {
      return {
        section: root.querySelector('#event-trade-section')?.value || activeSection || 'version',
        content: root.querySelector('#event-trade-content')?.value || '',
      };
    },
    readTradePlanItem() {
      return {
        itemId: tradePlanEditor?.id || '',
        market: root.querySelector('#event-trade-plan-market')?.value || 'team',
        team: root.querySelector('#event-trade-plan-team')?.value || '',
        direction: root.querySelector('#event-trade-plan-direction')?.value || '',
        statement: root.querySelector('#event-trade-plan-statement')?.value || '',
      };
    },
    beginTradePlanEdit(item) {
      tradePlanEditor = item || null;
      const values = tradePlanEditor || {};
      const market = root.querySelector('#event-trade-plan-market');
      const team = root.querySelector('#event-trade-plan-team');
      const direction = root.querySelector('#event-trade-plan-direction');
      const statement = root.querySelector('#event-trade-plan-statement');
      if (market) market.value = values.market || 'team';
      if (team) team.value = values.team || '';
      if (direction) direction.value = values.direction || '';
      if (statement) statement.value = values.statement || '';
      const submit = root.querySelector('[data-event-action="save-trade-plan-item"]');
      if (submit) submit.textContent = tradePlanEditor ? '保存修改' : '加入本场方案';
      const cancel = root.querySelector('[data-event-action="cancel-trade-plan-edit"]');
      if (cancel) cancel.hidden = !tradePlanEditor;
      root.querySelector('#event-trade-plan-market')?.focus();
    },
    clearTradePlanEditor() {
      tradePlanEditor = null;
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
        const button = event.target.closest('[data-event-action], [data-event-match], [data-event-recent-match], [data-event-method]');
        if (!button) return;
        if (button.dataset.eventMethod !== undefined) actions.openJudgment(button.dataset.eventMethod);
        if (button.dataset.eventAction === 'judgment-team') actions.reloadJudgment();
        if (button.dataset.eventAction === 'close-judgment') actions.closeJudgment();
        if (button.dataset.eventAction === 'ask-judgment') actions.askJudgment();
        if (button.dataset.eventMatch !== undefined) actions.selectMatch(Number(button.dataset.eventMatch));
        if (button.dataset.eventRecentMatch !== undefined) actions.selectRecentMatch(Number(button.dataset.eventRecentMatch));
        if (button.dataset.eventAction === 'copy-match') actions.copyMatch();
        if (button.dataset.eventAction === 'load-gol-evidence') actions.loadGolEvidence();
        if (button.dataset.eventAction === 'start-run') actions.startRun();
        if (button.dataset.eventAction === 'focus-run') actions.focusRun();
        if (button.dataset.eventAction === 'pause-run') actions.pauseRun();
        if (button.dataset.eventAction === 'save-trade-entry') actions.saveTradeEntry();
        if (button.dataset.eventAction === 'save-trade-plan-item') actions.saveTradePlanItem();
        if (button.dataset.eventAction === 'cancel-trade-plan-edit') actions.cancelTradePlanEdit();
        if (button.dataset.eventAction === 'edit-trade-plan-item') actions.editTradePlanItem(button.dataset.tradePlanItem);
        if (button.dataset.eventAction === 'delete-trade-plan-item') actions.deleteTradePlanItem(button.dataset.tradePlanItem);
        if (button.dataset.eventAction === 'restore-trade-plan-item') actions.restoreTradePlanItem(button.dataset.tradePlanItem);
        if (button.dataset.eventAction === 'move-trade-plan-item') actions.reorderTradePlanItem(button.dataset.tradePlanItem, button.dataset.tradePlanMovement);
        if (button.dataset.eventAction === 'select-stage') selectRunStage(button.dataset.stage);
        if (button.dataset.eventAction === 'select-entry') selectTradeSection(button.dataset.entrySection, button.dataset.entryContent || '');
      };
      const onChange = (event) => {
        if (event.target?.id !== 'event-trade-plan-market') return;
        const market = event.target.value;
        const direction = root.querySelector('#event-trade-plan-direction');
        const team = root.querySelector('#event-trade-plan-team');
        if (!direction) return;
        const options = market === 'team' ? ['做多', '做空'] : ['做大', '做小'];
        direction.innerHTML = options.map((value) => `<option value="${value}">${value}</option>`).join('');
        if (team) team.disabled = market !== 'team';
      };
      const onInput = (event) => {
        if (event.target?.id === 'event-judgment-question') actions.draftJudgment?.(event.target.value);
      };
      root.addEventListener('click', onClick);
      root.addEventListener('change', onChange);
      root.addEventListener('input', onInput);
      return () => {
        root.removeEventListener('click', onClick);
        root.removeEventListener('change', onChange);
        root.removeEventListener('input', onInput);
      };
    },
    error() {
      if (results) results.innerHTML = '<div class="tk-empty" style="color:var(--red)">当前赛事资料暂时不可用。</div>';
      if (methods) methods.innerHTML = '<div class="tk-empty" style="color:var(--red)">判断入口暂时无法读取。</div>';
      if (versionUnderstanding) versionUnderstanding.innerHTML = '<div class="tk-empty" style="color:var(--red)">当前版本理解暂时无法读取。</div>';
      root.dataset.moduleStatus = 'broken';
    },
  };
  return view;
}

export function renderPreparedMaterials(payload = {}) {
  if (payload?.suppressed) return `<div class="match-workspace-head"><b>${escapeHtml(payload.title || '比赛资料')}</b></div><p class="match-desk-line">${payload.title === '赛事资料' ? '赛前回放不采用当前赛事资料' : '赛前回放不采用赛后收集资料'}</p>`;
  const material = payload?.result;
  const active = ['queued', 'running'].includes(payload?.task?.state) && !payload?.notice;
  const stateText = payload?.notice ? '暂未取得更新'
    : active ? (material ? '正在核对最新变化' : '正在准备')
      : payload?.task?.state === 'paused' ? '自动准备已暂停'
      : payload?.task?.state === 'failed' ? '暂未补齐' : material?.status === 'partial' ? '部分资料已整理' : material ? '已准备资料' : '等待准备';
  const sections = (material?.sections || []).map((section) => {
    const items = (section.items || []).map((item, index) => {
      const prose = (value) => section.id === 'analysis' ? withoutMaterialReferences(readableMaterialText(value)) : readableMaterialText(value);
      const url = safeMaterialUrl(item.url);
      const source = readableMaterialText(item.source, '公开来源');
      const verification = { verified: '已核实', unverified: '待核实', lead: '待核实线索', search_lead: '仅搜索线索', source_text: '已读原文，适用性待核对', ai_summary: 'AI整理 · 请结合原文', internal_record: '已有记录，留意时效', knowledge_extract: '已有知识提炼，非原始全文', system_inference: '系统推导 · 未确认采用', conflict: '存在分歧' }[item.verification] || '';
      const applicability = { verified: '适用性已核实', unverified_public_evidence: '公开依据适用性待核实', unverified_knowledge_extract: '知识提炼，适用性待核实', useful_background: '仅作背景，尚未证明适用于本场', stale: '资料较旧，适用性待核实' }[item.applicability] || '';
      const evidence = [source, readableMaterialTime(item.published_at), verification, applicability, item.is_excerpt ? '原文摘录' : ''].filter(Boolean).join(' · ');
      const quote = item.verification === 'ai_summary' ? readableMaterialText(item.evidence_quote) : '';
      const reason = prose(item.why_relevant);
      const conditions = [item.basis_note,
        item.conditions && !item.text?.includes(`适用条件：${item.conditions}`) && `适用条件：${item.conditions}`,
        item.counterevidence && !item.text?.includes(`反证与限制：${item.counterevidence}`) && `反证：${item.counterevidence}`].filter(Boolean).map(prose);
      const inputEvidence = (item.evidence || []).map(renderAnalysisEvidence).filter(Boolean).join('');
      const kind = item.kind === 'author_analysis' ? '作者观点' : item.kind === 'reported_information' ? '报道信息' : '';
      return `<article class="today-entry"${readingHighlight(payload.reading, `${section.id}:${index}`)}><b>${escapeHtml(readableMaterialText(item.title) || kind)}</b><p style="white-space:pre-line">${escapeHtml(prose(item.text))}</p>${reason ? `<p>${escapeHtml(reason)}</p>` : ''}${conditions.map((text) => `<p>${escapeHtml(text)}</p>`).join('')}${evidence ? `<em>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(evidence)}</a>` : escapeHtml(evidence)}</em>` : ''}${quote ? `<details><summary>查看原文依据</summary><blockquote style="white-space:pre-line">${escapeHtml(quote)}</blockquote></details>` : ''}${inputEvidence ? `<details><summary>查看分析依据</summary>${inputEvidence}</details>` : ''}</article>`;
    }).join('');
    const screened = ['digest', 'shared_digest'].includes(section.id) && section.selection_status === 'screened';
    if (!items && !screened) return '';
    const title = section.id === 'digest' && !screened ? '历史摘录（未按本场粗筛）' : readableMaterialText(section.title, '相关资料');
    const opened = screened || ['analysis', 'comparison'].includes(section.id);
    return `<details class="event-context"${opened ? ' open' : ''}><summary>${escapeHtml(title)}<small>${section.items.length} 条</small></summary><div class="event-context-body">${items || `<p>${escapeHtml(readableMaterialText(section.summary, '已粗筛，未发现值得补充的本场信息。'))}</p>`}</div></details>`;
  }).join('');
  const limitations = [...(material?.limitations || []), payload?.notice].filter(Boolean)
    .map((item) => readableMaterialText(item, '部分来源暂时无法核实，已保留可读取的资料。'));
  return `<div class="match-workspace-head"><b>${escapeHtml(payload.title || '比赛资料')}</b><span>${stateText}</span></div>
    ${renderReadingNotice(payload.reading)}
    ${payload?.task?.state === 'paused' ? `<p class="match-desk-line">${escapeHtml(readableMaterialText(payload.task.message, '原资料仍可查看。'))}</p>` : ''}
    ${material?.updated_at ? `<p class="match-desk-line">截至 ${escapeHtml(readableMaterialTime(material.updated_at))}（北京时间）</p>` : ''}
    <p class="match-desk-line">${escapeHtml(readableMaterialText(material?.summary) || (active ? '小雪正在收集、核对并整理公开资料；已有比赛信息仍可直接查看。' : '暂时没有可读取的准备成果。'))}</p>
    ${sections}
    ${limitations.length ? `<details class="event-context"><summary>尚待核实</summary><div class="event-context-body">${[...new Set(limitations)].map((text) => `<p>${escapeHtml(text)}</p>`).join('')}</div></details>` : ''}`;
}

function readingHighlight(state, position) {
  return ` data-reading-position="${escapeHtml(position)}"${state?.changedRows?.includes(position) ? ' data-reading-changed="true"' : ''}`;
}

export function renderReadingNotice(state) {
  if (!state) return '';
  const message = state.storageAvailable === false ? '本次浏览暂不能记住阅读位置。'
    : state.changed ? ['上次打开后，内容有更新。', state.changedRows.length ? '标出的内容值得再看。' : '', state.removed ? `${state.removed}条此前内容已移除，以下以更新后内容为准。` : ''].filter(Boolean).join('') : '';
  return `<p data-reading-notice class="reading-notice"${message ? '' : ' hidden'}>${escapeHtml(message)}</p>`;
}

function safeMaterialUrl(value) {
  try {
    const url = new URL(String(value || ''));
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}

function renderAnalysisEvidence(row) {
  const text = readableMaterialText(row.text);
  if (!text) return '';
  const url = safeMaterialUrl(row.url);
  const kind = { author_analysis: '作者观点', reported_information: '报道信息', official_background: '官方资料',
    version_background: '旧版本背景', team_profile_background: '旧队伍背景', cycle: '周期与近期赛果',
    confirmed_tk: '已有交易认识', candidate_rule: '待确认认识' }[row.kind] || '';
  const meta = [readableMaterialText(row.source_title || row.title || row.source), readableMaterialTime(row.published_at), kind].filter(Boolean).join(' · ');
  const notes = [readableMaterialText(row.basis_note),
    row.conditions && `适用条件：${readableMaterialText(row.conditions)}`,
    row.counterevidence && `反证与限制：${readableMaterialText(row.counterevidence)}`].filter(Boolean);
  const quote = readableMaterialText(row.evidence_quote);
  return `<div class="judgment-prose"><p style="white-space:pre-line">${escapeHtml(withoutMaterialReferences(text))}</p>${meta ? `<small>${escapeHtml(meta)}</small>` : ''}${notes.map((note) => `<p>${escapeHtml(note)}</p>`).join('')}${quote && quote !== text ? `<blockquote>${escapeHtml(quote)}</blockquote>` : ''}${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">打开出处</a>` : ''}</div>`;
}

function readableMaterialText(value, fallback = '') {
  if (value !== null && typeof value === 'object') return fallback;
  const text = String(value || '').trim();
  if (/^[\[{]/.test(text)) {
    try { if (typeof JSON.parse(text) === 'object') return fallback; } catch { /* Ordinary prose may start with punctuation. */ }
  }
  if (/\/home\/|\/api\/|Traceback|SKILL\.md|\b(?:task_id|match_key|stacktrace)\b/i.test(text)) return fallback;
  return text.replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, '')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*[-*]\s+/gm, '').replace(/\[([^\]]+)\]\((?:https?:\/\/|\/)[^)]+\)/g, '$1');
}

function withoutMaterialReferences(text) {
  // I/P/M identify private input rows, not reader-facing citations. Keep prose and real names intact.
  return text.replace(/(?<![A-Za-z0-9])[IPM]\d+(?:\s*(?:[、,，/]|与|和|及)\s*[IPM]\d+)*(?![A-Za-z0-9])/g, '')
    .replace(/[（(]\s*[）)]/g, '');
}

function readableMaterialTime(value) {
  const text = readableMaterialText(value);
  const date = text ? new Date(text) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : text;
}

function renderTradePlan(plan = {}, match = {}, editor = null) {
  const locked = plan.locked || plan.state === 'locked';
  const finalItems = plan.final?.items || [];
  const positions = new Map(finalItems.map((item) => [item.id, item.position]));
  const automatic = (plan.auto?.items || []).map((item) => renderTradePlanItem(item, positions.get(item.id), locked)).join('')
    || '<div class="trade-plan-empty">没有可直接生成的交易 TK。</div>';
  const manual = (plan.manual?.items || []).map((item) => renderTradePlanItem(item, positions.get(item.id), locked)).join('')
    || '<div class="trade-plan-empty">这场还没有手动补充。</div>';
  const teamOptions = [match.team_a, match.team_b].filter(Boolean).map((team) =>
    `<option value="${escapeHtml(team)}"${editor?.team === team ? ' selected' : ''}>${escapeHtml(team)}</option>`).join('');
  const market = editor?.market || 'team';
  const directionOptions = market === 'team'
    ? [['做多', '做多'], ['做空', '做空']]
    : [['做大', '做大'], ['做小', '做小']];
  const direction = editor?.direction || directionOptions[0][0];
  const freezeNote = plan.snapshot_missing
    ? '开赛前没有保存方案，无法还原当时使用的交易 TK。'
    : `已于 ${plan.frozen_at || '开赛时'} 锁定最终赛前方案。`;
  return `<section class="trade-plan" aria-label="赛前交易方案">
    <div class="trade-plan-head"><div><b>赛前交易方案</b><span>${locked ? freezeNote : '交易 TK 更新时，自动方案会刷新；本场内容保持不变。'}</span></div><em>${locked ? '已锁定' : `${finalItems.length} 条本场方案`}</em></div>
    <section class="trade-plan-layer auto"><h4>自动方案</h4><div class="trade-plan-list">${automatic}</div></section>
    <section class="trade-plan-layer manual"><h4>本场内容</h4><div class="trade-plan-list">${manual}</div></section>
    ${locked ? '' : `<form class="trade-plan-editor" onsubmit="return false">
      <div class="trade-plan-editor-head"><b>${editor ? '修改本场方案' : '添加本场内容'}</b><span>直接选方向即可，不会改长期交易 TK。</span></div>
      <div class="trade-plan-controls">
        <select id="event-trade-plan-market" aria-label="方案类型">
          <option value="team"${market === 'team' ? ' selected' : ''}>队伍</option>
          <option value="kills"${market === 'kills' ? ' selected' : ''}>人头</option>
          <option value="duration"${market === 'duration' ? ' selected' : ''}>时间</option>
        </select>
        <select id="event-trade-plan-team" aria-label="队伍">${teamOptions}</select>
        <select id="event-trade-plan-direction" aria-label="方向">${directionOptions.map(([value, label]) => `<option value="${value}"${direction === value ? ' selected' : ''}>${label}</option>`).join('')}</select>
        <input id="event-trade-plan-statement" maxlength="240" value="${escapeHtml(editor?.statement || '')}" placeholder="补充说明（可选）" aria-label="补充说明">
      </div>
      <div class="trade-plan-editor-actions"><button class="compare-close" data-event-action="save-trade-plan-item">${editor ? '保存修改' : '加入本场方案'}</button><button class="compare-close" data-event-action="cancel-trade-plan-edit"${editor ? '' : ' hidden'}>取消修改</button></div>
    </form>`}
  </section>`;
}

function renderTradePlanItem(item = {}, position, locked) {
  const effective = item.effective || item;
  const deleted = item.manual_state === 'deleted';
  const label = effective.market === 'team'
    ? `${effective.team || '队伍'} ${effective.direction || ''}`
    : `${effective.market === 'kills' ? '人头' : effective.market === 'duration' ? '时间' : '本场内容'} ${effective.direction || ''}`;
  const state = item.origin === 'auto' ? (item.manual_state === 'edited' ? '本场已修改' : deleted ? '本场已删除' : '来自交易 TK') : '本场手动添加';
  const controls = locked ? '' : `<div class="trade-plan-item-actions">
    ${!deleted ? `<button class="compare-close" data-event-action="move-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}" data-trade-plan-movement="up" aria-label="上移">↑</button><button class="compare-close" data-event-action="move-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}" data-trade-plan-movement="down" aria-label="下移">↓</button>` : ''}
    ${deleted ? `<button class="compare-close" data-event-action="restore-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}">恢复自动</button>` : `<button class="compare-close" data-event-action="edit-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}">编辑</button><button class="compare-close" data-event-action="delete-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}">删除</button>${item.origin === 'auto' && item.manual_state === 'edited' ? `<button class="compare-close" data-event-action="restore-trade-plan-item" data-trade-plan-item="${escapeHtml(item.id || '')}">恢复自动</button>` : ''}`}
  </div>`;
  return `<article class="trade-plan-item${deleted ? ' is-deleted' : ''}"><div class="trade-plan-item-main"><span class="trade-plan-order">${position || '—'}</span><div><b>${escapeHtml(label)}</b><small>${escapeHtml(state)}</small>${effective.statement ? `<p>${escapeHtml(effective.statement)}</p>` : ''}</div></div>${controls}</article>`;
}

function renderTradePlanReview(review = null) {
  if (!review || review.status === 'pre_match') return '';
  if (review.status !== 'ok') return `<section class="trade-plan-review"><b>赛后复盘</b><span>${escapeHtml(review.reason || '赛果尚未导入。')}</span></section>`;
  const items = (review.items || []).map((item) => {
    const label = item.market === 'team' ? `${item.team} ${item.direction}` : `${item.market === 'kills' ? '人头' : '时间'} ${item.direction}`;
    const outcome = item.outcome === 'matched' ? '符合' : item.outcome === 'missed' ? '不符合' : '无数据';
    return `<li><b>${escapeHtml(label)}</b><span>${escapeHtml(outcome)} · ${escapeHtml(item.review_reason || '')}</span></li>`;
  }).join('') || '<li><span>最终赛前方案为空。</span></li>';
  const suggestions = (review.tk_suggestions || []).map((item) => `<li><b>${escapeHtml(item.recommendation || '')}</b><span>${escapeHtml(item.reason || '')}</span></li>`).join('') || '<li><span>本场没有关联的交易 TK。</span></li>';
  return `<section class="trade-plan-review"><b>赛后复盘</b><span>只对照锁定的赛前方案；没有可靠人头或时长赛果时会明确留空。</span><ul>${items}</ul><h4>交易 TK 建议</h4><ul>${suggestions}</ul><em>建议不会自动改动长期交易 TK。</em></section>`;
}

function renderFramework(target, framework = {}) {
  if (!target) return;
  const content = String(framework.content || '').trim();
  const historical = framework.status === 'historical';
  const summary = framework.summary || (historical ? '这是此前赛段的参考资料，不作为本届当前框架。' : content ? '当前赛段框架已建立，可展开查看全文。' : '当前还没有可用的赛段框架。');
  target.classList.toggle('exists', Boolean(content));
  target.innerHTML = `
    <div class="framework-head"><b>${historical ? '历史赛段参考' : '当前赛段框架'}</b><span>${historical ? '仅供查阅，不作为本届当前判断' : '阶段背景，不是每场必须照抄'}</span></div>
    <p class="framework-summary">${escapeHtml(summary)}</p>
    ${content ? `<details class="framework-details"><summary>展开全文</summary><div>${escapeHtml(content)}</div></details>` : '<div class="framework-empty">先和小雪聊清阶段判断，确认后再形成框架。</div>'}
    <em>${escapeHtml(framework.updated_at ? `更新于 ${framework.updated_at}` : '尚未记录更新时间')} · ${escapeHtml(framework.boundary || '需要变化时再和小雪讨论并确认。')}</em>`;
}

function renderVersionUnderstanding(target, data = null) {
  if (!target) return;
  const item = data?.item;
  const mainline = data?.current_mainline;
  if (!item) {
    target.innerHTML = '<div class="framework-empty">当前版本理解暂时读不到；不影响查看赛事和单场资料。</div>';
    return;
  }
  const title = mainline?.title || item.topic || '当前版本理解';
  const content = mainline?.content || item.content || '';
  target.innerHTML = `<div class="framework-head"><b>当前版本理解</b><span>${escapeHtml(item.created_at ? `更新于 ${item.created_at}` : '时间暂未记录')}</span></div>
    <p class="framework-summary">${escapeHtml(item.topic || '统一版本理解')}</p>
    <details class="framework-details"><summary>展开阅读：${escapeHtml(title)}</summary><div class="pc-version-content">${versionContentHtml(content)}</div></details>
    <em>这是当前赛事和单场判断共用的版本依据；需要调整时直接和小雪讨论。</em>`;
}

function versionContentHtml(content) {
  const lines = String(content || '').trim().split('\n').map(line => line.trim());
  if (!lines.some(Boolean)) return '<p>当前版本正文暂时读不到</p>';
  const output = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    if (!line) { index += 1; continue; }
    if (/^(#{1,6})\s+/.test(line)) {
      output.push(`<h4>${versionInlineHtml(line.replace(/^#{1,6}\s+/, ''))}</h4>`);
      index += 1;
      continue;
    }
    const listMatch = line.match(/^([-*]|\d+\.)\s+(.+)/);
    if (listMatch) {
      const ordered = /^\d+\.$/.test(listMatch[1]);
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(ordered ? /^\d+\.\s+(.+)/ : /^[-*]\s+(.+)/);
        if (!item) break;
        items.push(`<li>${versionInlineHtml(item[1])}</li>`);
        index += 1;
      }
      output.push(`<${ordered ? 'ol' : 'ul'}>${items.join('')}</${ordered ? 'ol' : 'ul'}>`);
      continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index] && !/^(#{1,6})\s+|^[-*]\s+|^\d+\.\s+/.test(lines[index])) {
      paragraph.push(versionInlineHtml(lines[index]));
      index += 1;
    }
    output.push(`<p>${paragraph.join('<br>')}</p>`);
  }
  return output.join('');
}

function versionInlineHtml(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderMethods(target, cards = []) {
  if (!target) return;
  target.innerHTML = renderJudgmentMethods(cards);
}

export function renderJudgmentMethods(cards = []) {
  const renderCard = (card) => {
    const ready = card.status === 'ready' && card.id;
    return `<article class="method-card"><b>${escapeHtml(readableMaterialText(card.title, '判断视角'))}</b><p>${escapeHtml(readableMaterialText(card.purpose))}</p>${ready ? `<button type="button" class="compare-close" data-event-method="${escapeHtml(card.id)}" aria-pressed="false">进入判断</button>` : `<small>${card.channel === 'xiaoxue_chat' ? '原能力仍可与小雪聊；这里尚未接通' : '此入口尚未接通'}</small>`}</article>`;
  };
  const sorted = [...cards].sort((a, b) => (Number(a.order) || 0) - (Number(b.order) || 0));
  const primary = sorted.filter((card) => card.primary !== false);
  const other = sorted.filter((card) => card.primary === false);
  return (primary.length ? `<div class="event-methods-list judgment-primary-methods">${primary.map(renderCard).join('')}</div>` : '') + (other.length ? `<details class="judgment-other-methods"><summary>其他已有能力</summary><div class="event-methods-list">${other.map(renderCard).join('')}</div></details>` : '')
    || '<div class="tk-empty">暂时没有可进入的判断视角。</div>';
}

export function renderJudgmentContext(payload = {}) {
  const method = payload.method || {};
  const object = payload.object || {};
  const match = object.match || {};
  const matchLabel = match.team_a && match.team_b ? `${match.team_a} vs ${match.team_b}` : '';
  const subject = [object.event, object.team, matchLabel].filter(Boolean).map((value) => readableMaterialText(value)).filter(Boolean).join(' · ');
  const needed = (payload.needed || []).map((key) => ({ team: '在上方填入想看的队伍，再点“查看队伍”', match: '选择上方一场已确认比赛，再进入这里', event: '当前赛事尚未确定，请稍后再看' }[key] || '当前对象尚未确定')).join('；');
  const contents = (payload.contents || []).map((item, index) => {
    const recognition = { confirmed: '已标记认可', user_confirmed: '你已认可', user_record: '你的原记录', candidate: '待确认', system: '系统推导 · 未确认采用' }[item.recognition] || '未标记认可';
    const published = readableMaterialTime(item.published_at);
    const updated = readableMaterialTime(item.updated_at);
    const meta = [readableMaterialText(item.source_label), published ? `发布于 ${published}` : updated ? `更新于 ${updated}` : '', recognition].filter(Boolean).join(' · ');
    const url = safeMaterialUrl(item.url);
    const quote = readableMaterialText(item.evidence_quote);
    const evidence = url || quote ? `<details class="judgment-origin"><summary>查看出处</summary>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">打开原文</a>` : ''}${quote ? `<blockquote>${escapeHtml(quote)}</blockquote>` : ''}</details>` : '';
    const text = readableMaterialText(item.text);
    const body = `<div class="judgment-prose">${versionContentHtml(text)}</div>${evidence}`;
    const background = ['version', 'version_understanding', 'team_profile', 'profile'].includes(item.kind) && text.length > 650;
    return `<article class="judgment-source"${readingHighlight(payload.reading, `content:${index}`)}><h4>${escapeHtml(readableMaterialText(item.title, '已有内容'))}</h4><p class="judgment-source-meta">${escapeHtml(meta)}</p>${background ? `<p class="judgment-source-meta">已有长期认识，适用本届前需核对。</p><details data-reading-background><summary>展开已有内容</summary>${body}</details>` : body}</article>`;
  }).join('');
  const analysis = (payload.analysis || []).map((item, index) => {
    const text = typeof item === 'string' ? item : item.text || item.summary || item.content || '';
    const evidence = (item.evidence || []).map(renderAnalysisEvidence).filter(Boolean).join('');
    return `<article class="judgment-inference"${readingHighlight(payload.reading, `analysis:${index}`)}><h4>${escapeHtml(readableMaterialText(item.title, '相关解释'))}</h4><small>系统推导，不等于你的判断</small><div class="judgment-prose">${versionContentHtml(withoutMaterialReferences(readableMaterialText(text)))}</div>${evidence ? `<details class="judgment-origin"><summary>所用依据</summary>${evidence}</details>` : ''}</article>`;
  }).join('');
  const limitations = [...new Set((payload.limitations || []).map((item) => readableMaterialText(item, '部分依据暂时无法核实。')).filter(Boolean))];
  return `<div class="judgment-reader-heading"><div><h3>${escapeHtml(readableMaterialText(method.title, '对应内容'))}</h3>${subject ? `<p>${escapeHtml(subject)}</p>` : ''}</div><button type="button" class="compare-close" data-event-action="close-judgment">返回比赛</button></div>
    ${renderReadingNotice(payload.reading)}
    ${needed ? `<p class="judgment-notice">${escapeHtml(needed)}</p>` : ''}
    ${limitations.length ? `<div class="judgment-notice">${limitations.map((text) => `<p>${escapeHtml(text)}</p>`).join('')}</div>` : ''}
    ${contents || (!needed && payload.status !== 'unavailable' ? '<p class="tk-empty">当前还没有可读取的对应内容，不会代填判断。</p>' : '')}
    ${analysis}
    ${payload.discussion_available ? '<p class="judgment-save-note">可以继续讨论；仅保留本次会话，未自动保存或采用。要长期修改，请沿用小雪对应内容的原维护入口。</p>' : ''}`;
}

export function renderJudgmentDiscussion(payload = {}) {
  const references = [...new Set((payload.references || []).map((item) => readableMaterialText(item.title)).filter(Boolean))];
  const basis = [payload.method_title ? `讨论视角：${readableMaterialText(payload.method_title)}` : '', payload.basis_updated ? '这条回答所用依据已有更新' : ''].filter(Boolean).join(' · ');
  return `<article class="judgment-exchange">${basis ? `<small>${escapeHtml(basis)}</small>` : ''}<b>你的问题</b><p>${escapeHtml(readableMaterialText(payload.question))}</p><b>小雪</b><div class="judgment-prose">${versionContentHtml(discussionDisplayText(readableMaterialText(payload.answer)))}</div>${references.length ? `<small>参考：${escapeHtml(references.join('、'))}</small>` : ''}<small>本次讨论未保存，不代表你已认可或采用。</small></article>`;
}

export function discussionDisplayText(value) {
  const text = String(value || '').replace(/\binputs\b/gi, '现有资料').replace(/三维/g, '旧资料项（现归队伍画像）');
  if (text.length <= 300 || /[\r\n]/.test(text)) return text;
  const sentences = text.split(/(?<=[。！？])/).filter(Boolean);
  return sentences.map((sentence, index) => sentence + (index % 2 === 1 && index < sentences.length - 1 ? '\n\n' : '')).join('');
}

function renderRecentList(target, recentMatches) {
  const history = target.closest('.event-history');
  if (history) history.hidden = !recentMatches.length;
  target.innerHTML = recentMatches.length
    ? recentMatches.map((item, index) => renderRecentMatchButton(item, index)).join('')
    : '';
}

function renderMatchButton(item, index) {
  const match = item.match || {};
  const materialState = { prepared: '已整理', partial: '部分整理', not_started: '暂无可用正文' }[item.preparation?.state];
  const materialNote = materialState ? '资料：' + materialState + (item.preparation.reason ? ' · ' + item.preparation.reason : '') : '';
  const ts = item.ts || {};
  const compare = ts.compare || {};
  const meta = [formatMatchTime(match.time), match.region, match.format].filter(Boolean).join(' · ');
  if (item.pending) {
    return `<article class="event-match-button event-fixture-card is-pending">
    <span class="event-match-kicker">${escapeHtml(match.match_date || match.date || '近期')} · 待定</span>
    <b>${escapeHtml(match.team_a || '待定')} <i>vs</i> ${escapeHtml(match.team_b || '待定')}</b>
    <span class="event-match-meta">${escapeHtml(meta)}</span>
    <em class="event-match-summary">${escapeHtml(item.pending_reason || '对阵未定，名额产生后再看这场。')}</em>
  </article>`;
  }
  const line = ts.available
    ? compare.comparable === false
      ? compare.reason || '不同赛区的实力分数不能直接比较'
      : `${compare.stronger || '双方'} · 综合实力差 ${format(compare.power_diff)}`
    : ts.reason || '未能读取两队实力资料';
  const plan = item.trade_plan?.final || {};
  const planBits = [
    ...(plan.team || []).map((value) => `${value.team} ${value.direction}`),
    ...(plan.kills || []).map((value) => `人头${value.direction}`),
    ...(plan.duration || []).map((value) => `时间${value.direction}`),
  ];
  const planLine = planBits.length ? ` · ${planBits.join(' / ')}` : '';
  return `<button class="event-match-button event-fixture-card" data-event-match="${index}" aria-pressed="false">
    <span class="event-match-kicker">${escapeHtml(match.match_date || match.date || '近期')}</span>
    <b>${escapeHtml(match.team_a || '')} <i>vs</i> ${escapeHtml(match.team_b || '')}</b>
    <span class="event-match-meta">${escapeHtml(meta)}</span>
    ${materialNote ? '<span class="event-match-meta">' + escapeHtml(materialNote) + '</span>' : ''}
    <em class="event-match-summary">${escapeHtml(`实力参考：${line}${planLine}`)}</em>
  </button>`;
}

function renderRecentMatchButton(item, index) {
  const match = item.match || {};
  const state = item.activity_status === 'active' ? '正在查看' : '已暂存';
  return `<button class="event-match-button event-recent-card" data-event-recent-match="${index}">
    <b>${escapeHtml(match.team_a || '')} <i>vs</i> ${escapeHtml(match.team_b || '')}</b>
    <span class="event-match-meta">${escapeHtml([match.match_date, match.match_time, match.event].filter(Boolean).join(' · '))}</span>
    <em class="event-match-summary">${escapeHtml(state)}</em>
  </button>`;
}

function formatMatchTime(value) {
  const text = String(value || '').trim();
  const time = text.match(/(?:T|\s)(\d{1,2}:\d{2})(?::\d{2})?$/);
  return time ? time[1] : text;
}

function renderTs(team) {
  return `综合实力 ${format(team.power_score)}`;
}

function renderSeriesContext(context = {}) {
  if (!context?.is_bo5) return '';
  const items = (context.items || []).filter(Boolean);
  if (!items.length) return '';
  return `<div class="match-desk-notes"><b>${escapeHtml(context.title || 'BO5 赛前资料')}</b>${items.map((item) => `<span>${escapeHtml(presentText(item))}</span>`).join('')}</div>`;
}

function renderTeamEvidence(team) {
  if (!team?.team) return '';
  const starters = (team.starters || []).map((player) => `${player.role || ''} ${player.name || ''}`.trim()).filter(Boolean).join(' / ');
  const styleUnderstanding = (team.three_dimensional?.items || [])
    .map((item) => [item.label, item.value].filter(Boolean).join('：')).filter(Boolean).join('；');
  if (!starters && !styleUnderstanding) return '';
  return `<div class="match-desk-team"><b>${escapeHtml(team.team)}</b>${starters ? `<span>登记名单（不代表本场首发）：${escapeHtml(starters)}</span>` : ''}${styleUnderstanding ? `<span>风格/版本理解：${escapeHtml(styleUnderstanding)}</span>` : ''}</div>`;
}

function renderTradingFramework(framework = {}) {
  const items = framework.items || [];
  if (!items.length) return '';
  return `<div class="match-desk-notes"><b>本场已有资料</b>${items.map((item) => {
    const prefix = item.scope_label || '';
    return `<span>${escapeHtml(presentText([prefix, item.statement].filter(Boolean).join('：')))}</span>`;
  }).join('')}</div>`;
}

function presentText(value) {
  return String(value || '').replace(/交易\s*TK/gi, '已有资料');
}

function renderGolEvidence(payload = null) {
  const series = payload?.gol_series;
  if (!series?.games?.length) return '';
  const rows = series.games.map((game) => {
    const sides = (game.teams || []).map((team) => `${team.team} ${team.result} · ${team.picks.join('/')}`).join('；');
    return `<li><b>第 ${escapeHtml(String(game.game_id))} 局 · ${escapeHtml(game.duration || '')} · ${escapeHtml(game.patch || '')}</b><span>${escapeHtml(sides)}</span></li>`;
  }).join('');
  const mismatch = payload?.association?.conflict ? '<span class="basis-hint">这页双方与当前比赛不一致，仅供核对。</span>' : '';
  return `<details class="match-basis" open><summary>Gol.gg 逐局事实</summary>${mismatch}<span class="basis-hint">按需查询的外部页面事实，不会写入本场或长期资料。</span><ul class="match-run-facts">${rows}</ul><a href="${escapeHtml(series.source_url || '')}" target="_blank" rel="noreferrer">查看来源</a></details>`;
}

function renderMatchRun(run = {}, viewState = {}) {
  if (!run?.exists) {
    return `<section class="match-run">
      <div class="match-workspace-head"><b>单场线程</b><span>只服务这场比赛，随时可以停下。</span></div>
      <div class="match-run-empty">打开后按你正在聊的部分查看资料；不需要把每一项都填完。</div>
      <div class="match-workspace-actions"><button class="compare-close" data-event-action="start-run">打开这场</button><span>长期认识仍回到队伍、版本、交易 TK 和方法说明。</span></div>
    </section>`;
  }
  const stages = normalizeStages(run.guide?.stages);
  const entries = run.entries || [];
  const activeStage = viewState.activeRunStage || stageForSection(viewState.activeSection || run.focus);
  const section = viewState.activeSection && viewState.activeSection !== 'overview'
    ? viewState.activeSection : firstModule(stages[activeStage]);
  const tabs = Object.entries(stages).map(([stage, meta]) => `<button class="run-stage-tab${stage === activeStage ? ' active' : ''}" data-event-action="select-stage" data-stage="${stage}" data-run-stage-tab="${stage}" aria-selected="${stage === activeStage ? 'true' : 'false'}">${escapeHtml(meta.label)}</button>`).join('');
  const panels = Object.entries(stages).map(([stage, meta]) => {
    const stageEntries = entries.filter((entry) => entry.stage === stage || (!entry.stage && stageForSection(entry.section) === stage));
    const modules = meta.modules || [];
    const chips = modules.map((module) => {
      const saved = stageEntries.find((entry) => entry.section === module.id);
      return `<button class="run-entry-chip${module.id === section ? ' active' : ''}${saved ? ' saved' : ''}" data-event-action="select-entry" data-entry-section="${escapeHtml(module.id)}" data-entry-content="${escapeHtml(saved?.content || '')}">${escapeHtml(module.label)}${saved ? '<i>已记</i>' : ''}</button>`;
    }).join('');
    const savedHtml = stageEntries.length
      ? `<ul class="match-stage-entries">${stageEntries.map((entry) => `<li><b>${escapeHtml(entry.label || '')}</b><span>${escapeHtml(entry.content || '')}</span><em>${escapeHtml(entry.updated_at || '')}</em></li>`).join('')}</ul>`
      : '<div class="match-run-empty">还没和小雪聊到这里。</div>';
    return `<section class="match-stage-panel" data-run-stage-panel="${stage}"${stage === activeStage ? '' : ' hidden'}>
      <p class="stage-purpose">${escapeHtml(meta.purpose || '')}</p>
      <div class="run-entry-chips">${chips}</div>${savedHtml}
    </section>`;
  }).join('');
  const focused = entries.find((entry) => entry.section === section);
  const sectionOptions = Object.values(stages).flatMap((stage) => stage.modules || []).map((module) =>
    `<option value="${escapeHtml(module.id)}"${module.id === section ? ' selected' : ''}>${escapeHtml(module.label)}</option>`).join('');
  const facts = (run.facts || []).map((fact) => {
    const time = fact.as_of ? ` · ${fact.as_of}` : '';
    return `<li class="match-run-fact status-${escapeHtml(fact.status || 'needs_review')}">
      <b>${escapeHtml(fact.label)}</b><span>${escapeHtml(fact.value)}</span>
      <em>${escapeHtml(SOURCE_LABELS[fact.source] || '已有资料')}${escapeHtml(time)}</em>
      <small>${escapeHtml(statusLabel(fact.status))}：${escapeHtml(fact.action || '')}</small>
    </li>`;
  }).join('');
  const runAction = run.activity_status === 'active'
    ? '<button class="compare-close" data-event-action="pause-run">先放下这场</button>'
    : '<button class="compare-close" data-event-action="start-run">回到这场</button>';
  return `<section class="match-run">
    <div class="match-workspace-head"><b>单场线程</b><span>${run.activity_status === 'active' ? '当前正在聊' : '已暂存，可随时回来'}</span></div>
    <div class="match-run-next"><b>按阶段查看</b><span>先看需要的部分，写下内容才会保存。</span></div>
    <div class="run-stage-tabs" role="tablist" aria-label="单场阶段">${tabs}</div>
    <div class="match-stage-panels">${panels}</div>
    <div class="match-change-form match-trade-entry-form">
      <select id="event-trade-section" hidden aria-label="交易环节">${sectionOptions}</select>
      <textarea id="event-trade-content" maxlength="1200" placeholder="只写现在需要整理的这一项" aria-label="当前阶段记录">${escapeHtml(focused?.content || '')}</textarea>
      <button class="compare-close" data-event-action="focus-run">切到这一项</button>
      <button class="compare-close" data-event-action="save-trade-entry">只更新这一项</button>
    </div>
    <details class="match-basis"><summary>本场依据</summary><span class="basis-hint">TS、队伍资料、交易 TK 和赛果只作为依据，单场判断仍由你和小雪讨论。</span>${facts ? `<ul class="match-run-facts">${facts}</ul>` : '<div class="match-run-empty">暂时没有可用依据。</div>'}</details>
    <div class="match-workspace-actions">${runAction}<span>有错误直接告诉小雪具体内容，不需要记编号。</span></div>
  </section>`;
}

function normalizeStages(stages = {}) {
  return Object.fromEntries(Object.entries(FALLBACK_STAGES).map(([stage, fallback]) => {
    const supplied = stages[stage] || {};
    const modules = supplied.modules?.length
      ? supplied.modules.map((item) => typeof item === 'string' ? { id: item, label: item } : item)
      : fallback.modules.map(([id, label]) => ({ id, label }));
    return [stage, { label: supplied.label || fallback.label, purpose: supplied.purpose || fallback.purpose, modules }];
  }));
}

function firstModule(stage = {}) {
  return stage.modules?.[0]?.id || 'version';
}

function stageForSection(section = '', stages = FALLBACK_STAGES) {
  for (const [stage, meta] of Object.entries(stages || {})) {
    if ((meta.modules || []).some((item) => (Array.isArray(item) ? item[0] : item.id) === section)) return stage;
  }
  return 'pre';
}

function statusLabel(status = '') {
  return ({ active: '已读取', excluded: '本场不用', needs_review: '待你核对', missing: '未找到', user_override: '已按你修正' })[status] || status;
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
