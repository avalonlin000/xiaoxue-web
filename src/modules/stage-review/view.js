const TARGET_LABELS = {
  team: '队伍', player: '选手', version: '版本', trading_method: '交易方法',
};

export function createStageReviewView(root) {
  if (!root) throw new Error('阶段整理入口不存在');
  const list = root.querySelector('#stage-review-list');
  const summary = root.querySelector('#stage-review-summary');
  const message = root.querySelector('#stage-review-message');
  return {
    loading() {
      if (summary) summary.textContent = '正在读取待整理内容…';
      if (list) list.innerHTML = '<div class="tk-empty">读取中…</div>';
    },
    render(payload = {}) {
      const candidates = payload.candidates || [];
      const tradingTK = payload.tradingTK || [];
      if (summary) summary.textContent = `知识候选 ${candidates.length} 条 · 交易 TK ${tradingTK.length} 条`;
      if (!list) return;
      if (!candidates.length && !tradingTK.length) {
        list.innerHTML = '<div class="tk-empty">当前没有待整理知识或交易 TK。</div>';
        return;
      }
      const groups = groupCandidates(candidates);
      const candidateHtml = [...groups.entries()].map(([target, items]) => `
        <section class="stage-review-group">
          <h3>${escapeHtml(target)}</h3>
          ${items.map(renderCandidate).join('')}
        </section>`).join('');
      const tradingTKHtml = tradingTK.length ? `<section class="stage-review-group">
        <h3>交易 TK</h3>
        ${tradingTK.map(renderTradingTK).join('')}
      </section>` : '';
      list.innerHTML = candidateHtml + tradingTKHtml;
    },
    setMessage(text = '', kind = '') {
      if (!message) return;
      message.textContent = text;
      message.dataset.kind = kind;
    },
    bind(actions) {
      const onClick = (event) => {
        const button = event.target.closest('[data-stage-action]');
        if (!button) return;
        if (button.dataset.stageAction === 'refresh') actions.refresh();
        if (button.dataset.stageAction === 'copy-prompt') actions.copyPrompt();
        if (button.dataset.stageAction === 'ignore') actions.ignore(Number(button.dataset.candidateId));
        if (button.dataset.stageAction === 'confirm-tk') actions.updateTradingTK(button.dataset.filename, 'confirmed');
        if (button.dataset.stageAction === 'invalidate-tk') actions.updateTradingTK(button.dataset.filename, 'invalid');
      };
      root.addEventListener('click', onClick);
      return () => root.removeEventListener('click', onClick);
    },
    error(error) {
      if (summary) summary.textContent = '阶段整理暂时不可用';
      if (list) list.innerHTML = `<div class="tk-empty">${escapeHtml(error?.message || '读取失败')}</div>`;
      root.dataset.moduleStatus = 'broken';
    },
  };
}

function groupCandidates(candidates) {
  const groups = new Map();
  candidates.forEach((candidate) => {
    const target = `${TARGET_LABELS[candidate.target_type] || candidate.target_type} · ${candidate.target_name}`;
    if (!groups.has(target)) groups.set(target, []);
    groups.get(target).push(candidate);
  });
  return groups;
}

function renderCandidate(candidate) {
  const match = candidate.match || {};
  const source = [
    `${match.team_a || ''} vs ${match.team_b || ''}`,
    match.match_date,
    candidate.reason,
  ].filter(Boolean).join(' · ');
  return `<article class="stage-candidate">
    <b>${escapeHtml(candidate.topic || '')}</b>
    <span>${escapeHtml(candidate.observation || '')}<em>${escapeHtml(source)}</em></span>
    <button class="compare-close" data-stage-action="ignore" data-candidate-id="${candidate.id}">本轮不处理</button>
  </article>`;
}

function renderTradingTK(item) {
  const status = ({ candidate: '待验证', confirmed: '已确认', invalid: '已失效' })[item.status] || item.status;
  const filename = escapeHtml(item.filename || '');
  const actions = item.editable === false ? '' : item.status === 'candidate'
    ? `<button class="compare-close" data-stage-action="confirm-tk" data-filename="${filename}">确认可用</button>
       <button class="compare-close" data-stage-action="invalidate-tk" data-filename="${filename}">标记失效</button>`
    : item.status === 'confirmed'
      ? `<button class="compare-close" data-stage-action="invalidate-tk" data-filename="${filename}">标记失效</button>`
      : '';
  return `<article class="stage-candidate">
    <b>${escapeHtml(status)} · ${escapeHtml(item.scope_label || '')}${item.scope_label ? ' · ' : ''}${escapeHtml(item.statement || '')}</b>
    <span>${escapeHtml(item.context || '未限定适用范围')}<em>${escapeHtml(item.updated_at || '')}</em></span>
    ${actions}
  </article>`;
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}
