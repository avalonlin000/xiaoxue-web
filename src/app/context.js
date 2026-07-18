import { createEventBus } from './event-bus.js';


export function createAppContext() {
  const events = createEventBus();
  let selectedTeam = '';
  return Object.freeze({
    events,
    get selectedTeam() { return selectedTeam; },
    selectTeam(team) {
      selectedTeam = String(team || '');
      events.emit('team:selected', { team: selectedTeam });
    },
  });
}
