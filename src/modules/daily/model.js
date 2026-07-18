const MATCH_CONTENT_KINDS = new Set(['daily_report', 'pre_match_card', 'trading_report']);

export function buildPreMatchContentView(data = {}) {
  const date = data.date || 'today';
  const items = (Array.isArray(data.items) ? data.items : [])
    .filter((item) => MATCH_CONTENT_KINDS.has(item.kind || item.id) && item.exists);

  if (items.length === 0) {
    return {
      kind: 'empty',
      date,
      title: '今天暂无赛前内容',
      detail: '有新的日报或赛前判断后，会直接显示在这里。',
      items: [],
    };
  }

  return {
    kind: 'ready',
    date,
    title: '今日赛前内容已更新',
    detail: '下面只显示已经整理好的赛前判断。',
    items,
  };
}

export function buildDailyContentView(data = {}) {
  const date = data.date || 'today';
  const matches = Array.isArray(data.matches) ? data.matches : [];
  const items = Array.isArray(data.items) ? data.items : [];
  const missingRequired = items
    .filter((item) => MATCH_CONTENT_KINDS.has(item.kind || item.id) && !item.exists)
    .map((item) => item.id || item.kind);

  if (!['no_matches', 'content_missing', 'ready'].includes(data.day_state)) {
    return {
      kind: 'unavailable', date, title: `${date} 今日状态无法确认`,
      detail: '服务没有返回明确的赛程状态，因此不展示旧赛程或示例内容。',
      matches: [], missingRequired: [],
    };
  }

  if (data.day_state === 'no_matches') {
    return {
      kind: 'no_matches', date, title: `${date} 今日无比赛`,
      detail: '赛程库没有已确认比赛，不生成赛前日报是正常状态。页面不会拿旧赛程或示例内容代替今天。',
      matches: [], missingRequired: [], action: null,
    };
  }

  if (matches.length === 0) {
    return {
      kind: 'unavailable', date, title: `${date} 今日状态无法确认`,
      detail: '服务状态与赛程数量不一致，因此不展示旧赛程或示例内容。',
      matches: [], missingRequired: [],
    };
  }

  if (data.day_state === 'content_missing' || missingRequired.length > 0) {
    return {
      kind: 'content_missing', date,
      title: `${date} 有 ${matches.length} 场已确认比赛，但赛前内容尚未齐全`,
      detail: '先不要把旧内容当作今天依据；等待真实日报、赛前卡和交易判断内容生成。',
      matches, missingRequired,
    };
  }

  return {
    kind: 'ready', date,
    title: `${date} 有 ${matches.length} 场已确认比赛，赛前内容已就绪`,
    detail: '只展示赛程库与当日文件返回的真实内容。',
    matches, missingRequired: [],
  };
}
