export function createCurrentEventView(root) {
  if (!root) throw new Error('当前赛事入口不存在');
  const results = root.querySelector('#event-knowledge-results');
  const plan = root.querySelector('#event-plan-status');
  return {
    loading() { if (results) results.innerHTML = '<div class="tk-empty">正在读取 LPL 资料…</div>'; },
    render(payload) {
      const { context = {}, items = [] } = payload || {};
      setText(root, '#event-name', context.event || '当前赛事');
      setText(root, '#event-phase', context.phase || '');
      if (plan) {
        plan.classList.toggle('exists', context.plan_status === 'ready');
        plan.innerHTML = context.plan_status === 'ready'
          ? `<b>${escapeHtml(context.plan_title || '当前交易预案')}</b><span>${escapeHtml(context.plan_content || '')}</span><em>${escapeHtml(context.plan_updated_at ? `更新于 ${context.plan_updated_at}` : '')}</em>`
          : '<b>大周期交易预案：尚未制定</b><span>先与小雪讨论并确认完整预案；工作台不会自动编造。</span>';
      }
      if (!results) return;
      results.innerHTML = items.length
        ? items.map((item) => `<article class="today-entry exists"><b>${escapeHtml(item.title)}</b><span class="today-summary">${escapeHtml(item.summary.slice(0, 240))}</span><em>${escapeHtml(item.date)}</em></article>`).join('')
        : '<div class="tk-empty">暂未找到 LPL 资料，不影响其他窗口使用。</div>';
    },
    error() {
      if (results) results.innerHTML = '<div class="tk-empty" style="color:var(--red)">当前赛事资料暂时不可用，其他窗口可以继续使用。</div>';
      root.dataset.moduleStatus = 'broken';
    },
  };
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
