export const TRADE_RESULTS = Object.freeze(['未结算', '赢', '输', '走水', '放弃']);

export function normalizeTradeResult(value) {
  return TRADE_RESULTS.includes(value) ? value : '未结算';
}

export function stripResultLine(text) {
  return String(text || '')
    .replace(/(?:^|\n)\s*结果[:：]\s*(?:未结算|赢|输|走水|放弃)\s*(?=\n|$)/g, '')
    .trim();
}

export function withResultLine(review, result) {
  const clean = stripResultLine(review);
  return [`结果：${normalizeTradeResult(result)}`, clean].filter(Boolean).join('\n');
}

export function getMarketNoteResult(record) {
  const match = String(record?.review || '')
    .match(/(?:^|\n)\s*结果[:：]\s*(未结算|赢|输|走水|放弃)\s*(?=\n|$)/);
  return normalizeTradeResult(match?.[1]);
}

export function getMarketNoteDate(record) {
  for (const value of [record?.match_time, record?.created_at, record?.updated_at].filter(Boolean)) {
    const date = new Date(String(value).replace(' ', 'T'));
    if (!Number.isNaN(date.getTime())) return date;
  }
  return null;
}

export function isWithinRange(record, range, now = Date.now()) {
  if (range === 'all') return true;
  const days = range === '7d' ? 7 : (range === '30d' ? 30 : 0);
  if (!days) return true;
  const date = getMarketNoteDate(record);
  return Boolean(date) && now - date.getTime() <= days * 86400000;
}

export function filterMarketNotes(records, filters = {}, now = Date.now()) {
  const range = filters.range || 'all';
  const result = filters.result || 'all';
  const keyword = String(filters.keyword || '').trim().toLowerCase();
  return (records || []).filter((record) => {
    if (!isWithinRange(record, range, now)) return false;
    if (result !== 'all' && getMarketNoteResult(record) !== result) return false;
    if (!keyword) return true;
    return [
      record.match_name, record.direction, record.total_lean, record.score_note,
      record.reason, record.review, record.linked_team, gameLabel(record.game),
    ].filter(Boolean).join(' ').toLowerCase().includes(keyword);
  });
}

export function buildFilterSummary(total, shown, filters = {}) {
  const range = { '7d': '最近 7 天', '30d': '最近 30 天', all: '全部最近记录' }[filters.range] || '全部最近记录';
  const result = filters.result && filters.result !== 'all' ? `结果：${filters.result}` : '全部结果';
  const keyword = filters.keyword ? `，关键词：${filters.keyword}` : '';
  return `当前筛选：${range} / ${result}${keyword}；显示 ${shown} / 已加载 ${total} 条原始 market_notes 记录。`;
}

export function gameLabel(game) {
  return { lol: 'LOL', cs: 'CS', valorant: '无畏', football: '足球' }[game] || game || 'LOL';
}

export function buildMarketNotePayload(values = {}, context = {}) {
  return {
    game: context.game || 'lol',
    match_name: String(values.matchName || '').trim(),
    match_time: values.matchTime || '',
    direction: values.direction || '',
    total_lean: values.totalLean || '放弃',
    score_note: values.scoreNote || '',
    reason: values.reason || '',
    confidence: values.confidence || '中',
    review: withResultLine(values.review, values.result),
    linked_team: context.selectedTeam || '',
  };
}

export function buildDailyTradeDraft(teamLine, context) {
  const lines = [teamLine];
  if (context?.compare) {
    const a = context.team_a || {};
    const b = context.team_b || {};
    lines.push(`TS底表：${a.team || '-'} mu ${format1(a.mu)} / σ ${format1(a.sigma)} / TS ${format1(a.ts)}（${a.sample_confidence || '-'}，${a.volatility_tier || '-'}）；${b.team || '-'} mu ${format1(b.mu)} / σ ${format1(b.sigma)} / TS ${format1(b.ts)}（${b.sample_confidence || '-'}，${b.volatility_tier || '-'}）`);
    lines.push(context.compare.risk_note || '', context.compare.daily_summary || '', context.compare.market_note || '');
  } else {
    lines.push('TS底表：待补对手后自动带入 mu / σ / TS 对比');
  }
  lines.push('盘口 / 方向：', '赔率 / 比分：', '我的判断：', '市场分歧点：', '不碰项：', '备注 / 复盘原始记录：');
  lines.push('边界：只填交易时手写记录，保存到 market_notes；不自动交易，最终判断由钧钧自己定。');
  return lines.filter(Boolean).join('\n');
}

export function buildTeamPrefill(selectedTeam, teamInfo = {}, schedule = null, matchContext = null) {
  const team = String(selectedTeam || '').trim();
  if (!team) return { ok: false, message: '先选择 LOL 队伍' };
  const a = schedule?.team_a || '';
  const b = schedule?.team_b || '';
  const opponent = a === team ? b : (b === team ? a : '');
  const matchName = schedule ? [a || team, b || 'TBD'].filter(Boolean).join(' vs ') : `${team} vs `;
  const matchTime = [schedule?.date, schedule?.time].filter(Boolean).join('T');
  const line = `对象：${team}${teamInfo.region ? `（${teamInfo.region}）` : ''}${opponent ? ` vs ${opponent}` : '，对手待补'}`;
  return {
    ok: true, game: 'lol', matchName, matchTime, opponent,
    reason: buildDailyTradeDraft(line, matchContext),
    message: opponent ? `已带入赛前参考：${team} vs ${opponent}` : `已带入对象：${team} · 待补对手`,
  };
}

export function buildTkDraft(record, selectedTeam = '') {
  if (!record) return null;
  const team = record.linked_team || selectedTeam || '';
  const review = stripResultLine(record.review || '');
  return {
    source: 'market-notes', sourceId: record.id, team,
    tags: ['盘口草稿', gameLabel(record.game), team].filter(Boolean),
    content: [
      `【结论】${gameLabel(record.game)} ${record.match_name}：盘口方向 ${record.direction || '未写'}，大小 ${record.total_lean || '放弃'}，比分判断 ${record.score_note || '-'}`,
      `【结果】${getMarketNoteResult(record)}`,
      `【队伍】${team || '未关联'}${team ? '（盘口草稿队伍标签）' : ''}`,
      `【因果】${record.reason || '待补'}`,
      `【备注】${review || '未补'}`,
      `【来源】盘口草稿 #${record.id}`,
    ].join('\n'),
  };
}

export function buildLineupHandoffDto(values = {}) {
  return {
    source: 'market-notes',
    matchName: String(values.matchName || '').trim(),
    marketDirection: String(values.direction || '').trim(),
    oddsScore: String(values.scoreNote || '').trim(),
    preMatchThought: String(values.reason || '').trim(),
    review: String(values.review || '').trim(),
  };
}

function format1(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) : '-';
}
