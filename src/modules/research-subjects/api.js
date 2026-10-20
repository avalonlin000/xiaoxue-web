import { apiRequest } from '../../shared/api/client.js';

const json = value => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value),
});

export const openSubject = value => apiRequest('/research/subjects', json(value));
export const listSubjects = query => apiRequest(`/research/subjects?query=${encodeURIComponent(query || '')}`);
export const fetchDossier = subjectId => apiRequest(`/research/subjects/${encodeURIComponent(subjectId)}`);
export const addEvent = (subjectId, value) => apiRequest(
  `/research/subjects/${encodeURIComponent(subjectId)}/events`, json(value),
);
export const addMaterial = (subjectId, value) => apiRequest(
  `/research/subjects/${encodeURIComponent(subjectId)}/materials`, json(value),
);
export const addUserNote = (subjectId, value) => apiRequest(
  `/research/subjects/${encodeURIComponent(subjectId)}/notes`, json(value),
);
