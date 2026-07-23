import { buildFilterSummary, gameLabel, getMarketNoteResult, stripResultLine } from './service.js';

export function createMarketNotesView(root) {
  if (!root) throw new Error('盘口记录入口不存在');
  const byId = (id) => root.querySelector(`#${id}`);
  const elements = {
    list: byId('trade-list'), message: byId('trade-msg'), summary: byId('trade-filter-summary'),
    match: byId('trade-match'), time: byId('trade-time'), confidence: byId('trade-confidence'),
    direction: byId('trade-winner'), total: byId('trade-total'), score: byId('trade-score'),
    result: byId('trade-result'), reason: byId('trade-reason'), review: byId('trade-review'),
    resultFilter: byId('trade-result-filter'), keywordFilter: byId('trade-keyword-filter'),
    teamNote: byId('team-trading-note-input'), teamNoteMessage: byId('team-trading-note-msg'),
  };

  return {
    root,
    readForm() {
      return {
        matchName: elements.match?.value || '', matchTime: elements.time?.value || '',
        confidence: elements.confidence?.value || '中', direction: elements.direction?.value || '',
        totalLean: elements.total?.value || '放弃', scoreNote: elements.score?.value || '',
        result: elements.result?.value || '未结算', reason: elements.reason?.value || '',
        review: elements.review?.value || '',
      };
    },
    readTeamNote: () => String(elements.teamNote?.value || '').trim(),
    setMessage(message, kind = '') { setText(elements.message, message, kind); },
    setTeamNoteMessage(message, kind = '') { setText(elements.teamNoteMessage, message, kind); },
    clearTeamNote() { if (elements.teamNote) elements.teamNote.value = ''; },
    clearForm() {
      [elements.match, elements.direction, elements.score, elements.reason, elements.review]
        .forEach((element) => { if (element) element.value = ''; });
      if (elements.total) elements.total.value = '放弃';
      if (elements.result) elements.result.value = '未结算';
    },
    applyPrefill(prefill) {
      if (elements.match) elements.match.value = prefill.matchName || '';
      if (elements.time && prefill.matchTime) elements.time.value = prefill.matchTime;
      if (elements.reason && !elements.reason.value) elements.reason.value = prefill.reason || '';
    },
    setGame(game) {
      root.querySelectorAll('.trade-game').forEach((button) => {
        button.classList.toggle('active', button.dataset.game === game);
      });
    },
    renderLoading() {
      if (elements.list) elements.list.innerHTML = '<div class="tk-empty">加载盘口记录中…</div>';
    },
    renderError(message = '盘口记录加载失败') {
      if (elements.list) elements.list.innerHTML = `<div class="tk-empty" style="color:var(--red)">${escapeHtml(message)}</div>`;
    },
    renderRecords(records, total, filters) {
      if (elements.summary) elements.summary.textContent = buildFilterSummary(total, records.length, filters);
      if (!elements.list) return;
      if (!records.length) {
        elements.list.innerHTML = total
          ? '<div class="tk-empty">没有符合筛选的盘口记录</div>'
          : '<div class="tk-empty">暂无盘口记录</div>';
        return;
      }
      elements.list.innerHTML = records.map(renderRecord).join('');
    },
    bind(actions) {
      const disposers = [];
      const on = (element, type, handler) => {
        if (!element) return;
        element.addEventListener(type, handler);
        disposers.push(() => element.removeEventListener(type, handler));
      };
      root.querySelectorAll('.trade-game').forEach((button) => on(button, 'click', () => actions.setGame(button.dataset.game)));
      on(elements.resultFilter, 'change', () => actions.setResultFilter(elements.resultFilter.value));
      on(elements.keywordFilter, 'input', () => actions.setKeywordFilter(elements.keywordFilter.value));
      bindAction(root, disposers, 'refresh', 'loadTrades()', () => actions.load());
      bindAction(root, disposers, 'save', 'saveTradeRecord()', () => actions.save());
      bindAction(root, disposers, 'prefill', 'prefillTradeFromTeam()', () => actions.prefill());
      bindAction(root, disposers, 'save-team-note', 'saveTeamTradingNote()', () => actions.saveTeamNote());
      ['7d', '30d', 'all'].forEach((range) => {
        bindAction(root, disposers, `range-${range}`, `setTradeRange('${range}')`, () => actions.setRange(range));
      });
      on(elements.list, 'click', (event) => {
        const button = event.target.closest('[data-market-action]');
        if (!button) return;
        const id = Number(button.dataset.id);
        if (button.dataset.marketAction === 'delete') actions.deleteRecord(id);
        if (button.dataset.marketAction === 'tk-draft') actions.requestTkDraft(id);
      });
      return () => disposers.splice(0).forEach((dispose) => dispose());
    },
  };
}

function bindAction(root, disposers, action, legacyOnclick, handler) {
  const legacy = legacyOnclick.replace(/(["\\])/g, '\\$1');
  root.querySelectorAll(`[data-market-action="${action}"], [onclick="${legacy}"]`).forEach((element) => {
    element.addEventListener('click', handler);
    disposers.push(() => element.removeEventListener('click', handler));
  });
}

function renderRecord(record) {
  const time = String(record.match_time || record.created_at || '').replace('T', ' ').slice(0, 16);
  const result = getMarketNoteResult(record);
  const review = stripResultLine(record.review || '');
  const reason = [record.reason, review ? `备注：${review}` : ''].filter(Boolean).join('\n');
  return `<div class="trade-item" id="trade-${Number(record.id)}">
    <div class="trade-item-head">
      <div><div class="trade-match">${escapeHtml(record.match_name)}</div><div class="trade-meta">${escapeHtml(gameLabel(record.game))} · ${escapeHtml(time)}</div></div>
      <span class="trade-pill gray">盘口记录</span>
    </div>
    <div class="trade-picks">
      <span class="trade-pill">方向：${escapeHtml(record.direction || '未写')}</span>
      <span class="trade-pill blue">大小：${escapeHtml(record.total_lean || '放弃')}</span>
      <span class="trade-pill gray">比分：${escapeHtml(record.score_note || '-')}</span>
      <span class="trade-pill gray">信心：${escapeHtml(record.confidence || '中')}</span>
      <span class="trade-pill gray">结果：${escapeHtml(result)}</span>
    </div>
    <div class="trade-reason">${escapeHtml(reason || '无备注')}</div>
    <div class="trade-item-actions">
      <button data-market-action="tk-draft" data-id="${Number(record.id)}">沉淀TK</button>
      <button class="danger" data-market-action="delete" data-id="${Number(record.id)}">删除</button>
    </div>
  </div>`;
}

function setText(element, message, kind) {
  if (!element) return;
  element.textContent = message || '';
  element.dataset.kind = kind;
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}
