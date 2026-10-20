import {
  deleteTKEntryRequest, fetchTKEntry, fetchTKLibrary, fetchTeamTradingNotes,
  saveTKEntryRequest, searchTKEntries,
} from './api.js';
import {
  applyLibraryPayload, buildEditorDraft, buildLibraryParams, buildSavePayload,
  createLibraryState, librarySummary, normalizeExternalDraft, normalizePeriod,
} from './service.js';
import { createTKLibraryView, renderTKReaderContent } from './view.js';

export {
  deleteTKEntryRequest, fetchTKEntry, fetchTKLibrary, fetchTeamTradingNotes,
  saveTKEntryRequest, searchTKEntries,
} from './api.js';
export { renderTKReaderContent } from './view.js';

export function createTKLibraryModule(options = {}) {
  const dependencies = {
    api: {
      library: options.api?.library || fetchTKLibrary,
      entry: options.api?.entry || fetchTKEntry,
      search: options.api?.search || searchTKEntries,
      tradingNotes: options.api?.tradingNotes || fetchTeamTradingNotes,
      save: options.api?.save || saveTKEntryRequest,
      delete: options.api?.delete || deleteTKEntryRequest,
    },
    getTeams: options.getTeams || (() => []),
    getSelectedTeam: options.getSelectedTeam || (() => ''),
    confirmDelete: options.confirmDelete || ((message) => globalThis.confirm?.(message) ?? false),
    notify: options.notify || ((message) => globalThis.alert?.(message)),
  };
  const library = createLibraryState();
  const quick = { results: [], query: '', team: '', teamOverview: false, total: 0, expanded: false };
  let view = null;
  let dispose = () => {};
  let readerEntry = null;

  const actions = {
    populateTeams(teams = dependencies.getTeams()) { requireView().populateTeams(teams || []); },
    async load(reset = false) {
      if (library.loading) return null;
      if (reset) { library.offset = 0; library.results = []; }
      library.loading = true;
      requireView().renderLibraryLoading(reset);
      try {
        const payload = await dependencies.api.library(buildLibraryParams(library));
        applyLibraryPayload(library, payload, reset);
        view.renderLibrary(library, payload.latest_date, librarySummary(library));
        return payload;
      } catch (error) {
        view.renderLibraryError();
        return null;
      } finally {
        library.loading = false;
      }
    },
    async applyFilters() {
      const filters = requireView().readFilters();
      library.query = filters.query;
      library.team = filters.team;
      library.month = filters.month;
      return actions.load(true);
    },
    async setPeriod(period) {
      library.period = normalizePeriod(period);
      requireView().setPeriod(library.period);
      return actions.applyFilters();
    },
    loadMore() { return actions.load(false); },
    async openReader(index) {
      const item = library.results[index];
      if (!item) return null;
      readerEntry = { ...item, index };
      requireView().openReader(readerEntry);
      try {
        const payload = await dependencies.api.entry(item.filename);
        readerEntry = { ...readerEntry, ...payload };
        view.showReader(readerEntry, item);
        return payload;
      } catch (error) {
        view.showReaderError();
        return null;
      }
    },
    closeReader() { view?.closeReader(); },
    editReader() {
      if (!readerEntry?.filename) return false;
      requireView().openEditor(buildEditorDraft(readerEntry, dependencies.getSelectedTeam()), '');
      return true;
    },
    async deleteReader() {
      if (!readerEntry?.filename) return false;
      if (!dependencies.confirmDelete(`删除 TK：${readerEntry.concept || readerEntry.filename}？`)) return false;
      try {
        await dependencies.api.delete(readerEntry.filename);
        readerEntry = null;
        view?.closeReader();
        await actions.load(true);
        return true;
      } catch (error) {
        dependencies.notify(`删除失败：${error?.message || '请稍后重试'}`);
        return false;
      }
    },
    async quickSearch(query = '', context = {}) {
      const team = context.team === undefined ? dependencies.getSelectedTeam() || '' : context.team || '';
      const teamOverview = Boolean(context.teamOverview && team);
      const value = String(query || view?.readQuickQuery() || (teamOverview ? team : dependencies.getSelectedTeam() || '')).trim();
      if (!value) return [];
      quick.query = value;
      quick.team = team;
      quick.teamOverview = teamOverview;
      quick.total = 0;
      quick.expanded = false;
      requireView().setQuickQuery(value);
      view.renderQuickLoading();
      try {
        const source = teamOverview
          ? loadAllTeamLibraryEntries(team)
          : dependencies.api.search(value, team, context.limit || 15);
        const [payload, tradingPayload] = await Promise.all([
          source,
          team
            ? dependencies.api.tradingNotes(team, 'active', 8).catch(() => ({ notes: [] }))
            : Promise.resolve({ notes: [] }),
        ]);
        const priority = (tradingPayload?.notes || []).map((note) => ({
          id: note.filename || `trading-${note.team}-${note.title}`,
          filename: note.filename || '',
          concept: note.title || `${note.team || quick.team} 交易 TK`,
          content: [note.original, note.daily_hint].filter(Boolean).join('\n'),
          date: '', source: '交易 TK', source_type: 'trading_note',
          tags: ['交易 TK'], isTradingTK: true,
        }));
        const priorityFiles = new Set(priority.map((item) => item.filename).filter(Boolean));
        const regular = (Array.isArray(payload?.results) ? payload.results : [])
          .filter((item) => !priorityFiles.has(item.filename));
        quick.results = [...priority, ...regular];
        quick.total = teamOverview ? Number(payload?.total ?? regular.length) : quick.results.length;
        view.renderQuickResults(quick.results, { total: quick.total, expanded: quick.expanded });
        return quick.results;
      } catch (error) {
        quick.results = [];
        quick.total = 0;
        view.renderQuickError();
        return [];
      }
    },
    async openQuickReader(index) {
      const item = quick.results[index];
      if (!item) return null;
      requireView().openQuickReader(item);
      if (!item.filename) {
        view.showQuickReader(item, item);
        return item;
      }
      try {
        const payload = await dependencies.api.entry(item.filename);
        view.showQuickReader(payload, item);
        return payload;
      } catch (error) {
        view.showQuickReaderError();
        return null;
      }
    },
    closeQuickReader() { view?.closeQuickReader(); },
    toggleQuickList() {
      quick.expanded = !quick.expanded;
      requireView().renderQuickResults(quick.results, { total: quick.total, expanded: quick.expanded });
      return quick.expanded;
    },
    goToLibrary() {
      document.getElementById('tab-tk')?.click();
      return true;
    },
    openEditor(filename = '') {
      const entry = filename ? quick.results.find((item) => item.filename === filename) : null;
      requireView().openEditor(buildEditorDraft(entry, dependencies.getSelectedTeam()), '');
    },
    openDraft(draft) {
      const normalized = normalizeExternalDraft(draft);
      requireView().openEditor(normalized, normalized.message);
      return normalized;
    },
    closeEditor() { view?.closeEditor(); },
    editQuick(index) {
      const entry = quick.results[index];
      if (entry?.filename) actions.openEditor(entry.filename);
    },
    async deleteQuick(index) {
      const entry = quick.results[index];
      if (!entry?.filename) return false;
      if (!dependencies.confirmDelete(`删除 TK：${entry.concept || entry.filename}？`)) return false;
      try {
        await dependencies.api.delete(entry.filename);
        if (library.initialized) await actions.load(true);
        if (quick.teamOverview) await actions.quickSearch('', { team: quick.team, teamOverview: true });
        else await actions.quickSearch(quick.query, { team: quick.team });
        return true;
      } catch (error) {
        dependencies.notify(`删除失败：${error?.message || '请稍后重试'}`);
        return false;
      }
    },
    async saveEditor() {
      let payload;
      try {
        payload = buildSavePayload(requireView().readEditor(), dependencies.getSelectedTeam());
      } catch (error) {
        view.setEditorMessage(error.message);
        return null;
      }
      view.setEditorMessage('保存中…');
      try {
        const result = await dependencies.api.save(payload.filename, payload.body);
        view.setEditorMessage(payload.filename ? '✅ 已更新' : '✅ 已保存');
        if (readerEntry?.filename && readerEntry.filename === payload.filename) {
          readerEntry = { ...readerEntry, ...payload.body };
          view.showReader(readerEntry, readerEntry);
        }
        setTimeout(async () => {
          view?.closeEditor();
          if (library.initialized) await actions.load(true);
          else if (quick.query) await actions.quickSearch(quick.query, { team: quick.team });
        }, 800);
        return result;
      } catch (error) {
        view.setEditorMessage('❌ 保存失败');
        return null;
      }
    },
    getState() {
      return {
        library: { ...library, results: [...library.results] },
        quick: { ...quick, results: [...quick.results] },
      };
    },
  };

  async function loadAllTeamLibraryEntries(team) {
    const results = [];
    let offset = 0;
    let hasMore = true;
    let latestDate = '';
    while (hasMore) {
      const payload = await dependencies.api.library(new URLSearchParams({
        period: 'all', month: '', q: '', team, offset: String(offset), limit: '100',
      }));
      const page = Array.isArray(payload?.results) ? payload.results : [];
      results.push(...page);
      offset += page.length;
      latestDate ||= payload?.latest_date || '';
      hasMore = Boolean(payload?.has_more) && page.length > 0;
    }
    return { results, latest_date: latestDate, total: results.length, has_more: false };
  }

  function requireView() {
    if (!view) throw new Error('TK资料库模块尚未挂载');
    return view;
  }

  return {
    id: 'tk-library', name: 'TK资料库', actions,
    async mount(context = {}) {
      const injected = context.tkLibrary || {};
      dependencies.api = { ...dependencies.api, ...(injected.api || {}) };
      ['getTeams', 'getSelectedTeam', 'confirmDelete', 'notify'].forEach((name) => {
        if (typeof injected[name] === 'function') dependencies[name] = injected[name];
      });
      const roots = {
        root: injected.root || context.root || document.getElementById('card-tk-library'),
        readerRoot: injected.readerRoot || document.getElementById('tk-library-reader'),
        quickReaderRoot: injected.quickReaderRoot || document.getElementById('tk-quick-reader'),
        editorRoot: injected.editorRoot || document.getElementById('tk-editor-overlay'),
        quickSearchRoot: injected.quickSearchRoot || document.getElementById('card-tk'),
      };
      view = createTKLibraryView(roots);
      roots.root.dataset.moduleId = 'tk-library';
      roots.root.dataset.moduleStatus = 'healthy';
      if (injected.bindHandlers || context.bindHandlers) dispose = view.bind(actions);
      actions.populateTeams();
      if (injected.autoLoad || context.autoLoad) await actions.load(true);
      return actions;
    },
    unmount() {
      dispose();
      dispose = () => {};
      view = null;
    },
  };
}

const tkLibraryModule = createTKLibraryModule();
export const actions = tkLibraryModule.actions;
export const mount = (context) => tkLibraryModule.mount(context);
export const unmount = () => tkLibraryModule.unmount();
export default tkLibraryModule;
