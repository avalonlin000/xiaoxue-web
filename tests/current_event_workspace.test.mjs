import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildMatchPrompt,
  buildMatchWorkspacePayload,
  parseMatchJudgment,
} from '../src/modules/current-event/service.js';


test('a four-line Xiaoxue reply becomes one structured current judgment', () => {
  const parsed = parseMatchJudgment(`方向：A 小分\n理由：A 前期主动\n处理：等首局前十分钟\n变化条件：A 打野轮换则取消`);

  assert.equal(parsed.ok, true);
  assert.equal(parsed.value.direction, 'A 小分');
  assert.equal(parsed.value.change_conditions, 'A 打野轮换则取消');
});

test('an incomplete reply is not saved as an opaque match note', () => {
  const parsed = parseMatchJudgment('方向：A 胜\n理由：前期更稳定');

  assert.equal(parsed.ok, false);
});

test('match workspace payload keeps the scheduled match identity', () => {
  const payload = buildMatchWorkspacePayload({
    team_a: 'A', team_b: 'B', stage: 'LPL', date: '2026-07-31', time: '17:00', format: 'BO3',
  }, { direction: 'A 胜' });

  assert.deepEqual(payload, {
    game: 'lol', team_a: 'A', team_b: 'B', event: 'LPL', match_date: '2026-07-31',
    match_time: '17:00', match_format: 'BO3', direction: 'A 胜',
  });
});

test('the Xiaoxue prompt keeps modules free while leaving trend confirmation to the user', () => {
  const prompt = buildMatchPrompt({
    match: { team_a: 'A', team_b: 'B' },
    workspace: {
      current: { direction: 'A 小分', reasons: '前期主动', handling: '等十分钟', change_conditions: '轮换则取消' },
      changes: [{ source: '首发', impact: '削弱', detail: 'A 打野轮换' }],
    },
  }, { stage: 'LPL', format: 'BO3' });

  assert.match(prompt, /单场交易推演/);
  assert.match(prompt, /正在说的模块进入/);
  assert.match(prompt, /可随时切换/);
  assert.match(prompt, /是否采用由我确认/);
  assert.doesNotMatch(prompt, /先看版本|推进一个/);
  assert.doesNotMatch(prompt, /封存|解封|编号/);
  assert.doesNotMatch(prompt, /方向：A 小分|首发 削弱/);
});
