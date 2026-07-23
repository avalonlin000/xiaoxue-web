import {
  fetchFundamentals, fetchMatchContext, fetchTeamBundle, fetchTeams,
  fetchUpcomingSchedule, saveTeam3D,
} from './api.js';

export function createTeamsService({ view, appContext, events } = {}) {
  const state = { team: '', teams: [], threeDimensional: null, dirty: false, fundScope: 'lpl' };
  const disposers = [];
  let mounted = false;

  async function mount() {
    mounted = true;
    view.bind({
      onToggleTeams: () => view.toggleTeamDropdown(state.teams, selectTeam),
      onScope: loadFundamentals,
      onSave: save3D,
      onDirty: markDirty,
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
    state.dirty = false;
    view.showTeamDetails();
    view.updateTopBar(team);
    view.setDirty(false);
    view.loadingTeam(team);
    if (announce) appContext?.selectTeam?.(team);
    const [profile, wiki, threeDimensional] = await fetchTeamBundle(team);
    if (!mounted || state.team !== team) return snapshot();
    state.threeDimensional = threeDimensional;
    view.renderProfile(wiki?.found ? { ...wiki, source: 'wiki' } : profile, team);
    view.render3D(threeDimensional);
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

  function markDirty() {
    state.dirty = true;
    view.setDirty(true);
  }

  function toggleTeamDropdown() {
    view.toggleTeamDropdown(state.teams, selectTeam);
  }

  function closeTeamDropdown() { view.closeTeamDropdown(); }

  function applyEditCommand(field, value, rawCommand) {
    const applied = view.applyEditCommand(field, value, rawCommand);
    if (applied) markDirty();
    return applied;
  }

  async function save3D() {
    if (!state.team || !state.dirty) return null;
    const body = view.read3D();
    view.saving();
    try {
      const result = await saveTeam3D(state.team, body);
      state.dirty = false;
      state.threeDimensional = { ...(state.threeDimensional || {}), ...body, updated_at: new Date().toLocaleString() };
      view.saved();
      events?.emit?.('teams:3d-saved', { team: state.team });
      return result;
    } catch (error) {
      view.saveFailed();
      throw error;
    }
  }

  function getTeamInfo(code = state.team) {
    return state.teams.find((team) => team.short_name === code)
      || { short_name: code, name: code, region: '' };
  }

  function snapshot() {
    return {
      team: state.team,
      teams: [...state.teams],
      threeDimensional: state.threeDimensional ? { ...state.threeDimensional } : null,
      dirty: state.dirty,
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
    markDirty, save3D, toggleTeamDropdown, closeTeamDropdown, applyEditCommand, getTeamInfo, snapshot,
  };
}

export {
  fetchFundamentals, fetchMatchContext, fetchTeamBundle, fetchTeams,
  fetchUpcomingSchedule, saveTeam3D,
};
