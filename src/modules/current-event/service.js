import {
  fetchCurrentEvent,
  fetchCurrentEventDashboard,
  fetchEventKnowledge,
  fetchGlobalVersionUnderstanding,
  fetchTradingMethods,
  fetchEventScopeMaterials,
  fetchJudgmentContext,
  requestJudgmentDiscussion,
  fetchMatchDesk,
  fetchGolSeriesEvidence,
  fetchRecentMatchRuns,
  fetchMatchMaterials,
  prepareMatchMaterials,
  focusMatchRun,
  pauseMatchRun,
  saveMatchTradeEntry,
  saveTradePlanManual,
  createTradePlanItem,
  updateTradePlanItem,
  deleteTradePlanItem,
  restoreTradePlanItem,
  reorderTradePlanItem,
  startMatchRun,
} from './api.js';

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

export async function loadCurrentEventWorkspace(date = 'today') {
  const [dashboard, recent, methods, versionUnderstanding] = await Promise.all([
    fetchCurrentEventDashboard(date),
    fetchRecentMatchRuns(12),
    fetchTradingMethods(),
    fetchGlobalVersionUnderstanding().catch(() => null),
  ]);
  const context = dashboard.context || await fetchCurrentEvent();
  const [payload, eventMaterials] = await Promise.all([
    fetchEventKnowledge(context.knowledge_query || context.event, 8),
    fetchEventScopeMaterials(context.event || '').catch(() => null),
  ]);
  return {
    context,
    eventMaterials,
    matches: dashboard.matches || [],
    recentMatches: recent.matches || [],
    methods: methods.methods || [],
    versionUnderstanding: versionUnderstanding?.data || null,
    date: dashboard.date || date,
    items: (payload.results || []).map((item) => ({
      title: item.concept || item.id || '赛事资料', summary: item.content || '', date: item.date || '',
    })),
  };
}

export function loadMatchDesk(match = {}) {
  return fetchMatchDesk(match);
}

function readingHash(value) {
  const text = JSON.stringify(value);
  let left = 2166136261; let right = 5381;
  for (let index = 0; index < text.length; index += 1) {
    left = Math.imul(left ^ text.charCodeAt(index), 16777619);
    right = Math.imul(right, 33) ^ text.charCodeAt(index);
  }
  return `${(left >>> 0).toString(36)}${(right >>> 0).toString(36)}`;
}

