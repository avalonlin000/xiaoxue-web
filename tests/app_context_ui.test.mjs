import assert from 'node:assert/strict';
import test from 'node:test';

import { createAppContext } from '../src/app/context.js';


test('modules communicate selected-team changes through a semantic event', () => {
  const context = createAppContext();
  let received = null;
  context.events.on('team:selected', (payload) => { received = payload; });

  context.selectTeam('AL');

  assert.equal(context.selectedTeam, 'AL');
  assert.deepEqual(received, { team: 'AL' });
});

test('one failing event listener does not block other modules', () => {
  const context = createAppContext();
  let received = '';
  context.events.on('team:selected', () => { throw new Error('broken module'); });
  context.events.on('team:selected', ({ team }) => { received = team; });

  context.selectTeam('GEN');

  assert.equal(received, 'GEN');
});
