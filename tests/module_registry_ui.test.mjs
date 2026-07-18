import assert from 'node:assert/strict';
import test from 'node:test';

import { loadAndMountModules, mountModules } from '../src/app/module-registry.js';


test('one broken frontend module does not stop later modules from mounting', async () => {
  const mounted = [];
  const modules = [
    { id: 'teams', name: '队伍资料', mount: async () => mounted.push('teams') },
    { id: 'daily', name: '每日准备', mount: async () => { throw new Error('missing report'); } },
    { id: 'tk', name: 'TK资料库', mount: async () => mounted.push('tk') },
  ];

  const result = await mountModules(modules, {});

  assert.deepEqual(mounted, ['teams', 'tk']);
  assert.equal(result.status, 'degraded');
  assert.equal(result.modules.teams.status, 'healthy');
  assert.equal(result.modules.daily.status, 'broken');
  assert.equal(result.modules.tk.status, 'healthy');
});

test('disabled frontend modules do not degrade the app', async () => {
  const result = await mountModules([
    { id: 'legacy', name: '旧入口', enabled: false, mount: async () => {} },
  ], {});

  assert.equal(result.status, 'healthy');
  assert.equal(result.modules.legacy.status, 'disabled');
});

test('one module import failure does not stop other module imports', async () => {
  const mounted = [];
  const result = await loadAndMountModules([
    { id: 'daily', name: '每日准备', load: async () => { throw new Error('bad bundle'); } },
    {
      id: 'tk',
      name: 'TK资料库',
      load: async () => ({ default: { id: 'tk', name: 'TK资料库', mount: async () => mounted.push('tk') } }),
    },
  ], {});

  assert.deepEqual(mounted, ['tk']);
  assert.equal(result.modules.daily.status, 'broken');
  assert.equal(result.modules.tk.status, 'healthy');
});

test('mounted module handles are exposed through the registry public result', async () => {
  const result = await mountModules([
    { id: 'daily', name: '每日准备', async mount() { return { actions: { refresh: true } }; } },
  ], {});

  assert.equal(result.handles.daily.actions.refresh, true);
});