function readingText(value) {
  return String(value ?? '').replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, '')
    .replace(/(?:\*\*|`|^#{1,6}\s*|^[-*]\s*)/gm, '')
    .replace(/(?<![A-Za-z0-9])[IPM]\d+(?![A-Za-z0-9])/g, '').replace(/\s+/g, ' ').trim();
}

function readingObject(kind, payload) {
  const result = kind === 'judgment' ? payload : payload.result || {};
  const object = payload.object || result.subject || result.match || {};
  const match = object.match || object;
  const fields = [object.event || match.event || match.stage || '', object.team || '', match.team_a || '', match.team_b || '',
    match.match_date || match.date || '', match.match_time || match.time || '', match.match_format || match.format || '', payload.as_of || object.as_of || ''];
  return [kind, ...fields.map((value) => String(value).trim()), kind === 'judgment' ? payload.method?.id || '' : ''];
}

function readingSnapshot(kind, payload) {
  const result = kind === 'judgment' ? payload : payload.result || {};
  const rows = [];
  const add = (position, item, section = '') => {
    const text = typeof item === 'string' ? item : item.text || item.content || item.summary || '';
    if (!String(text).trim()) return;
    const group = readingHash([section, item.kind || '', item.url || '', item.method_id || '', item.title || '']);
    const content = [text, item.conditions, item.counterevidence, item.why_relevant, item.evidence_quote,
      item.recognition, item.verification, item.inference_scope,
      ...(item.evidence || []).flatMap((entry) => [entry.text, entry.kind, entry.url])];
    rows.push({ position, group, signature: readingHash(content.map(readingText)) });
  };
  if (kind === 'judgment') {
    (result.contents || []).forEach((item, index) => add(`content:${index}`, item, 'content'));
    (result.analysis || []).forEach((item, index) => add(`analysis:${index}`, item, 'analysis'));
  } else {
    (result.sections || []).filter((section) => ['digest', 'analysis', 'comparison'].includes(section.id))
      .forEach((section) => (section.items || []).forEach((item, index) => add(`${section.id}:${index}`, item, section.id)));
  }
  const meta = readingHash([readingText(result.summary), (result.limitations || []).map(readingText).sort()]);
  return { version: 1, revision: result.revision || '', rows, meta,
    signature: readingHash([meta, rows.map((row) => `${row.group}:${row.signature}`).sort()]) };
}

// Local reading receipts contain hashes and a displayed revision, never article
// bodies or personal judgments. Reads alone do not mark background data as seen.
export function createReadingTracker({ storage = null } = {}) {
  const session = new Map();
  let available = Boolean(storage);
  return {
    reset() { session.clear(); },
    inspect(kind, payload = {}) {
      const key = `xiaoxue:reading:v1:${readingHash(readingObject(kind, payload))}`;
      const snapshot = readingSnapshot(kind, payload);
      const previousSession = session.get(key);
      if (previousSession?.snapshot.signature === snapshot.signature) return { ...previousSession, snapshot };
      let prior = null;
      try {
        const raw = storage?.getItem(key);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed.version === 1 && Array.isArray(parsed.rows) && typeof parsed.meta === 'string') prior = parsed;
        }
      } catch (error) { if (!(error instanceof SyntaxError)) available = false; }
      const existing = (prior?.rows || []).map((row) => ({ ...row, consumed: false }));
      const changedRows = [];
      if (prior) for (const row of snapshot.rows) {
        const same = existing.find((old) => !old.consumed && old.group === row.group && old.signature === row.signature);
        if (same) same.consumed = true;
        else {
          const unseen = existing.find((old) => !old.consumed && old.group === row.group && old.signature === null);
          if (unseen) unseen.consumed = true;
          else changedRows.push(row.position);
        }
      }
      const groups = new Set(snapshot.rows.map((row) => row.group));
      const removed = prior ? existing.filter((row) => !groups.has(row.group)).length : 0;
      const state = { key, snapshot, prior, known: Boolean(prior), storageAvailable: available,
        changed: Boolean(prior && (changedRows.length || removed || prior.meta !== snapshot.meta)), changedRows, removed,
        statusChanged: Boolean(prior && prior.meta !== snapshot.meta) };
      session.set(key, state); return state;
    },
    mark(state, visiblePositions = null) {
      if (!available || !state?.snapshot || !state.key) return false;
      try {
        let snapshot = state.snapshot;
        if (visiblePositions) {
          const visible = new Set(visiblePositions);
          const previous = (state.prior?.rows || []).map((row) => ({ ...row, consumed: false }));
          const rows = snapshot.rows.map((row) => {
            const old = previous.find((item) => !item.consumed && item.group === row.group);
            if (old) old.consumed = true;
            return { ...row, signature: visible.has(row.position) ? row.signature : old?.signature || null };
          });
          snapshot = { ...snapshot, rows, signature: readingHash([snapshot.meta, rows.map((row) => `${row.group}:${row.signature}`).sort()]) };
        }
        storage.setItem(state.key, JSON.stringify(snapshot)); state.prior = snapshot; return true;
      } catch { available = false; state.storageAvailable = false; return false; }
    },
  };
}

export function judgmentObject(context = {}, desk = null, selected = null, team = '') {
  const match = desk?.match || selected || {};
  const run = desk?.match_run;
  const replay = run?.mode === 'virtual_pre' && !run.result_unlocked;
  let cutoff = String(run?.cutoff_at || '').trim().replace(' ', 'T');
  // Original match-run timestamps are Beijing local time, while the judgment
  // boundary requires an explicit offset. Never interpret them in browser time.
  if (cutoff && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(cutoff)) cutoff += '+08:00';
  return {
    event: match.event || context.event || match.stage || '',
    team, team_a: match.team_a || '', team_b: match.team_b || '',
    match_date: match.match_date || match.date || '', match_time: match.match_time || match.time || '',
    match_format: match.match_format || match.format || '',
    ...(replay ? { as_of: cutoff, blocked: !cutoff } : {}),
  };
}

// A perspective is an ephemeral conversation, never a match-run or knowledge writer.
export function createJudgmentController({
  load = fetchJudgmentContext, discuss = requestJudgmentDiscussion,
  onContext = () => {}, onDiscussion = () => {},
} = {}) {
  let generation = 0;
  let object = {};
  let methodId = '';
  let context = null;
  let history = [];
  let pending = false;
  const reset = () => { generation += 1; context = null; history = []; pending = false; };
  return {
    setObject(value = {}) { reset(); object = { ...value }; methodId = ''; },
    stop() { reset(); methodId = ''; },
    async open(id, overrides = {}) {
      reset(); methodId = id; object = { ...object, ...overrides };
      const current = generation;
      if (object.blocked) {
        context = { status: 'unavailable', limitations: ['这场回放缺少赛前截止时间，暂不读取当前资料以免带入赛后信息。'], discussion_available: false };
        onContext(context); return context;
      }
      try {
        const payload = await load(id, object);
        if (current !== generation) return null;
        context = payload; onContext(payload); return payload;
      } catch {
        if (current !== generation) return null;
        context = { status: 'unavailable', limitations: ['这部分内容暂时读不到，比赛资料仍可正常查看。'], discussion_available: false };
        onContext(context); return null;
      }
    },
    async ask(question) {
      const text = String(question || '').trim();
      if (!text || pending || !methodId || !context?.discussion_available || object.blocked) return null;
      if (text.length > 2000) {
        onDiscussion({ pending: false, error: '这次问题最多2000字，可以缩短后再继续讨论。' }); return null;
      }
      const current = generation;
      pending = true; onDiscussion({ pending: true });
      try {
        const boundedHistory = history.slice(-8).map((row) => ({ ...row,
          content: row.content.length > 4000 ? `${row.content.slice(0, 3970)}\n（此前回答节选）` : row.content,
        }));
        const payload = await discuss(methodId, object, text, boundedHistory);
        if (current !== generation) return null;
        if (!payload?.answer) throw new Error('empty answer');
        history.push({ role: 'user', content: text }, { role: 'assistant', content: payload.answer });
        onDiscussion({ ...payload, question: text, pending: false }); return payload;
      } catch {
        if (current !== generation) return null;
        onDiscussion({ pending: false, error: '这次讨论暂时没有完成，你的问题已保留；可以稍后重试。' }); return null;
      } finally { if (current === generation) pending = false; }
    },
  };
}

export function matchMaterialsForDesk(desk = {}) {
  if (desk.match_run?.mode === 'virtual_pre' && !desk.match_run.result_unlocked) {
    return { suppressed: true, result: null };
  }
  return desk.prepared_materials;
}

export function createMatchMaterialsController({
  prepare = prepareMatchMaterials, read = fetchMatchMaterials,
  schedule = setTimeout, cancel = clearTimeout, pollMs = 1800, onUpdate = () => {},
} = {}) {
  let generation = 0;
  let timer = null;
  const stop = () => {
    generation += 1;
    if (timer !== null) cancel(timer);
    timer = null;
  };
  return {
    stop,
    async start(match, initial = null) {
      stop();
      const current = generation;
      let latest = initial || { task: { state: 'queued' }, result: null };
      onUpdate(latest);
      const failed = () => {
        if (current !== generation) return;
        latest = { ...latest, notice: latest.result
          ? '暂时无法确认更新，已保留已有资料；重新进入这场时会继续核对。'
          : '暂时无法读取准备进度，重新进入这场时会继续核对。' };
        onUpdate(latest);
      };
      const accept = (payload) => {
        if (current !== generation) return;
        if (!payload || typeof payload !== 'object') { failed(); return; }
        latest = { ...payload, result: payload.result || latest.result };
        onUpdate(latest);
        if (['queued', 'running'].includes(payload.task?.state) && payload.task?.id) {
          timer = schedule(async () => {
            timer = null;
            try { accept(await read(payload.task.id)); } catch { failed(); }
          }, pollMs);
        }
      };
      try { accept(await prepare(match)); } catch { failed(); }
      return latest;
    },
  };
}

export function loadGolSeriesEvidence(match = {}, gameId = '') {
  return fetchGolSeriesEvidence(match, gameId);
}

export function buildMatchPrompt(desk = {}, schedule = {}) {
  const match = desk.match || {};
  const lines = [
    `小雪，打开 ${match.team_a || schedule.team_a || ''} vs ${match.team_b || schedule.team_b || ''} 的单场交易推演。`,
  ];
  if (schedule.format || schedule.stage || schedule.time) {
    lines.push(`比赛：${[schedule.time, schedule.stage, schedule.format].filter(Boolean).join(' / ')}`);
  }
  lines.push('我想先聊这场现在最需要看的部分；赛前、赛中、赛后都可以自然切换。已有交易 TK 只作提醒，是否采用由我确认。');
  return lines.join('\n');
}


export {
  focusMatchRun, pauseMatchRun, saveMatchTradeEntry, saveTradePlanManual, startMatchRun,
  createTradePlanItem, updateTradePlanItem, deleteTradePlanItem, restoreTradePlanItem, reorderTradePlanItem,
};
