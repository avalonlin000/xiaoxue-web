import { loadAndMountModules } from './app/module-registry.js';
import { MODULE_LOADERS } from './app/module-catalog.js';
import { createAppContext } from './app/context.js';
import { renderHealthSummary, summarizeModuleHealth } from './app/health-summary.js';
import { apiRequest } from './shared/api/client.js';
import {
  actions as teamsActions,
  fetchMatchContext,
  fetchUpcomingSchedule,
} from './modules/teams/public.js';
import { actions as tkLibraryActions } from './modules/tk-library/public.js';
import { actions as marketNotesActions } from './modules/market-notes/public.js';

const appContext = createAppContext();
const primaryPages = new Set(['teams', 'event', 'tk']);
const pages = new Set([...primaryPages, 'market']);
let page = 'teams';

function tick() {
  const now = new Date();
  const pad = value => String(value).padStart(2, '0');
  document.getElementById('clock').textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function showPage(nextPage) {
  page = pages.has(nextPage) ? nextPage : 'teams';
  document.querySelectorAll('.workspace-tab').forEach(button => {
    button.classList.toggle('active', button.id === `tab-${page}`);
  });
  document.getElementById('empty-state').style.display = 'none';
  const content = document.getElementById('content-area');
  content.style.display = 'flex';
  for (const name of pages) content.classList.toggle(`page-${name}`, page === name);
  appContext.events.emit('page:changed', { page });
  if (page === 'market') marketNotesActions.load().catch(() => {});
  if (page === 'tk') {
    tkLibraryActions.populateTeams(teamsActions.snapshot().teams);
    if (!tkLibraryActions.getState().library.initialized) tkLibraryActions.load(true);
  }
}

function bindShell() {
  document.addEventListener('click', event => {
    const pageTarget = event.target.closest('[data-shell-page]');
    if (pageTarget) showPage(pageTarget.dataset.shellPage);
    const actionTarget = event.target.closest('[data-shell-action]');
    if (actionTarget?.dataset.shellAction === 'open-market-helper') showPage('market');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      tkLibraryActions.closeEditor();
      tkLibraryActions.closeReader();
      teamsActions.closeTeamDropdown();
    }
  });
}

async function init() {
  bindShell();
  const frontendPromise = loadAndMountModules(MODULE_LOADERS, {
    appContext,
    events: appContext.events,
    marketNotes: {
      bindHandlers: true,
      getSelectedTeam: () => appContext.selectedTeam,
      getTeamInfo: code => teamsActions.getTeamInfo(code),
      getUpcomingSchedule: fetchUpcomingSchedule,
      getMatchContext: fetchMatchContext,
      onTkDraft: draft => tkLibraryActions.openDraft(draft),
    },
    tkLibrary: {
      bindHandlers: true,
      getTeams: () => teamsActions.snapshot().teams,
      getSelectedTeam: () => appContext.selectedTeam,
      readerRoot: document.getElementById('tk-reader-overlay'),
      editorRoot: document.getElementById('tk-editor-overlay'),
      quickSearchRoot: document.getElementById('card-tk'),
    },
    onModuleError(module, error) {
      console.warn(`module ${module.id} unavailable:`, error);
    },
  });
  const backendPromise = apiRequest('/health').catch(error => ({
    status: 'broken',
    modules: { platform: { id: 'platform', name: '应用服务', status: 'broken', message: error.message } },
  }));
  const [frontend, backend] = await Promise.all([frontendPromise, backendPromise]);
  window.xiaoxueModuleStatus = { frontend, backend };
  renderHealthSummary(
    document.getElementById('module-health-summary'),
    summarizeModuleHealth(backend, frontend),
  );
  const teams = teamsActions.snapshot();
  tkLibraryActions.populateTeams(teams.teams);
  appContext.events.on('team:selected', ({ team }) => {
    if (team) tkLibraryActions.quickSearch(team);
  });
  showPage('teams');
}

tick();
setInterval(tick, 1000);
init();
