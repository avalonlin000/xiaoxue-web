export async function writeClipboard(text) {
  if (!navigator.clipboard?.writeText) return false;
  await navigator.clipboard.writeText(text);
  return true;
}

import { apiRequest } from '../../shared/api/client.js';

export function fetchAnalyst(team, analyst) {
  return apiRequest(`/analyst/${encodeURIComponent(team)}?analyst=${encodeURIComponent(analyst)}`);
}
