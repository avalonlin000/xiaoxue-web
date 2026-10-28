import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as service from '../src/modules/current-event/service.js';
import * as view from '../src/modules/current-event/view.js';

function storage() {
  const values = new Map();
  return { values, getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
}
const object = { event: 'S16', team: 'AL' };
const context = (text = '中野节奏影响前十五分钟。', revision = 'r1') => ({
  method: { id: 'team-understanding' }, object, revision, status: 'ok',
  contents: [{ id: `saved-${revision}`, title: '队伍打法', text, kind: 'team_profile', updated_at: '2026-10-20', recognition: 'unknown' }],
  analysis: [], limitations: [],
});

test('first opening does not claim unread changes; only actually displayed content is persisted locally', () => {
  const local = storage(); const tracker = service.createReadingTracker({ storage: local });
  const first = tracker.inspect('judgment', context());
  assert.equal(first.known, false); assert.equal(first.changed, false); assert.equal(local.values.size, 0);
  assert.equal(tracker.inspect('judgment', context('尚未显示的内容')).known, false);
  tracker.mark(first);
  const saved = JSON.parse([...local.values.values()][0]);
  assert.equal(saved.revision, 'r1');
  assert.ok(!JSON.stringify(saved).includes('中野节奏'));
  tracker.reset();
  assert.equal(tracker.inspect('judgment', context()).known, true);
});

test('refresh timestamps, server revisions, markdown, reference IDs and item order alone do not create false changes', () => {
  const local = storage(); const tracker = service.createReadingTracker({ storage: local });
  const original = context(); original.contents.push({ id: 'other', title: '另一条', text: '保持资源先手。', kind: 'team_profile' });
  tracker.mark(tracker.inspect('judgment', original)); tracker.reset();
  const latest = context('**中野节奏**影响前十五分钟。', 'r2');
  latest.contents[0].updated_at = '2026-11-01';
  latest.contents.unshift({ id: 'new-other-id', title: '另一条', text: '保持资源先手。', kind: 'team_profile' });
  assert.equal(tracker.inspect('judgment', latest).changed, false);
});

test('only changed content is highlighted; condition, recognition and removed items remain meaningful updates', () => {
  const local = storage(); const tracker = service.createReadingTracker({ storage: local });
  const old = context(); old.contents.push({ title: '保留条目', text: '仍成立。', kind: 'team_profile' });
  tracker.mark(tracker.inspect('judgment', old)); tracker.reset();
  const next = structuredClone(old); next.revision = 'r2'; next.contents[0].text = '前期野区更需要线权。';
  const diff = tracker.inspect('judgment', next);
  assert.equal(diff.changed, true); assert.deepEqual(diff.changedRows, ['content:0']);
  tracker.mark(diff); tracker.reset();
  next.contents[0].recognition = 'confirmed';
  assert.deepEqual(tracker.inspect('judgment', next).changedRows, ['content:0']);
  tracker.mark(tracker.inspect('judgment', next)); tracker.reset();
  next.contents.pop();
  assert.equal(tracker.inspect('judgment', next).removed, 1);
  const html = view.renderJudgmentContext({ ...next, reading: tracker.inspect('judgment', next) });
  assert.match(html, /上次打开后/); assert.match(html, /1条此前内容已移除/);
});

test('different event, team, match time, perspective and historical cutoff cannot share reading positions', () => {
  const tracker = service.createReadingTracker({ storage: storage() });
  tracker.mark(tracker.inspect('judgment', context())); tracker.reset();
  for (const changed of [
    { object: { ...object, event: 'MSI' } }, { object: { ...object, team: 'BLG' } },
    { method: { id: 'version-understanding' } }, { as_of: '2026-10-19T12:00:00+08:00' },
    { object: { event: 'S16', match: { team_a: 'AL', team_b: 'BLG', match_date: '2026-10-24', match_time: '10:00' } } },
  ]) assert.equal(tracker.inspect('judgment', { ...context(), ...changed }).known, false);
});

test('blocked or corrupt local storage cannot break content and is not silently described as persisted reading', () => {
  const blocked = service.createReadingTracker({ storage: { getItem() { throw new Error('denied'); } } });
  const result = blocked.inspect('judgment', context());
  assert.equal(result.storageAvailable, false);
  assert.equal(blocked.mark(result), false);
  const html = view.renderJudgmentContext({ ...context(), reading: result });
  assert.match(html, /暂不能记住阅读位置/);
  const local = storage(); local.getItem = () => '{broken';
  assert.equal(service.createReadingTracker({ storage: local }).inspect('judgment', context()).known, false);
});

test('prepared material changes stay scoped to the match; raw closed background and task polling states do not raise unread alerts', () => {
  const local = storage(); const tracker = service.createReadingTracker({ storage: local });
  const prepared = { result: { match: { event: 'S16', team_a: 'AL', team_b: 'BLG', match_date: '2026-10-24', match_time: '10:00' }, revision: 'one', status: 'partial', sections: [
    { id: 'digest', selection_status: 'screened', items: [{ title: '作者分析', text: '需注意野区节奏。', conditions: '中路能先动', url: 'https://example.org/a' }] },
    { id: 'news', items: [{ text: '后台原文' }] },
  ], limitations: [] } };
  tracker.mark(tracker.inspect('materials', prepared)); tracker.reset();
  const next = structuredClone(prepared); next.task = { state: 'running' }; next.result.status = 'complete'; next.result.updated_at = '2026-11-01'; next.result.revision = 'two'; next.result.sections[1].items[0].text = '抓取时间更新';
  assert.equal(tracker.inspect('materials', next).changed, false);
  next.result.sections[0].items[0].conditions = '中下两路都能先动';
  const diff = tracker.inspect('materials', next);
  assert.deepEqual(diff.changedRows, ['digest:0']);
  assert.match(view.renderPreparedMaterials({ ...next, reading: diff }), /data-reading-changed="true"/);
});

test('event preparation is readable before the optional perspective directory, without requiring a match', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('id="event-prepared-content"') < html.indexOf('id="event-methods-list"'));
  assert.ok(html.includes('id="event-prepared-content"'));
  assert.match(view.renderPreparedMaterials({ title: '赛事资料', suppressed: true }), /赛前回放不采用当前赛事资料/);
});

