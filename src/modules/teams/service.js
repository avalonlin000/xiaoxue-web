import {
  fetchFundamentals, fetchMatchContext, fetchProfile, fetchTeams,
  fetchUpcomingSchedule,
} from './api.js';

export function createTeamsService({ view, appContext, events } = {}) {
  const state = { team: '', teams: [], fundScope: 'lpl' };
  const disposers = [];
  let mounted = false;

  async function mount() {
    mounted = true;
    view.bind({
      onToggleTeams: () => view.toggleTeamDropdown(state.teams, selectTeam),
      onScope: loadFundamentals,
      onEscape: () => view.closeTeamDropdown(),
      onToggleProfile: () => view.toggleProfile(),
    });
    if (events?.on) {
      disposers.push(events.on('page:changed', ({ page }) => {
        if (page === 'teams') loadFundamentals(state.fundScope).catch(() => {});
      }));
      disposers.push(events.on('team:selected', ({ team }) => {
        if (team && team !== state.team) selectTeam(team, { announce: false }).catch(() => {});
      }));
    }
    try {
      state.teams = await fetchTeams();
      view.setTeams(state.teams, selectTeam);
      view.showOverview();
      await loadFundamentals('lpl');
      view.markStatus('healthy');
    } catch (error) {
      state.teams = [];
      view.setTeams([], selectTeam);
      view.markStatus('broken', error.message || '队伍资料加载失败');
      throw error;
    }
    return snapshot();
  }

  async function selectTeam(code, { announce = true } = {}) {
    const team = String(code || '').trim().toUpperCase();
    if (!team || state.team === team) return snapshot();
    state.team = team;
    view.showTeamDetails();
    view.updateTopBar(team);
    view.loadingTeam(team);
    if (announce) appContext?.selectTeam?.(team);
    const profile = await fetchProfile(team).catch(() => ({ found: false, markdown: '' }));
    if (!mounted || state.team !== team) return snapshot();
    view.renderProfile(profile, getTeamInfo(team));
    events?.emit?.('teams:loaded', { team, teamInfo: getTeamInfo(team) });
    return snapshot();
  }

  async function loadFundamentals(scope = 'all') {
    state.fundScope = scope || 'all';
    view.loadingFundamentals(state.fundScope);
    try {
      const payload = await fetchFundamentals(state.fundScope);
      view.renderFundamentals(payload.teams || [], selectTeam);
      return payload;
    } catch (error) {
      view.errorFundamentals();
      throw error;
    }
  }

  function toggleTeamDropdown() {
    view.toggleTeamDropdown(state.teams, selectTeam);
  }

  function closeTeamDropdown() { view.closeTeamDropdown(); }

  function getTeamInfo(code = state.team) {
    return state.teams.find((team) => team.short_name === code)
      || { short_name: code, name: code, region: '' };
  }

  function snapshot() {
    return {
      team: state.team,
      teams: [...state.teams],
      fundScope: state.fundScope,
    };
  }

  function unmount() {
    mounted = false;
    disposers.splice(0).forEach((dispose) => dispose?.());
    view.unbind();
  }

  return {
    mount, unmount, selectTeam, loadFundamentals,
    toggleTeamDropdown, closeTeamDropdown, getTeamInfo, snapshot,
  };
}

export {
  fetchFundamentals, fetchMatchContext, fetchProfile, fetchTeams,
  fetchUpcomingSchedule,
};
