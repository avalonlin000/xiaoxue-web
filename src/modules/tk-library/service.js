export function createLibraryState() {
  return {
    period: 'all', month: '', query: '', team: '', offset: 0, limit: 30,
    total: 0, hasMore: false, results: [], loading: false, initialized: false,
  };
}

export function normalizePeriod(period) {
  return ['today', '7d', '30d', 'month', 'all'].includes(period) ? period : 'all';
}

export function buildLibraryParams(state) {
  return new URLSearchParams({
    period: normalizePeriod(state.period),
    month: state.period === 'month' ? state.month || '' : '',
    q: state.query || '', team: state.team || '', offset: String(state.offset || 0),
    limit: String(state.limit || 30),
  });
}

export function applyLibraryPayload(state, payload = {}, reset = false) {
  const incoming = Array.isArray(payload.results) ? payload.results : [];
  state.results = reset ? incoming : state.results.concat(incoming);
  state.total = Number(payload.total || 0);
  state.hasMore = Boolean(payload.has_more);
  state.offset = state.results.length;
  state.initialized = true;
  return state;
}

export function groupLibraryItems(items = []) {
  const groups = new Map();
  items.forEach((item, index) => {
    const date = item.date || '日期不明';
    if (!groups.has(date)) groups.set(date, []);
    groups.get(date).push({ item, index });
  });
  return [...groups.entries()].map(([date, entries]) => ({ date, entries }));
}

export function librarySummary(state) {
  const filtered = state.query || state.team || state.period !== 'all';
  return `${filtered ? '筛选结果' : '全部TK'} ${state.total} 条 · 已显示 ${state.results.length} 条`;
}

export function libraryPreview(item = {}) {
  let preview = item.preview || '';
  if (item.concept && preview.startsWith(item.concept)) preview = preview.slice(item.concept.length).trim();
  return preview || item.preview || '点击阅读全文查看内容。';
}

export function quickEntryView(entry = {}) {
  const content = entry.content || '';
  return {
    ...entry,
    preview: content.slice(0, 200),
    hasMore: content.length > 200,
    isShell: content.trim().length < 50,
  };
}

export function buildEditorDraft(entry = null, selectedTeam = '') {
  if (!entry) return { filename: '', content: '', tags: '', team: selectedTeam || '' };
  return {
    filename: entry.filename || '', content: entry.content || '',
    tags: Array.isArray(entry.tags) ? entry.tags.join(', ') : String(entry.tags || ''),
    team: selectedTeam || '',
  };
}

export function normalizeExternalDraft(draft = {}) {
  return {
    filename: draft.filename || '', content: draft.content || '',
    tags: Array.isArray(draft.tags) ? draft.tags.join(',') : String(draft.tags || ''),
    team: draft.team || '',
    message: draft.team ? `已带入队伍标签：${draft.team}` : '已生成TK草稿，未关联队伍',
  };
}

export function buildSavePayload(values = {}, selectedTeam = '') {
  const content = String(values.content || '').trim();
  if (content.length < 10) {
    const error = new Error('内容太短（至少10字）');
    error.code = 'content_too_short';
    throw error;
  }
  return {
    filename: String(values.filename || '').trim(),
    body: {
      content, source: '手动录入', tags: values.tags || '',
      team: values.team || selectedTeam || '', player: '',
    },
  };
}