test('personal inference evidence is collapsed, safely readable, and changes the reading signature', () => {
  const tracker = service.createReadingTracker({ storage: storage() });
  const old = context(); old.analysis = [{ text: '条件式解释。', evidence: [{ text: '当时实际引用的队伍画像。', url: 'https://example.org/a' }] }];
  tracker.mark(tracker.inspect('judgment', old)); tracker.reset();
  const current = structuredClone(old); current.analysis[0].evidence[0].text = '修订后的实际画像依据。';
  assert.deepEqual(tracker.inspect('judgment', current).changedRows, ['analysis:0']);
  const html = view.renderJudgmentContext(current);
  assert.match(html, /<details class="judgment-origin"><summary>所用依据<\/summary>/);
  assert.match(html, /修订后的实际画像依据/);
  assert.match(html, /href="https:\/\/example.org\/a"/);
  assert.doesNotMatch(html, /details class="judgment-origin" open/);
  tracker.mark(tracker.inspect('judgment', current)); tracker.reset();
  current.analysis[0].evidence[0].url = 'https://example.org/revised';
  assert.deepEqual(tracker.inspect('judgment', current).changedRows, ['analysis:0']);
});

test('default workspace reads prepared event results even with no scheduled matches and makes no write', async () => {
  const original = globalThis.fetch; const calls = [];
  const result = { revision: 'event-one', sections: [{ id: 'digest', items: [{ text: '赛事准备成果。' }] }] };
  globalThis.fetch = async (input, options = {}) => {
    const url = String(input); calls.push({ url, method: options.method || 'GET' });
    let payload = {};
    if (url.includes('/dashboard?')) payload = { context: { event: 'S16 世界赛' }, matches: [] };
    else if (url.includes('/scope-materials?')) payload = { result };
    return { ok: true, headers: { get: () => 'application/json' }, json: async () => payload };
  };
  try {
    const workspace = await service.loadCurrentEventWorkspace();
    assert.deepEqual(workspace.matches, []);
    assert.deepEqual(workspace.eventMaterials.result, result);
    assert.ok(calls.some(({ url }) => url.includes('scope=event') && new URL(url, 'http://localhost').searchParams.get('event') === 'S16 世界赛'));
    assert.ok(calls.every(({ method }) => method === 'GET'));
  } finally { globalThis.fetch = original; }
});

