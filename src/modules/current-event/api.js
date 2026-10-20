import { apiRequest } from '../../shared/api/client.js';

export function fetchEventKnowledge(query = 'LPL', limit = 12) {
  return apiRequest(`/tk/search?q=${encodeURIComponent(query)}&team=&limit=${limit}`);
}

export function fetchCurrentEvent() {
  return apiRequest('/current-event');
}

export function fetchTradingMethods() {
  return apiRequest('/trading-methods');
}

export function fetchEventScopeMaterials(event = '') {
  return apiRequest(`/current-event/scope-materials?${new URLSearchParams({ scope: 'event', event })}`);
}

function judgmentIdentity(methodId, object = {}) {
  const fields = ['event', 'team', 'team_a', 'team_b', 'match_date', 'match_time', 'match_format', 'as_of'];
  return Object.fromEntries([['method_id', methodId], ...fields
    .filter((key) => object[key] !== undefined && object[key] !== '')
    .map((key) => [key, object[key]])]);
}

export function fetchJudgmentContext(methodId, object = {}) {
  return apiRequest(`/current-event/judgment-context?${new URLSearchParams(judgmentIdentity(methodId, object))}`);
}

export function requestJudgmentDiscussion(methodId, object = {}, question = '', history = []) {
  return apiRequest('/current-event/judgment-discussion', {
    method: 'POST', timeoutMs: 130000, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...judgmentIdentity(methodId, object), question, history }),
  });
}

export function fetchGlobalVersionUnderstanding() {
  return apiRequest('/version-understanding/global/current');
}

export function fetchCurrentEventDashboard(date = 'today', limit = 12) {
  return apiRequest(`/current-event/dashboard?date=${encodeURIComponent(date)}&limit=${encodeURIComponent(limit)}`);
}

function matchParams(match = {}) {
  const params = new URLSearchParams({
    team_a: match.team_a || '', team_b: match.team_b || '', game: match.game || 'lol',
    match_date: match.date || match.match_date || 'today', match_time: match.time || match.match_time || '',
    match_format: match.format || match.match_format || '',
  });
  const event = match.event || match.stage || match.region || '';
  if (event) params.set('event', event);
  return params;
}

export function fetchMatchDesk(match = {}) {
  const params = matchParams(match);
  return apiRequest(`/current-event/match-desk?${params.toString()}`);
}

export function prepareMatchMaterials(match = {}) {
  return apiRequest('/current-event/collection', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.fromEntries(matchParams(match))),
  });
}

export function fetchMatchMaterials(taskId) {
  return apiRequest(`/current-event/collection/${encodeURIComponent(taskId)}`);
}

export function fetchGolSeriesEvidence(match = {}, gameId = '') {
  const params = matchParams(match);
  params.set('game_id', gameId);
  return apiRequest(`/current-event/gol-series-evidence?${params.toString()}`);
}

export function fetchMatchRun(match = {}) {
  return apiRequest(`/current-event/match-run?${matchParams(match).toString()}`);
}

export function fetchRecentMatchRuns(limit = 12) {
  return apiRequest(`/current-event/match-runs?limit=${encodeURIComponent(limit)}`);
}

export function startMatchRun(match = {}, mode = 'live', focus = '') {
  const payload = Object.fromEntries(matchParams(match).entries());
  return apiRequest('/current-event/match-run/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, mode, ...(focus ? { focus } : {}) }),
  });
}

export function focusMatchRun(match = {}, focus = '') {
  const payload = Object.fromEntries(matchParams(match).entries());
  return apiRequest('/current-event/match-run/focus', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, focus }),
  });
}

export function pauseMatchRun(match = {}) {
  const payload = Object.fromEntries(matchParams(match).entries());
  return apiRequest('/current-event/match-run/pause', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}

export function saveMatchTradeEntry(match = {}, section = '', content = '') {
  const payload = Object.fromEntries(matchParams(match).entries());
  return apiRequest('/current-event/match-run/entry', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, section, content, confirmed_by_user: section === 'trend' }),
  });
}

export function saveTradePlanManual(match = {}, content = '') {
  const payload = Object.fromEntries(matchParams(match).entries());
  return apiRequest('/current-event/trade-plan/manual', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, content }),
  });
}

function tradePlanPayload(match = {}, values = {}) {
  return { ...Object.fromEntries(matchParams(match).entries()), ...values };
}

export function createTradePlanItem(match = {}, values = {}) {
  return apiRequest('/current-event/trade-plan/items', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tradePlanPayload(match, values)),
  });
}

export function updateTradePlanItem(match = {}, itemId = '', values = {}) {
  return apiRequest(`/current-event/trade-plan/items/${encodeURIComponent(itemId)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tradePlanPayload(match, values)),
  });
}

export function deleteTradePlanItem(match = {}, itemId = '') {
  return apiRequest(`/current-event/trade-plan/items/${encodeURIComponent(itemId)}`, {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tradePlanPayload(match)),
  });
}

export function restoreTradePlanItem(match = {}, itemId = '') {
  return apiRequest(`/current-event/trade-plan/items/${encodeURIComponent(itemId)}/restore`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tradePlanPayload(match)),
  });
}

export function reorderTradePlanItem(match = {}, itemId = '', movement = '') {
  return apiRequest('/current-event/trade-plan/items/reorder', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tradePlanPayload(match, { item_id: itemId, movement })),
  });
}
