import { apiRequest } from '../../shared/api/client.js';
import { buildMarketReviewPayload } from './review-model.js';

// 盘口判断的唯一持久正源是 category=market 的交易 TK；
// /api/market-notes 只是只读兼容投影，这里所有写动作都落在 /api/trading-tk。
const MARKET_CATEGORY = 'market';
const SOURCE_COMMAND = '盘口记录页手写';

function marketStatement(body = {}) {
  const name = String(body.match_name || '').trim() || '盘口判断';
  const bits = [
    body.direction ? `方向 ${body.direction}` : '',
    body.total_lean ? `大小 ${body.total_lean}` : '',
    body.score_note ? `比分判断 ${body.score_note}` : '',
  ].filter(Boolean);
  return [`【${name}】`, bits.join('｜')].filter(Boolean).join(' ');
}

function marketContext(body = {}) {
  return [
    body.reason,
    body.review,
    body.match_time ? `时间 ${body.match_time}` : '',
    body.confidence ? `信心 ${body.confidence}` : '',
  ].filter(Boolean).join('\n');
}

export const fetchMarketNotes = (game, limit = 200) =>
  apiRequest(`/market-notes?game=${encodeURIComponent(game)}&limit=${encodeURIComponent(limit)}`);

export function createMarketNote(body = {}) {
  const team = String(body.linked_team || '').trim();
  return apiRequest('/trading-tk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      category: MARKET_CATEGORY,
      statement: marketStatement(body),
      context: marketContext(body),
      scope: team ? 'team' : 'global',
      subject: team,
      source_command: SOURCE_COMMAND,
    }),
  });
}

// 复盘预览在本地生成，不再请求已退役的预览接口。
export function previewMarketReview(_id, body = {}) {
  const values = buildMarketReviewPayload(body || {});
  const lines = [
    `结果：${values.result}`,
    values.actual_score ? `实际比分：${values.actual_score}` : '',
    values.correct_points ? `看对：${values.correct_points}` : '',
    values.wrong_points ? `看错：${values.wrong_points}` : '',
    values.calibration ? `校准：${values.calibration}` : '',
  ].filter(Boolean);
  return Promise.resolve({ review_text: lines.join('\n'), targets: values.destinations });
}

export function commitMarketReview(id, body = {}) {
  const values = buildMarketReviewPayload(body || {});
  const note = [
    `结果 ${values.result}`,
    values.actual_score ? `实际比分 ${values.actual_score}` : '',
    values.correct_points ? `看对 ${values.correct_points}` : '',
    values.wrong_points ? `看错 ${values.wrong_points}` : '',
    values.calibration ? `校准 ${values.calibration}` : '',
  ].filter(Boolean).join('；');
  return apiRequest(`/trading-tk/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'confirmed', review_note: note }),
  });
}

// 交易 TK 只有状态流转，没有硬删除；这里的“删除”改为标记失效，原文保留可查。
export function deleteMarketNote(id) {
  return apiRequest(`/trading-tk/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'invalid', review_note: '前端标记失效' }),
  });
}

export async function createTeamTradingNote(body = {}) {
  const text = String(body.text || '').trim();
  const matched = text.match(/记到\s*([A-Za-z][A-Za-z0-9]*)\s*[：:]\s*(\S[\s\S]*)$/);
  if (!matched) {
    return { ok: false, detail: '写成「小雪记到 HLE：规律内容」，我才能认队伍并写进交易 TK。' };
  }
  const team = matched[1].toUpperCase();
  const statement = matched[2].trim();
  const saved = await apiRequest('/trading-tk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      category: MARKET_CATEGORY,
      statement,
      scope: 'team',
      subject: team,
      source_command: '口述记到队伍',
    }),
  });
  if (saved?.ok === false) {
    return { ok: false, detail: saved.detail || saved.message || '未写入正式 TK' };
  }
  return { ok: true, team, note: { market_label: '', market: '' }, saved };
}
