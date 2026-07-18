import { loadCurrentEventKnowledge } from './service.js';
import { createCurrentEventView } from './view.js';

export default {
  id: 'current-event',
  name: '当前赛事',
  async mount(context = {}) {
    const root = document.getElementById('card-current-event');
    const view = createCurrentEventView(root);
    const refresh = async () => {
      view.loading();
      try {
        view.render(await loadCurrentEventKnowledge());
        root.dataset.moduleStatus = 'healthy';
      } catch {
        view.error();
      }
    };
    root.querySelector('[data-event-action="refresh"]')?.addEventListener('click', refresh);
    context.events?.on('page:changed', ({ page }) => { if (page === 'event') refresh(); });
    root.dataset.moduleId = 'current-event';
    root.dataset.moduleStatus = 'healthy';
    return { actions: { refresh } };
  },
};
