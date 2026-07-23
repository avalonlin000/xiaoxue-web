import { apiRequest } from '../../shared/api/client.js';

export const fetchTKLibrary = (params) => apiRequest(`/tk/library?${params.toString()}`);
export const fetchTKEntry = (filename) => apiRequest(`/tk/entry/${encodeURIComponent(filename)}`);
export const searchTKEntries = (query, team = '', limit = 15) =>
  apiRequest(`/tk/search?q=${encodeURIComponent(query)}&team=${encodeURIComponent(team)}&limit=${limit}`);
export const fetchTeamTradingNotes = (team, status = 'active', limit = 8) =>
  apiRequest(`/team-trading-notes/${encodeURIComponent(team)}?status=${encodeURIComponent(status)}&limit=${limit}`);
export const deleteTKEntryRequest = (filename) =>
  apiRequest(`/tk/${encodeURIComponent(filename)}`, { method: 'DELETE' });

export function saveTKEntryRequest(filename, body) {
  return apiRequest(filename ? `/tk/${encodeURIComponent(filename)}` : '/tk', {
    method: filename ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
