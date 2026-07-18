import { apiRequest } from '../../shared/api/client.js';

export const fetchMarketNotes = (game, limit = 200) =>
  apiRequest(`/market-notes?game=${encodeURIComponent(game)}&limit=${limit}`);
export const deleteMarketNote = (id) =>
  apiRequest(`/market-notes/${encodeURIComponent(id)}`, { method: 'DELETE' });

export function createMarketNote(body) {
  return apiRequest('/market-notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}

export function createTeamTradingNote(body) {
  return apiRequest('/team-trading-notes/from-text', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}
