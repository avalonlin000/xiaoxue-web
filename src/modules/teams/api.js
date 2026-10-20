import { apiRequest } from '../../shared/api/client.js';

export const fetchTeams = () => apiRequest('/teams');

export const fetchProfile = (code) =>
  apiRequest(`/profile-full/${encodeURIComponent(code)}`);

export const fetchWikiTeam = (code) =>
  apiRequest(`/wiki/team/${encodeURIComponent(code)}`);

export function fetchTeamBundle(code) {
  return Promise.all([
    fetchProfile(code).catch(() => ({ found: false, html: '' })),
    fetchWikiTeam(code).catch(() => ({ found: false, html: '' })),
  ]);
}

export const fetchFundamentals = (scope = 'all') =>
  apiRequest(`/fundamentals/teams?scope=${encodeURIComponent(scope)}&limit=80`);
export const fetchVersionUnderstanding = (team) =>
  apiRequest(`/version-understanding/${encodeURIComponent(team)}`);
export const fetchUpcomingSchedule = (team) =>
  apiRequest(`/schedules?team=${encodeURIComponent(team)}&upcoming=true&limit=1`);
export const fetchMatchContext = (teamA, teamB) =>
  apiRequest(`/fundamentals/msi-match-context?team_a=${encodeURIComponent(teamA)}&team_b=${encodeURIComponent(teamB)}`);
