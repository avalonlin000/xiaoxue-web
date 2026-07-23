import * as api from './api.js';
import { createTeamsService } from './service.js';
import { createTeamsView, markTeamsModule, renderFundamentalsTable } from './view.js';


let active = null;

export async function mount(context = {}) {
  if (active) active.unmount();
  const view = createTeamsView(document);
  const service = createTeamsService({ view, appContext: context.appContext, events: context.events });
  active = service;
  try {
    await service.mount();
  } catch (error) {
    service.unmount();
    active = null;
    throw error;
  }
  return { actions, unmount };
}

export function unmount() {
  active?.unmount();
  active = null;
}

function invoke(method, ...args) {
  if (!active) throw new Error('队伍资料模块尚未挂载');
  return active[method](...args);
}

export const actions = Object.freeze({
  selectTeam: (...args) => invoke('selectTeam', ...args),
  loadFundamentals: (...args) => invoke('loadFundamentals', ...args),
  markDirty: (...args) => invoke('markDirty', ...args),
  save3D: (...args) => invoke('save3D', ...args),
  getTeamInfo: (code = '') => active?.getTeamInfo(code)
    || { short_name: code, name: code, region: '' },
  snapshot: () => active?.snapshot()
    || { team: '', teams: [], threeDimensional: null, dirty: false, fundScope: 'all' },
  toggleTeamDropdown: (...args) => invoke('toggleTeamDropdown', ...args),
  closeTeamDropdown: (...args) => invoke('closeTeamDropdown', ...args),
  applyEditCommand: (...args) => invoke('applyEditCommand', ...args),
});

export const {
  fetchFundamentals, fetchMatchContext, fetchTeamBundle, fetchTeams,
  fetchUpcomingSchedule, saveTeam3D,
} = api;

export { createTeamsService, createTeamsView, markTeamsModule, renderFundamentalsTable };

export default { id: 'teams', name: '队伍资料', mount, unmount, actions };
