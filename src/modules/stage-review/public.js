import {
  fetchStageCandidates,
  fetchTradingTK,
  updateStageCandidate,
  updateTradingTK as updateTradingTKRequest,
} from './api.js';
import { createStageReviewView } from './view.js';

let dispose = () => {};

export default {
  id: 'stage-review',
  name: '阶段整理',
  async mount(context = {}) {
    const root = document.getElementById('card-stage-review');
    const view = createStageReviewView(root);
    dispose();
    const state = { candidates: [], tradingTK: [] };
    const actions = {
      async refresh() {
        view.loading();
        try {
          const [candidatePayload, tradingPayload] = await Promise.all([
            fetchStageCandidates('pending', 100), fetchTradingTK('all', 100),
          ]);
          const payload = {
            candidates: candidatePayload.candidates || [],
            tradingTK: tradingPayload.items || [],
          };
          state.candidates = payload.candidates;
          state.tradingTK = payload.tradingTK;
          view.render(payload);
          root.dataset.moduleStatus = 'healthy';
          return payload;
        } catch (error) {
          view.error(error);
          return null;
        }
      },
      async ignore(candidateId) {
        try {
          await updateStageCandidate(candidateId, 'ignored');
          view.setMessage('本轮不处理；没有修改任何长期资料', 'success');
          return actions.refresh();
        } catch (error) {
          view.setMessage(error.message || '更新失败', 'error');
          return null;
        }
      },
      async updateTradingTK(filename, status) {
        try {
          await updateTradingTKRequest(filename, status);
          view.setMessage(status === 'confirmed' ? '已确认这条交易 TK' : '已标记这条交易 TK 失效', 'success');
          return actions.refresh();
        } catch (error) {
          view.setMessage(error.message || '交易 TK 状态更新失败', 'error');
          return null;
        }
      },
      async copyPrompt() {
        const text = '小雪，开始阶段知识整理。先读取待整理候选，再结合原有版本理解、队伍和选手资料、三维、TK 与 TS 依据；只展示真正需要修改的内容，最后等我确认后再写回。';
        try {
          await copyText(text);
          view.setMessage('已复制，直接发给小雪', 'success');
        } catch {
          view.setMessage('复制失败', 'error');
        }
      },
    };
    dispose = view.bind(actions);
    context.events?.on('page:changed', ({ page }) => { if (page === 'stage') actions.refresh(); });
    root.dataset.moduleId = 'stage-review';
    root.dataset.moduleStatus = 'healthy';
    return { actions, state };
  },
  unmount() {
    dispose();
    dispose = () => {};
  },
};

async function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const area = document.createElement('textarea');
  area.value = text;
  document.body.append(area);
  area.select();
  document.execCommand('copy');
  area.remove();
}
