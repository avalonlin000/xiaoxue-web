import { apiRequest } from '../../shared/api/client.js';

export function fetchEventKnowledge(query = 'EWC', limit = 12) {
  return apiRequest(`/tk/search?q=${encodeURIComponent(query)}&team=&limit=${limit}`);
}

export function fetchCurrentEvent() {
  return apiRequest('/current-event');
}
