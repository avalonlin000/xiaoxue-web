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
const primaryPages = new Set(['teams', 'event', 'stage', 'tk', 'project']);
const pages = new Set([...primaryPages, 'market']);
let page = 'event';
let projectView = 'book';

function tick() {
  const now = new Date();
  const pad = value => String(value).padStart(2, '0');
  document.getElementById('clock').textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function showPage(nextPage, { view = projectView, history = true } = {}) {
  page = pages.has(nextPage) ? nextPage : 'event';
  projectView = validProjectView(view) ? view : 'book';
  const activeTabId = `tab-${page === 'project' ? 'project-center' : page}`;
  document.querySelectorAll('.workspace-tab').forEach(button => {
    button.classList.toggle('active', button.id === activeTabId);
  });
  document.getElementById(activeTabId)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  document.getElementById('empty-state').style.display = 'none';
  const content = document.getElementById('content-area');
  const projectCenter = document.getElementById('project-center');
  const isProject = page === 'project';
  content.style.display = isProject ? 'none' : 'flex';
  projectCenter.classList.toggle('visible', isProject);
  for (const name of pages) content.classList.toggle(`page-${name}`, !isProject && page === name);
  appContext.events.emit('page:changed', { page });
  if (isProject) appContext.events.emit('project-center:shown', { view: projectView });
  if (page === 'market') marketNotesActions.load().catch(() => {});
  if (page === 'tk') {
    tkLibraryActions.populateTeams(teamsActions.snapshot().teams);
    if (!tkLibraryActions.getState().library.initialized) tkLibraryActions.load(true);
  }
  if (history) updateLocation(page, projectView);
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
  appContext.events.on('project-center:navigate', ({ view }) => showPage('project', { view }));
  appContext.events.on('project-center:open-entry', ({ page: targetPage }) => showPage(targetPage));
  const restoreFromLocation = () => {
    const target = locationTarget();
    showPage(target.page, { view: target.view, history: false });
  };
  window.addEventListener('popstate', restoreFromLocation);
  window.addEventListener('hashchange', restoreFromLocation);
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
      quickReaderRoot: document.getElementById('tk-quick-reader'),
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
    if (team) {
      tkLibraryActions.closeQuickReader();
      tkLibraryActions.quickSearch('', { team, teamOverview: true });
    }
  });
  const target = locationTarget();
  showPage(target.page, { view: target.view, history: false });
}

function validProjectView(value) {
  return ['book', 'architecture', 'objects', 'modules', 'requests', 'deliveries', 'manual'].includes(value);
}

function locationTarget() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, ''));
  const project = raw.match(/^project-center(?:\/(book|architecture|objects|modules|requests|deliveries|manual))?$/);
  if (project) return { page: 'project', view: project[1] || 'book' };
  return { page: pages.has(raw) ? raw : 'event', view: 'book' };
}

function updateLocation(nextPage, nextProjectView) {
  const hash = nextPage === 'project' ? `#project-center/${nextProjectView}` : `#${nextPage}`;
  if (location.hash === hash) return;
  history.pushState({}, '', hash);
}

tick();
setInterval(tick, 1000);
init();
