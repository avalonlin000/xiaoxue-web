export const MODULE_LOADERS = [
  { id: 'teams', name: '队伍资料', contract_ids: ['ts_strength', 'team_profile', 'attention_config'], load: () => import('../modules/teams/index.js') },
  { id: 'current-event', name: '当前赛事', contract_ids: ['current_match', 'team_profile', 'version_lineup', 'attention_config'], load: () => import('../modules/current-event/index.js') },
  { id: 'stage-review', name: '沉淀候选', contract_ids: ['daily_knowledge'], load: () => import('../modules/stage-review/index.js') },
  { id: 'tk-library', name: 'TK资料库', contract_ids: ['tk', 'daily_knowledge'], load: () => import('../modules/tk-library/index.js') },
  { id: 'market-notes', name: '盘口记录', contract_ids: ['tk'], load: () => import('../modules/market-notes/index.js') },
  { id: 'project-center', name: '项目中心', contract_ids: [], load: () => import('../modules/project-center/index.js') },
];
