import {
  buildMatchPrompt, buildMatchWorkspacePayload, loadCurrentEventWorkspace, loadMatchDesk,
  parseMatchJudgment, focusMatchRun, pauseMatchRun, saveMatchChange, saveMatchTradeEntry, saveMatchWorkspace, startMatchRun,
} from './service.js';
import { createCurrentEventView } from './view.js';

let dispose = () => {};

export default {
  id: 'current-event',
  name: '当前赛事',
  async mount(context = {}) {
    const root = document.getElementById('card-current-event');
    const view = createCurrentEventView(root);
    dispose();
    const state = { matches: [], recentMatches: [], selected: null, desk: null };
    const refresh = async () => {
      view.loading();
      try {
        const payload = await loadCurrentEventWorkspace();
        state.matches = payload.matches || [];
        state.recentMatches = payload.recentMatches || [];
        state.selected = null;
        state.desk = null;
        view.render(payload);
        root.dataset.moduleStatus = 'healthy';
        if (state.matches.length) await actions.selectMatch(0);
      } catch {
        view.error();
      }
    };
    const actions = {
      refresh,
      async selectMatch(index) {
        const entry = state.matches[index];
        if (!entry?.match) return null;
        state.selected = entry.match;
        state.desk = null;
        view.selectMatch(index);
        view.renderMatchLoading();
        try {
          state.desk = await loadMatchDesk(entry.match);
          view.renderMatch(state.desk, entry.match);
          return state.desk;
        } catch (error) {
          view.setMessage(error.message || '这场比赛暂时无法汇总', 'error');
          return null;
        }
      },
      async selectRecentMatch(index) {
        const entry = state.recentMatches[index];
        if (!entry?.match) return null;
        state.selected = entry.match;
        state.desk = null;
        view.selectRecentMatch(index);
        view.renderMatchLoading();
        try {
          state.desk = await loadMatchDesk(entry.match);
          view.renderMatch(state.desk, entry.match);
          return state.desk;
        } catch (error) {
          view.setMessage(error.message || '这场比赛暂时无法汇总', 'error');
          return null;
        }
      },
      async copyMatch() {
        if (!state.desk) return;
        const text = buildMatchPrompt(state.desk, state.selected || {});
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
          } else {
            const area = document.createElement('textarea');
            area.value = text;
            document.body.append(area);
            area.select();
            document.execCommand('copy');
            area.remove();
          }
          view.setMessage('已复制到剪贴板', 'success');
        } catch {
          view.setMessage('复制失败，请直接从单场底稿读取', 'error');
        }
      },
      async saveJudgment() {
        if (!state.desk) return null;
        const parsed = parseMatchJudgment(view.readJudgment());
        if (!parsed.ok) {
          view.setMessage(parsed.message, 'error');
          return null;
        }
        view.setMessage('正在留存本场当前判断…');
        try {
          const workspace = await saveMatchWorkspace(
            buildMatchWorkspacePayload(state.desk.match || state.selected || {}, parsed.value),
          );
          state.desk.workspace = workspace;
          view.renderMatch(state.desk, state.selected || {});
          view.setMessage('已留存本场当前判断', 'success');
          return workspace;
        } catch (error) {
          view.setMessage(error.message || '当前判断保存失败', 'error');
          return null;
        }
      },
      async saveChange() {
        if (!state.desk) return null;
        const change = view.readChange();
        if (!change.detail) {
          view.setMessage('写清楚这次具体变了什么', 'error');
          return null;
        }
        view.setMessage('正在记录变化…');
        try {
          const result = await saveMatchChange(
            buildMatchWorkspacePayload(state.desk.match || state.selected || {}, change),
          );
          const workspace = state.desk.workspace || { exists: true, current: null, changes: [] };
          workspace.exists = true;
          workspace.changes = [result.change, ...(workspace.changes || [])];
          state.desk.workspace = workspace;
          view.renderMatch(state.desk, state.selected || {});
          view.setMessage('已记录这次变化；当前判断没有被自动改写', 'success');
          return result;
        } catch (error) {
          view.setMessage(error.message || '变化记录失败', 'error');
          return null;
        }
      },
      async startRun() {
        if (!state.desk || !state.selected) return null;
        view.setMessage('正在打开这场交易推演…');
        try {
          const run = await startMatchRun(state.desk.match || state.selected, 'live');
          state.desk.match_run = run;
          state.recentMatches = upsertRecentRun(state.recentMatches, run, true);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已打开；可以从任何一项开始，也可以随时切换比赛', 'success');
          return run;
        } catch (error) {
          view.setMessage(error.message || '赛前模拟启动失败', 'error');
          return null;
        }
      },
      async pauseRun() {
        if (!state.desk || !state.selected) return null;
        view.setMessage('正在保存并放下这场…');
        try {
          const run = await pauseMatchRun(state.desk.match || state.selected);
          state.desk.match_run = run;
          state.recentMatches = upsertRecentRun(state.recentMatches, run, false);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已保存；以后回来会接着当前内容', 'success');
          return run;
        } catch (error) {
          view.setMessage(error.message || '暂存失败', 'error');
          return null;
        }
      },
      async focusRun() {
        if (!state.desk?.match_run) return null;
        const { section } = view.readTradeEntry();
        view.setMessage('正在切换当前模块…');
        try {
          const run = await focusMatchRun(state.desk.match || state.selected || {}, section);
          state.desk.match_run = run;
          state.recentMatches = upsertRecentRun(state.recentMatches, run, true);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected || {});
          view.setMessage(`已切到${run.guide?.focus_label || '这一项'}；没有写入任何判断`, 'success');
          return run;
        } catch (error) {
          view.setMessage(error.message || '切换模块失败', 'error');
          return null;
        }
      },
      async saveTradeEntry() {
        if (!state.desk || !state.selected) return null;
        const entry = view.readTradeEntry();
        if (!entry.content.trim()) {
          view.setMessage('先写清楚这一项的当前判断', 'error');
          return null;
        }
        view.setMessage('正在保存这一项…');
        try {
          const run = await saveMatchTradeEntry(state.desk.match || state.selected, entry.section, entry.content);
          state.desk.match_run = run;
          view.renderMatch(state.desk, state.selected);
          view.setMessage('只更新了这一项，其他内容保持不动', 'success');
          return run;
        } catch (error) {
          view.setMessage(error.message || '这一项保存失败', 'error');
          return null;
        }
      },
    };
    root.querySelector('[data-event-action="refresh"]')?.addEventListener('click', refresh);
    dispose = view.bind(actions);
    context.events?.on('page:changed', ({ page }) => { if (page === 'event') refresh(); });
    root.dataset.moduleId = 'current-event';
    root.dataset.moduleStatus = 'healthy';
    return { actions };
  },
  unmount() {
    dispose();
    dispose = () => {};
  },
};

function upsertRecentRun(items, run, activate) {
  const next = (items || []).filter((item) => Number(item.id) !== Number(run.id)).map((item) => (
    activate && item.activity_status === 'active' ? { ...item, activity_status: 'paused' } : item
  ));
  return [{
    id: run.id,
    match: run.match,
    activity_status: run.activity_status,
    focus: run.focus,
    focus_label: run.guide?.focus_label || '单场底稿',
    updated_at: run.updated_at,
  }, ...next].slice(0, 12);
}
