export function createDailyView(root) {
  const status = root.querySelector('#today-content-status');
  const state = root.querySelector('#today-content-state');
  const list = root.querySelector('#today-entry-list');

  return {
    loading() {
      if (status) status.textContent = '正在读取已经整理好的内容';
    },
    render(view) {
      if (status) status.textContent = view.title;
      if (state) state.textContent = view.detail;
      if (!list) return;
      list.innerHTML = view.items.length
        ? view.items.map((item) => `<article class="today-entry exists"><b>${escapeHtml(item.title || '赛前判断')}</b><span class="today-summary">${escapeHtml(item.summary || '内容已生成，暂无摘要。')}</span></article>`).join('')
        : '<div class="today-empty">还没有需要你看的内容。有新的赛前判断时，小雪会把摘要放到这里。</div>';
    },
    error() {
      if (status) status.textContent = '今日赛前内容暂时无法读取';
      if (state) state.textContent = '稍后刷新即可；这里不会用旧内容代替。';
      if (list) list.innerHTML = '<div class="today-empty">该模块暂时不可用，其他模块可以继续使用。</div>';
      root.dataset.moduleStatus = 'broken';
    },
  };
}


function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value || '';
  return element.innerHTML;
}
