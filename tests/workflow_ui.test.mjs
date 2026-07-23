import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  buildDailyContentView,
  buildMarketReviewPayload,
  buildPreMatchContentView,
  requestMarketReview,
} from '../src/workflow-ui.js';


test('the workbench navigation contains only long-term knowledge windows', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const tabs = [...html.matchAll(/<button class="workspace-tab[^>]*>([^<]+)<\/button>/g)]
    .map((match) => match[1].trim());

  assert.deepEqual(tabs, ['队伍资料', '当前赛事', 'TK资料库']);
  assert.doesNotMatch(html, /id="card-today-content"|id="card-analyst"|BP 问小雪/);
  assert.match(html, /data-shell-action="open-market-helper"/);
});

test('the frontend never renders schedule or matchup lists', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const source = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8');

  assert.doesNotMatch(html, /today-match-list|msi-schedules|刷新 MSI 赛程/);
  assert.doesNotMatch(source, /renderDailyContentMatches|loadMsiSchedules|renderMsiSchedules/);
});

test('the current event workspace follows the configured LPL stage rather than stale tournaments', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const eventCard = html.match(/<div class="card" id="card-current-event">([\s\S]*?)<\/div>\s*<\/div>/)?.[1] || '';

  assert.match(eventCard, /LPL 2026 第三赛段/);
  assert.match(html, /id="event-plan-status"/);
  assert.match(html, /大周期交易预案/);
  assert.doesNotMatch(eventCard, /MSI|季中赛/);
});

test('refreshing team fundamentals keeps the active LPL scope', () => {
  const source = readFileSync(new URL('../src/modules/teams/view.js', import.meta.url), 'utf8');

  assert.match(source, /refresh-fundamentals[\s\S]*?onScope\?\.\('lpl'\)/);
  assert.doesNotMatch(source, /refresh-fundamentals[\s\S]*?onScope\?\.\('all'\)/);
});

test('the daily view is driven only by processed artifacts, not schedule state', () => {
  const view = buildPreMatchContentView({
    date: '2026-07-14',
    day_state: 'no_matches',
    matches: [{ team_a: 'A', team_b: 'B' }],
    items: [
      { id: 'daily_report', kind: 'daily_report', exists: true, summary: '今天的赛前判断' },
      { id: 'analyst_entry_copy', kind: 'analyst_entry_copy', exists: true },
    ],
  });

  assert.equal(view.kind, 'ready');
  assert.equal(view.items.length, 1);
  assert.equal(view.items[0].summary, '今天的赛前判断');
  assert.doesNotMatch(view.title + ' ' + view.detail, /比赛|赛程|休赛/);
  assert.equal('matches' in view, false);
});


test('buildDailyContentView treats an empty verified schedule as a rest day', () => {
  const view = buildDailyContentView({
    date: '2026-07-13',
    day_state: 'no_matches',
    matches: [],
    items: [
      { id: 'daily_report', kind: 'daily_report', exists: false },
      { id: 'analyst_entry_copy', kind: 'analyst_entry_copy', exists: true },
    ],
  });

  assert.equal(view.kind, 'no_matches');
  assert.match(view.title, /今日无比赛/);
  assert.deepEqual(view.matches, []);
  assert.equal(view.missingRequired.length, 0);
  assert.equal(view.action, null);
  assert.doesNotMatch(view.detail, /复盘/);
});

test('buildDailyContentView distinguishes match-day content gaps from rest days', () => {
  const view = buildDailyContentView({
    date: '2026-07-14',
    day_state: 'content_missing',
    matches: [{ team_a: 'A', team_b: 'B' }],
    items: [{ id: 'daily_report', kind: 'daily_report', exists: false }],
  });

  assert.equal(view.kind, 'content_missing');
  assert.match(view.title, /1 场已确认比赛/);
  assert.deepEqual(view.missingRequired, ['daily_report']);
});

test('buildDailyContentView does not guess a rest day when the server state is absent', () => {
  const view = buildDailyContentView({ date: '2026-07-15', items: [] });

  assert.equal(view.kind, 'unavailable');
  assert.match(view.title, /无法确认/);
});

test('the frontend does not host the post-match review conversation', () => {
  const source = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /开始复盘|startMarketReview/);
});


test('buildMarketReviewPayload keeps review writes unconfirmed by default', () => {
  const payload = buildMarketReviewPayload({
    result: '赢',
    actualScore: '2-1',
    correctPoints: '看对资源团',
    wrongPoints: '低估换线',
  });

  assert.equal(payload.result, '赢');
  assert.equal(payload.actual_score, '2-1');
  assert.deepEqual(payload.destinations, ['market_notes']);
  assert.equal(payload.confirmed, false);
});

test('requestMarketReview turns network failures into a user-facing result', async () => {
  const result = await requestMarketReview(
    async () => { throw new Error('connection reset'); },
    '/api/market-notes/1/review-preview',
    { method: 'POST' },
  );

  assert.equal(result.ok, false);
  assert.match(result.detail, /网络请求失败/);
});
