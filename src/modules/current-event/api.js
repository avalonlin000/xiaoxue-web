import { apiRequest } from '../../shared/api/client.js';

export function fetchEventKnowledge(query = 'LPL', limit = 12) {
  return apiRequest(`/tk/search?q=${encodeURIComponent(query)}&team=&limit=${limit}`);
}

export function fetchCurrentEvent() {
  return apiRequest('/current-event');
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

export function fetchMatchWorkspace(match = {}) {
  return apiRequest(`/current-event/match-workspace?${matchParams(match).toString()}`);
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

export function saveMatchWorkspace(payload) {
  return apiRequest('/current-event/match-workspace', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}

export function saveMatchChange(payload) {
  return apiRequest('/current-event/match-workspace/changes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}
