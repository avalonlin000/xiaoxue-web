import { loadDailyView } from './service.js';
import { createDailyView } from './view.js';


export default {
  id: 'daily',
  name: '每日准备',
  async mount() {
    const root = document.getElementById('card-today-content');
    if (!root) throw moduleError('每日准备入口不存在');
    const view = createDailyView(root);
    const load = async () => {
      view.loading();
      try {
        view.render(await loadDailyView('today'));
        root.dataset.moduleStatus = 'healthy';
      } catch (error) {
        view.error(error);
        error.userMessage = '每日准备暂时不可用，其他模块可以继续使用';
        throw error;
      }
    };
    root.querySelector('[data-action="daily-refresh"]')?.addEventListener('click', load);
    root.dataset.moduleId = 'daily';
    await load();
    return { actions: { refresh: load } };
  },
};


function moduleError(message) {
  const error = new Error(message);
  error.userMessage = `${message}，其他模块可以继续使用`;
  return error;
}
