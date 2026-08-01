import { apiRequest } from '../../shared/api/client.js';

export function fetchStageCandidates(status = 'pending', limit = 100) {
  return apiRequest(`/stage-review/candidates?status=${encodeURIComponent(status)}&limit=${encodeURIComponent(limit)}`);
}

export function updateStageCandidate(candidateId, status) {
  return apiRequest(`/stage-review/candidates/${encodeURIComponent(candidateId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

export function fetchTradingTK(status = 'all', limit = 100) {
  return apiRequest(`/trading-tk?status=${encodeURIComponent(status)}&limit=${encodeURIComponent(limit)}`);
}

export function updateTradingTK(filename, status) {
  return apiRequest(`/trading-tk/${encodeURIComponent(filename)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, review_note: '在阶段整理中由钧钧确认' }),
  });
}
