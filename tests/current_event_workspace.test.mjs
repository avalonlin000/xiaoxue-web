import assert from 'node:assert/strict';
import test from 'node:test';

import { buildMatchPrompt } from '../src/modules/current-event/service.js';


test('the Xiaoxue prompt lets one match move naturally across three stages', () => {
  const prompt = buildMatchPrompt({
    match: { team_a: 'A', team_b: 'B' },
  }, { stage: 'LPL', format: 'BO3' });

  assert.match(prompt, /单场交易推演/);
  assert.match(prompt, /赛前、赛中、赛后/);
  assert.match(prompt, /自然切换/);
  assert.match(prompt, /是否采用由我确认/);
  assert.doesNotMatch(prompt, /先看版本|推进一个/);
  assert.doesNotMatch(prompt, /封存|解封|编号/);
});
