export function buildLineupPrompt(input = {}) {
  return [
    '小雪，BP 出来了，按阵容八步法看这把。', '',
    `比赛：${input.matchName || '待补'}`,
    '蓝色方：待补队伍 + 五英雄', '红色方：待补队伍 + 五英雄', '首发 / ban-pick：待补',
    `盘口 / 水位：${[input.marketDirection, input.oddsScore].filter(Boolean).join(' / ') || '待补'}`,
    `我赛前想法：${input.preThought || input.preMatchThought || '待补'}`, `备注：${input.review || '待补'}`, '',
    input.lineupText ? `我粘贴的 BP/阵容：\n${input.lineupText}` : '我粘贴的 BP/阵容：待补', '',
    '请走 lol-lineup-analysis：阵容确认、控制量化、三维加权、线权与时间边界、阵容构建核心链、BP 控制链与 24 场景、六条预检。',
    '最后只判断赛前结论保留 / 降权 / 取消 / 等待，以及哪些盘口是不碰项；不要直接给买谁。',
  ].join('\n');
}

export function buildAnalystPrompt(team, lineup) {
  const normalized = normalizeLineupText(lineup || '未粘贴 BP/阵容，先补：蓝色方 / 红色方 / 五个位置 / 关键 ban pick。');
  return [
    '【复制这段去问小雪】', '',
    '请按 lol-lineup-analysis 阵容八步法处理这场 BP/阵容，不要直接下交易结论，先补齐判断链：', '',
    '1. 阵容确认', team ? `当前选择队伍：${team}` : '当前选择队伍：未选择', normalized, '',
    '2. 控制量化待算', '- 硬控 / 软控 / 开团 / 反开 / 留人 / 保护分别列数。', '- 标出关键控制链是否稳定、是否依赖闪现或先手视野。', '',
    '3. 基本面/TS待带入', '- 带入两队 mu / σ / TS / risk_gap / 样本置信度。', '- 对照当前版本理解、队伍风格和 BO 场景。', '',
    '4. 线权时间边界待判断', '- 1-6级、首巢虫/小龙、14分钟前镀层、一先锋/二龙团分别判断线权。', '- 写清哪一路是阵容发动机，哪一路只要不炸就行。', '',
    '5. 核心链/24 场景待定位', '- 定位主要赢法：开团链、单带链、poke/消耗链、保护后排链或前中期滚雪球链。', '- 拆 2-4 个关键场景：一级设计、第一波资源团、中期转线、远古资源团。', '',
    '明确：复制这段去问小雪；本页面只整理提示，不调用 LLM、不保存。',
  ].join('\n');
}

export function normalizeLineupText(text = '') {
  return text.replace(/；/g, '\n').split('\n').map((item) => item.trim()).filter(Boolean).map((item) => `- ${item}`).join('\n');
}
