import {
  buildMatchPrompt, createMatchMaterialsController, matchMaterialsForDesk, loadCurrentEventWorkspace, loadCurrentEventReferences, loadMatchDesk, loadGolSeriesEvidence,
  focusMatchRun, pauseMatchRun, saveMatchTradeEntry, startMatchRun,
  createTradePlanItem, updateTradePlanItem, deleteTradePlanItem, restoreTradePlanItem, reorderTradePlanItem,
  createJudgmentController, judgmentObject,
  createReadingTracker,
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
    const state = { matches: [], recentMatches: [], selected: null, desk: null, context: {}, methods: [], eventMaterials: null };
    let active = true;
    let selection = 0;
    let workspaceRevision = 0;
    let materialsDesk = null;
    let selectedMethod = '';
    let selecting = false;
    let judgmentIdentityKey = '';
    let localReadingStorage = null;
    try { localReadingStorage = globalThis.localStorage || null; } catch { /* Browser policy may deny local storage. */ }
    const reading = createReadingTracker({ storage: localReadingStorage });
    const readingStops = new Map();
    const stopReading = (kind) => {
      if (kind) { readingStops.get(kind)?.(); readingStops.delete(kind); }
      else { readingStops.forEach((stop) => stop()); readingStops.clear(); }
    };
    const readable = (kind, payload, object) => {
      const packet = object ? { ...payload, object } : { ...payload };
      if (kind === 'judgment' ? packet.status === 'ok' && (packet.contents?.length || packet.analysis?.length) : packet.result) {
        packet.reading = reading.inspect(kind === 'judgment' ? 'judgment' : 'materials', packet);
      }
      return packet;
    };
    const watchReading = (kind, packet) => {
      stopReading(kind);
      if (packet.reading) readingStops.set(kind, view.watchReading(kind, (positions) => reading.mark(packet.reading, positions)));
    };
    const judgment = createJudgmentController({
      onContext(payload) {
        if (!active) return;
        const packet = readable('judgment', payload);
        view.renderJudgment(packet); watchReading('judgment', packet);
      },
      onDiscussion(payload) { if (active) view.renderJudgmentDiscussion(payload); },
      onSession(payload) { if (active) view.restoreJudgmentSession(payload); },
    });
    const rememberJudgmentDraft = () => judgment.setDraft(view.readJudgmentQuestion());
    const resetJudgment = () => {
      stopReading('judgment');
      const identity = judgmentObject(state.context, state.desk, state.selected);
      judgmentIdentityKey = JSON.stringify(identity);
      const session = judgment.setObject(identity, { restoreTeam: true });
      selectedMethod = session.methodId;
      view.resetJudgment();
      view.restoreJudgmentSession(session);
      if (!selecting && state.methods.some((method) => method.id === selectedMethod && method.status === 'ready')) {
        view.renderJudgmentLoading(selectedMethod);
        view.restoreJudgmentSession(session);
        void judgment.open(selectedMethod);
      }
    };
    const materials = createMatchMaterialsController({
      onUpdate(payload) {
        if (!active || !state.desk || matchMaterialsForDesk(state.desk)?.suppressed) return;
        const packet = readable('materials', payload, judgmentObject(state.context, state.desk, state.selected));
        state.desk.prepared_materials = packet;
        // Polling must not erase unsaved trade-plan or discussion input.
        view.renderMaterials(packet); watchReading('materials', packet);
      },
    });
    const refreshMaterialsForDesk = () => {
      const desk = state.desk;
      if (!desk) return;
      // Run mode may change without selecting another match. Invalidate any live
      // discussion before switching to a sealed pre-match replay (or back).
      if (JSON.stringify(judgmentObject(state.context, desk, state.selected)) !== judgmentIdentityKey) resetJudgment();
      const display = matchMaterialsForDesk(desk);
      if (display?.suppressed) {
        stopReading('event');
        view.renderEventMaterials({ suppressed: true });
        materials.stop();
        materialsDesk = null;
        desk.prepared_materials = null;
        view.renderMaterials(display);
      } else if (materialsDesk !== desk) {
        if (state.eventMaterials) {
          view.renderEventMaterials(state.eventMaterials);
          watchReading('event', state.eventMaterials);
        }
        materialsDesk = desk;
        void materials.start(desk.match || state.selected || {}, display);
      }
    };
    const refresh = async () => {
      const current = ++selection;
      const revision = ++workspaceRevision;
      rememberJudgmentDraft();
      materials.stop();
      materialsDesk = null;
      stopReading();
      reading.reset();
      judgment.stop();
      view.resetJudgment();
      view.loading();
      try {
        const payload = await loadCurrentEventWorkspace();
        if (!active || current !== selection) return;
        state.matches = payload.matches || [];
        state.recentMatches = payload.recentMatches || [];
        state.selected = null;
        state.desk = null;
        selecting = false;
        state.context = payload.context || {};
        state.methods = payload.methods || [];
        view.render(payload);
        // Reference search is an independent read: a slow search must not hide
        // the already prepared schedule, methods and event content.
        void loadCurrentEventReferences(state.context).then(
          references => { if (active && revision === workspaceRevision) view.renderKnowledge(references); },
          () => { if (active && revision === workspaceRevision) view.renderKnowledge({ error: true }); },
        );
        const eventPacket = readable('event', payload.eventMaterials || {}, { event: state.context.event || '' });
        state.eventMaterials = eventPacket;
        view.renderEventMaterials(eventPacket); watchReading('event', eventPacket);
        resetJudgment();
        root.dataset.moduleStatus = 'healthy';
        const firstConfirmed = state.matches.findIndex((entry) => entry.match && !entry.pending);
        if (firstConfirmed >= 0) await actions.selectMatch(firstConfirmed);
      } catch {
        if (active && current === selection) view.error();
      }
    };
    const selectMatch = async (entry, select) => {
      if (!entry?.match || entry.pending) return null;
      // Selecting the active card is navigation, not a refresh. Keep its live
      // editor and let an in-flight read finish; explicit refresh still reloads.
      if (state.selected === entry.match && (selecting || state.desk)) return state.desk;
      rememberJudgmentDraft();
      const current = ++selection;
      materials.stop();
      materialsDesk = null;
      stopReading('materials');
      state.selected = entry.match;
      state.desk = null;
      selecting = true;
      resetJudgment();
      view.clearTradePlanEditor();
      select();
      view.setMessage('');
      view.renderMatchLoading();
      try {
        const desk = await loadMatchDesk(entry.match);
        if (!active || current !== selection) return null;
        state.desk = desk;
        selecting = false;
        resetJudgment();
        view.renderMatch(desk, entry.match);
        refreshMaterialsForDesk();
        return desk;
      } catch {
        if (active && current === selection) {
          selecting = false;
          view.setMessage('这场比赛暂时无法汇总，请稍后重新进入。', 'error');
        }
        return null;
      }
    };
    const isCurrentSelection = (current, desk) => active && current === selection && desk === state.desk;
    const actions = {
      refresh,
      async openJudgment(methodId) {
        const method = state.methods.find((item) => item.id === methodId);
        if (!method || method.status !== 'ready') return null;
        if (selecting) {
          view.renderJudgment({ method, status: 'unavailable', limitations: ['正在读取这场资料，请载入后再进入判断。'], discussion_available: false });
          return null;
        }
        selectedMethod = methodId;
        rememberJudgmentDraft();
        stopReading('judgment');
        reading.reset();
        const session = judgment.setObject(judgmentObject(state.context, state.desk, state.selected, view.readJudgmentTeam()));
        view.renderJudgmentLoading(methodId);
        view.restoreJudgmentSession(session);
        return judgment.open(methodId);
      },
      async reloadJudgment() {
        const current = state.methods.find((item) => item.id === selectedMethod);
        const method = current?.scopes?.includes('team') ? current
          : state.methods.find((item) => item.status === 'ready' && (item.handler === 'team' || item.id === 'team-understanding'));
        return method ? actions.openJudgment(method.id) : null;
      },
      closeJudgment() {
        rememberJudgmentDraft();
        judgment.stop();
        selectedMethod = '';
        stopReading('judgment');
        view.resetJudgment();
        view.returnToMatch();
      },
      draftJudgment(value) { judgment.setDraft(value); },
      async askJudgment() {
        return judgment.ask(view.readJudgmentQuestion());
      },
      async selectMatch(index) {
        return selectMatch(state.matches[index], () => view.selectMatch(index));
      },
      async selectRecentMatch(index) {
        return selectMatch(state.recentMatches[index], () => view.selectRecentMatch(index));
      },
      async loadGolEvidence() {
        if (!state.desk) return null;
        const current = selection;
        const desk = state.desk;
        const gameId = view.readGolGameId().trim();
        if (!/^\d+$/.test(gameId)) {
          view.setMessage('填入 Gol.gg 页面地址里的对局编号', 'error');
          return null;
        }
        view.setMessage('正在读取 Gol.gg 逐局事实…');
        try {
          const evidence = await loadGolSeriesEvidence(state.desk.match || state.selected || {}, gameId);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.gol_evidence = evidence;
          view.renderMatch(state.desk, state.selected || {});
          view.setMessage('已加载外部逐局事实；没有写入任何长期资料', 'success');
          return state.desk.gol_evidence;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || 'Gol.gg 暂时不可用', 'error');
          return null;
        }
      },
      async copyMatch() {
        if (!state.desk) return;
        const current = selection;
        const desk = state.desk;
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
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage('已复制到剪贴板', 'success');
        } catch {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage('复制失败，请直接从单场底稿读取', 'error');
        }
      },
      async saveTradePlanItem() {
        if (!state.desk || !state.selected) return null;
        const current = selection;
        const desk = state.desk;
        const item = view.readTradePlanItem();
        if (!item.direction) {
          view.setMessage('先选择这场的交易方向', 'error');
          return null;
        }
        view.setMessage(item.itemId ? '正在修改本场方案…' : '正在加入本场方案…');
        try {
          const plan = item.itemId
            ? await updateTradePlanItem(state.desk.match || state.selected, item.itemId, item)
            : await createTradePlanItem(state.desk.match || state.selected, item);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.trade_plan = plan;
          view.clearTradePlanEditor();
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已保存本场方案，没有改动长期交易 TK', 'success');
          return state.desk.trade_plan;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '本场方案保存失败', 'error');
          return null;
        }
      },
      cancelTradePlanEdit() {
        if (!state.desk) return;
        view.clearTradePlanEditor();
        view.renderMatch(state.desk, state.selected || {});
      },
      editTradePlanItem(itemId) {
        const item = findTradePlanItem(state.desk?.trade_plan, itemId);
        if (!item || item.manual_state === 'deleted') return;
        view.beginTradePlanEdit(item.effective || item);
      },
      async deleteTradePlanItem(itemId) {
        if (!state.desk || !state.selected || !itemId) return null;
        const current = selection;
        const desk = state.desk;
        view.setMessage('正在移除本场方案…');
        try {
          const plan = await deleteTradePlanItem(state.desk.match || state.selected, itemId);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.trade_plan = plan;
          view.clearTradePlanEditor();
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已从本场方案移除；长期交易 TK 没有改动', 'success');
          return state.desk.trade_plan;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '移除本场方案失败', 'error');
          return null;
        }
      },
      async restoreTradePlanItem(itemId) {
        if (!state.desk || !state.selected || !itemId) return null;
        const current = selection;
        const desk = state.desk;
        view.setMessage('正在恢复自动方案…');
        try {
          const plan = await restoreTradePlanItem(state.desk.match || state.selected, itemId);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.trade_plan = plan;
          view.clearTradePlanEditor();
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已恢复交易 TK 自动版本', 'success');
          return state.desk.trade_plan;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '恢复自动方案失败', 'error');
          return null;
        }
      },
      async reorderTradePlanItem(itemId, movement) {
        if (!state.desk || !state.selected || !itemId) return null;
        const current = selection;
        const desk = state.desk;
        try {
          const plan = await reorderTradePlanItem(state.desk.match || state.selected, itemId, movement);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.trade_plan = plan;
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已调整本场方案顺序', 'success');
          return state.desk.trade_plan;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '方案排序失败', 'error');
          return null;
        }
      },
      async startRun() {
        if (!state.desk || !state.selected) return null;
        const current = selection;
        const desk = state.desk;
        view.setMessage('正在打开这场交易推演…');
        try {
          const run = await startMatchRun(state.desk.match || state.selected, 'live');
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.match_run = run;
          refreshMaterialsForDesk();
          state.recentMatches = upsertRecentRun(state.recentMatches, run, true);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已打开；可以从任何一项开始，也可以随时切换比赛', 'success');
          return run;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '赛前模拟启动失败', 'error');
          return null;
        }
      },
      async pauseRun() {
        if (!state.desk || !state.selected) return null;
        const current = selection;
        const desk = state.desk;
        view.setMessage('正在保存并放下这场…');
        try {
          const run = await pauseMatchRun(state.desk.match || state.selected);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.match_run = run;
          refreshMaterialsForDesk();
          state.recentMatches = upsertRecentRun(state.recentMatches, run, false);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected);
          view.setMessage('已保存；以后回来会接着当前内容', 'success');
          return run;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '暂存失败', 'error');
          return null;
        }
      },
      async focusRun() {
        if (!state.desk?.match_run) return null;
        const current = selection;
        const desk = state.desk;
        const { section } = view.readTradeEntry();
        view.setMessage('正在切换当前模块…');
        try {
          const run = await focusMatchRun(state.desk.match || state.selected || {}, section);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.match_run = run;
          refreshMaterialsForDesk();
          state.recentMatches = upsertRecentRun(state.recentMatches, run, true);
          view.renderRecentMatches(state.recentMatches);
          view.renderMatch(state.desk, state.selected || {});
          view.setMessage(`已切到${run.guide?.focus_label || '这一项'}；没有写入任何判断`, 'success');
          return run;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '切换模块失败', 'error');
          return null;
        }
      },
      async saveTradeEntry() {
        if (!state.desk || !state.selected) return null;
        const current = selection;
        const desk = state.desk;
        const entry = view.readTradeEntry();
        if (!entry.content.trim()) {
          view.setMessage('先写清楚这一项的当前判断', 'error');
          return null;
        }
        view.setMessage('正在保存这一项…');
        try {
          const run = await saveMatchTradeEntry(state.desk.match || state.selected, entry.section, entry.content);
          if (!isCurrentSelection(current, desk)) return null;
          state.desk.match_run = run;
          refreshMaterialsForDesk();
          view.renderMatch(state.desk, state.selected);
          view.setMessage('只更新了这一项，其他内容保持不动', 'success');
          return run;
        } catch (error) {
          if (!isCurrentSelection(current, desk)) return null;
          view.setMessage(error.message || '这一项保存失败', 'error');
          return null;
        }
      },
      openTradeRecord() {
        context.events?.emit('project-center:open-entry', { page: 'tk' });
      },
    };
    const refreshButton = root.querySelector('[data-event-action="refresh"]');
    refreshButton?.addEventListener('click', refresh);
    const unbind = view.bind(actions);
    const unsubscribe = context.events?.on('page:changed', ({ page }) => {
      if (page === 'event') refresh();
      else { rememberJudgmentDraft(); selection += 1; materials.stop(); materialsDesk = null; judgment.stop(); stopReading(); }
    });
    dispose = () => {
      rememberJudgmentDraft();
      active = false;
      selection += 1;
      materials.stop();
      materialsDesk = null;
      judgment.stop();
      stopReading();
      unbind();
      refreshButton?.removeEventListener('click', refresh);
      if (typeof unsubscribe === 'function') unsubscribe();
    };
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

function findTradePlanItem(plan = {}, itemId = '') {
  return [
    ...(plan.auto?.items || []),
    ...(plan.manual?.items || []),
  ].find((item) => item.id === itemId) || null;
}
