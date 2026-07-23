export const MODULE_LOADERS = [
  { id: 'teams', name: '队伍资料', load: () => import('../modules/teams/index.js') },
  { id: 'current-event', name: '当前赛事', load: () => import('../modules/current-event/index.js') },
  { id: 'tk-library', name: 'TK资料库', load: () => import('../modules/tk-library/index.js') },
  { id: 'market-notes', name: '盘口记录', load: () => import('../modules/market-notes/index.js') },
];
