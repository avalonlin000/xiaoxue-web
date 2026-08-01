import {
  fetchCurrentEvent,
  fetchCurrentEventDashboard,
  fetchEventKnowledge,
  fetchMatchDesk,
  fetchRecentMatchRuns,
  focusMatchRun,
  pauseMatchRun,
  saveMatchChange,
  saveMatchTradeEntry,
  saveMatchWorkspace,
  startMatchRun,
} from './api.js';

export async function loadCurrentEventKnowledge() {
  const context = await fetchCurrentEvent();
  const payload = await fetchEventKnowledge(context.knowledge_query || context.event, 12);
  return {
    context,
    items: (payload.results || []).map((item) => ({
      title: item.concept || item.id || '赛事资料', summary: item.content || '', date: item.date || '',
    })),
  };
}

export async function loadCurrentEventWorkspace(date = 'today') {
  const [dashboard, recent] = await Promise.all([
    fetchCurrentEventDashboard(date),
    fetchRecentMatchRuns(12),
  ]);
  const context = dashboard.context || await fetchCurrentEvent();
  const payload = await fetchEventKnowledge(context.knowledge_query || context.event, 8);
  return {
    context,
    matches: dashboard.matches || [],
    recentMatches: recent.matches || [],
    date: dashboard.date || date,
    items: (payload.results || []).map((item) => ({
      title: item.concept || item.id || '赛事资料', summary: item.content || '', date: item.date || '',
    })),
  };
}

export function loadMatchDesk(match = {}) {
  return fetchMatchDesk(match);
}

export function buildMatchPrompt(desk = {}, schedule = {}) {
  const match = desk.match || {};
  const lines = [
    `小雪，打开 ${match.team_a || schedule.team_a || ''} vs ${match.team_b || schedule.team_b || ''} 的单场交易推演。`,
  ];
  if (schedule.format || schedule.stage || schedule.time) {
    lines.push(`比赛：${[schedule.time, schedule.stage, schedule.format].filter(Boolean).join(' / ')}`);
  }
  lines.push('我这次想先从我正在说的模块进入；版本、赛区、队伍/选手、规律、阵容、市场和执行可随时切换。已有交易 TK 只负责搜索和提醒，是否采用由我确认。');
  return lines.join('\n');
}

export function parseMatchJudgment(text = '') {
  const labels = {
    '方向': 'direction', '理由': 'reasons', '处理': 'handling', '变化条件': 'change_conditions',
  };
  const result = { direction: '', reasons: '', handling: '', change_conditions: '' };
  let active = '';
  String(text).split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;
    const match = line.match(/^(方向|理由|处理|变化条件)\s*[：:]\s*(.*)$/);
    if (match) {
      active = labels[match[1]];
      result[active] = match[2].trim();
    } else if (active) {
      result[active] = [result[active], line].filter(Boolean).join('\n');
    }
  });
  return {
    ok: Object.values(result).every(Boolean),
    value: result,
    message: '请直接贴入小雪的四行回复：方向、理由、处理、变化条件。',
  };
}

export function formatMatchJudgment(current = {}) {
  return [
    `方向：${current.direction || ''}`,
    `理由：${current.reasons || ''}`,
    `处理：${current.handling || ''}`,
    `变化条件：${current.change_conditions || ''}`,
  ].join('\n');
}

export function buildMatchWorkspacePayload(match = {}, current = {}) {
  return {
    game: match.game || 'lol', team_a: match.team_a || '', team_b: match.team_b || '',
    event: match.event || match.stage || match.region || '', match_date: match.match_date || match.date || 'today',
    match_time: match.match_time || match.time || '', match_format: match.match_format || match.format || '',
    ...current,
  };
}

export { focusMatchRun, pauseMatchRun, saveMatchChange, saveMatchTradeEntry, saveMatchWorkspace, startMatchRun };
