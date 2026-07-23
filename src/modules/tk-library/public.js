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
  const quick = { results: [], query: '', team: '' };
  let view = null;
  let dispose = () => {};

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
      requireView().openReader(item);
      try {
        const payload = await dependencies.api.entry(item.filename);
        view.showReader(payload, item);
        return payload;
      } catch (error) {
        view.showReaderError();
        return null;
      }
    },
    closeReader() { view?.closeReader(); },
    async quickSearch(query = '', context = {}) {
      const value = String(query || view?.readQuickQuery() || dependencies.getSelectedTeam() || '').trim();
      if (!value) return [];
      quick.query = value;
      quick.team = context.team === undefined ? dependencies.getSelectedTeam() || '' : context.team || '';
      requireView().setQuickQuery(value);
      view.renderQuickLoading();
      try {
        const [payload, tradingPayload] = await Promise.all([
          dependencies.api.search(value, quick.team, context.limit || 15),
          quick.team
            ? dependencies.api.tradingNotes(quick.team, 'active', 8).catch(() => ({ notes: [] }))
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
        view.renderQuickResults(quick.results);
        return quick.results;
      } catch (error) {
        quick.results = [];
        view.renderQuickError();
        return [];
      }
    },
    toggleQuick(index) { view?.toggleQuick(index); },
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
        await actions.quickSearch(quick.query, { team: quick.team });
        return true;
      } catch (error) {
        dependencies.notify('删除失败');
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
        readerRoot: injected.readerRoot || document.getElementById('tk-reader-overlay'),
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
