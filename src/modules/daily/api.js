import { apiRequest } from '../../shared/api/client.js';

export function fetchDailyContent(date = 'today') {
  return apiRequest(`/daily-content?date=${encodeURIComponent(date)}`);
}
