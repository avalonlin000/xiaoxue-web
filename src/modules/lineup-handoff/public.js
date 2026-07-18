import { fetchAnalyst, writeClipboard } from './api.js';
import { buildAnalystPrompt, buildLineupPrompt, normalizeLineupText } from './service.js';
import { createLineupView } from './view.js';

export { buildAnalystPrompt, buildLineupPrompt, normalizeLineupText };

let view = null;
let getSelectedTeam = () => '';
let dispose = () => {};

export const actions = {
  generate() {
    const text = buildAnalystPrompt(getSelectedTeam(), view?.readLineup() || '');
    view?.show(text);
    return text;
  },
  async copyFromAnalyst() {
    return copy(buildLineupPrompt({ lineupText: view?.readLineup() || '' }));
  },
  async copyFromMarket(dto = {}) {
    return copy(buildLineupPrompt(dto));
  },
  async loadAnalyst(analyst = '中年电竞人') {
    const team = getSelectedTeam();
    if (!team) return null;
    view?.loading(team, analyst);
    try {
      const data = await fetchAnalyst(team, analyst);
      if (!data || data.found === false) view?.show(`暂无 ${team} 的分析师结果。`);
      else if (typeof data.content === 'string') view?.show(`【${data.analyst || analyst}】\n${data.content}`);
      else view?.show(Object.entries(data.content || {}).map(([name, text]) => `【${name}】\n${text}`).join('\n\n'));
      return data;
    } catch {
      view?.show('分析师接口调用失败；基本面、TK、临场记录不受影响。');
      return null;
    }
  },
};

async function copy(text) {
  try {
    if (await writeClipboard(text)) return { copied: true, text };
  } catch {}
  view?.show(text);
  return { copied: false, text };
}

export default {
  id: 'lineup-handoff', name: '阵容交接',
  async mount(context = {}) {
    const root = document.getElementById('card-analyst');
    view = createLineupView(root);
    getSelectedTeam = context.lineup?.getSelectedTeam || (() => context.appContext?.selectedTeam || '');
    dispose = view.bind(actions);
    root.dataset.moduleId = 'lineup-handoff';
    root.dataset.moduleStatus = 'healthy';
    return { actions };
  },
  unmount() { dispose(); dispose = () => {}; view = null; },
};
