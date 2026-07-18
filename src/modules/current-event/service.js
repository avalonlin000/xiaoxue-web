import { fetchCurrentEvent, fetchEventKnowledge } from './api.js';

export async function loadCurrentEventKnowledge() {
  const context = await fetchCurrentEvent();
  const payload = await fetchEventKnowledge(context.knowledge_query || context.event, 12);
  return {
    context,
    items: (payload.results || []).map((item) => ({
      title: item.concept || item.id || '赛事资料', summary: item.content || '', date: item.date || '',
    })),
  };
}