test('a stalled reference search cannot block the current schedule, methods or prepared event content', async () => {
  const original = globalThis.fetch;
  let releaseSearch;
  const stalledSearch = new Promise(resolve => { releaseSearch = resolve; });
  const response = payload => ({ ok: true, headers: { get: () => 'application/json' }, json: async () => payload });
  globalThis.fetch = async input => {
    const url = String(input);
    if (url.includes('/tk/search?')) return stalledSearch;
    if (url.includes('/dashboard?')) return response({ context: { event: 'S16' }, matches: [{ match: { team_a: 'AL', team_b: 'BLG' } }] });
    if (url.includes('/trading-methods')) return response({ methods: [{ id: 'team-understanding' }] });
    if (url.includes('/scope-materials?')) return response({ result: { revision: 'prepared-event' } });
    return response({});
  };
  const pending = service.loadCurrentEventWorkspace();
  let timer;
  try {
    const workspace = await Promise.race([
      pending,
      new Promise(resolve => { timer = setTimeout(() => resolve(null), 100); }),
    ]);
    assert.ok(workspace, 'existing event content must be readable while reference search is stalled');
    assert.equal(workspace.matches[0].match.team_a, 'AL');
    assert.equal(workspace.methods[0].id, 'team-understanding');
    assert.equal(workspace.eventMaterials.result.revision, 'prepared-event');
  } finally {
    clearTimeout(timer);
    releaseSearch(response({ results: [] }));
    await pending;
    globalThis.fetch = original;
  }
});

test('long existing background starts collapsed and is not marked read until explicitly expanded', () => {
  const local = storage(); const tracker = service.createReadingTracker({ storage: local });
  const packet = context();
  packet.contents.push({ title: '旧版本认识', kind: 'version', text: '先核对适用条件。'.repeat(100) });
  const first = tracker.inspect('judgment', packet);
  tracker.mark(first, ['content:0']);
  assert.equal(JSON.parse([...local.values.values()][0]).rows[1].signature, null);
  tracker.reset();
  assert.equal(tracker.inspect('judgment', packet).changed, false);
  const html = view.renderJudgmentContext(packet);
  assert.match(html, /<details data-reading-background><summary>展开已有内容/);
  assert.doesNotMatch(html, /data-reading-background open/);
  const second = tracker.inspect('judgment', packet);
  tracker.mark(second, ['content:0', 'content:1']);
  assert.ok(JSON.parse([...local.values.values()][0]).rows[1].signature);
  tracker.mark(second, ['content:0']);
  assert.ok(JSON.parse([...local.values.values()][0]).rows[1].signature, 'closing a previously read background must retain its receipt');
  tracker.reset(); packet.contents[1].text += '新条件。';
  const changed = tracker.inspect('judgment', packet);
  assert.deepEqual(changed.changedRows, ['content:1']);
  tracker.mark(changed, ['content:0']); tracker.reset();
  assert.deepEqual(tracker.inspect('judgment', packet).changedRows, ['content:1'], 'an unopened changed background must remain unread');
});
