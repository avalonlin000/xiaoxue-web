import {
  createMarketNote, createTeamTradingNote, deleteMarketNote, fetchMarketNotes,
} from './api.js';
import {
  buildMarketNotePayload, buildTeamPrefill, buildTkDraft,
  filterMarketNotes,
} from './service.js';
import { createMarketNotesView } from './view.js';

export { createMarketNote, createTeamTradingNote, deleteMarketNote, fetchMarketNotes } from './api.js';
export {
  buildDailyTradeDraft, filterMarketNotes, getMarketNoteResult, stripResultLine, withResultLine,
} from './service.js';

export function createMarketNotesModule(options = {}) {
  const dependencies = {
    api: {
      fetch: options.api?.fetch || fetchMarketNotes,
      create: options.api?.create || createMarketNote,
      delete: options.api?.delete || deleteMarketNote,
      createTeamNote: options.api?.createTeamNote || createTeamTradingNote,
    },
    getSelectedTeam: options.getSelectedTeam || (() => ''),
    getTeamInfo: options.getTeamInfo || ((code) => ({ short_name: code, name: code, region: '' })),
    getUpcomingSchedule: options.getUpcomingSchedule || null,
    getMatchContext: options.getMatchContext || null,
    confirmDelete: options.confirmDelete || ((message) => globalThis.confirm?.(message) ?? false),
    onTkDraft: options.onTkDraft || (() => {}),
  };
  let view = null;
  let dispose = () => {};
  const state = {
    game: 'lol', records: [], filters: { range: 'all', result: 'all', keyword: '' },
  };

  const actions = {
    async load() {
      view?.renderLoading();
      try {
        const payload = await dependencies.api.fetch(state.game, 200);
        state.records = Array.isArray(payload?.records) ? payload.records : [];
        render();
        return state.records;
      } catch (error) {
        view?.renderError(error.message || '盘口草稿加载失败');
        throw error;
      }
    },
    async setGame(game) {
      state.game = game || 'lol';
      view?.setGame(state.game);
      return actions.load();
    },
    setRange(range) {
      state.filters.range = ['7d', '30d', 'all'].includes(range) ? range : 'all';
      render();
    },
    setResultFilter(result) { state.filters.result = result || 'all'; render(); },
    setKeywordFilter(keyword) { state.filters.keyword = String(keyword || '').trim(); render(); },
    async save() {
      const values = requireView().readForm();
      const body = buildMarketNotePayload(values, {
        game: state.game, selectedTeam: dependencies.getSelectedTeam() || '',
      });
      if (!body.match_name) { view.setMessage('先填比赛', 'error'); return null; }
      view.setMessage('保存中…');
      try {
        const result = await dependencies.api.create(body);
        view.clearForm();
        view.setMessage('已保存原始记录；赛后直接跟小雪讨论复盘', 'success');
        await actions.load();
        return result;
      } catch (error) {
        view.setMessage(error.message || '保存失败', 'error');
        return null;
      }
    },
    async deleteRecord(id) {
      if (!dependencies.confirmDelete('删除这条盘口草稿？')) return false;
      requireView().setMessage('删除中…');
      try {
        await dependencies.api.delete(id);
        await actions.load();
        view.setMessage('已删除', 'success');
        return true;
      } catch (error) {
        view.setMessage(error.message || '删除失败', 'error');
        return false;
      }
    },
    async prefill() {
      const team = dependencies.getSelectedTeam() || '';
      if (!team) { requireView().setMessage('先选择 LOL 队伍', 'error'); return null; }
      view.setMessage('正在带入当前队伍对象…');
      let schedule = null;
      let matchContext = null;
      try {
        const rows = dependencies.getUpcomingSchedule ? await dependencies.getUpcomingSchedule(team) : [];
        schedule = Array.isArray(rows) ? rows[0] : null;
        const opponent = schedule?.team_a === team ? schedule.team_b : (schedule?.team_b === team ? schedule.team_a : '');
        if (opponent && dependencies.getMatchContext) matchContext = await dependencies.getMatchContext(team, opponent);
      } catch {
        // Context is optional; manual prefill must remain usable when it fails.
      }
      state.game = 'lol';
      const prefill = buildTeamPrefill(team, dependencies.getTeamInfo(team), schedule, matchContext);
      view.setGame('lol');
      view.applyPrefill(prefill);
      view.setMessage(prefill.message, 'success');
      return prefill;
    },
    async saveTeamNote() {
      const text = requireView().readTeamNote();
      if (!text) { view.setTeamNoteMessage('先写一句，比如：小雪记到 HLE：虐菜大人头', 'error'); return null; }
      view.setTeamNoteMessage('正在写入队伍 TK…');
      try {
        const data = await dependencies.api.createTeamNote({ text });
        if (data?.ok === false) throw new Error(data.detail || data.message || '队伍未确认，未写入正式 TK');
        view.clearTeamNote();
        view.setTeamNoteMessage(`已记到 ${data.team} 队伍 TK：${data.note?.market_label || data.note?.market || '交易备注'}`, 'success');
        return data;
      } catch (error) {
        view.setTeamNoteMessage(error.message || '写入失败，稍后重试', 'error');
        return null;
      }
    },
    requestTkDraft(id) {
      const draft = buildTkDraft(state.records.find((record) => Number(record.id) === Number(id)), dependencies.getSelectedTeam());
      if (draft) dependencies.onTkDraft(draft);
      return draft;
    },
    getState() {
      return { game: state.game, records: [...state.records], filters: { ...state.filters } };
    },
  };

  function render() {
    const filtered = filterMarketNotes(state.records, state.filters);
    view?.renderRecords(filtered, state.records.length, state.filters);
  }

  function requireView() {
    if (!view) throw new Error('临场记录模块尚未挂载');
    return view;
  }

  return {
    id: 'market-notes', name: '临场记录', actions,
    async mount(context = {}) {
      const injected = context.marketNotes || {};
      dependencies.api = { ...dependencies.api, ...(injected.api || {}) };
      [
        'getSelectedTeam', 'getTeamInfo', 'getUpcomingSchedule', 'getMatchContext',
        'confirmDelete', 'onTkDraft',
      ].forEach((name) => {
        if (typeof injected[name] === 'function') dependencies[name] = injected[name];
      });
      const root = context.root || document.getElementById(context.rootId || 'card-trades');
      view = createMarketNotesView(root);
      root.dataset.moduleId = 'market-notes';
      root.dataset.moduleStatus = 'healthy';
      // The legacy page still has inline handlers. The shell opts in after removing them,
      // preventing duplicate writes during the incremental migration.
      if (context.bindHandlers || injected.bindHandlers) dispose = view.bind(actions);
      if (context.autoLoad || injected.autoLoad) await actions.load();
      return actions;
    },
    unmount() {
      dispose();
      dispose = () => {};
      view = null;
    },
  };
}

const marketNotesModule = createMarketNotesModule();

export const actions = marketNotesModule.actions;
export const mount = (context) => marketNotesModule.mount(context);
export const unmount = () => marketNotesModule.unmount();
export default marketNotesModule;
