import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import * as api from '../src/modules/current-event/api.js';
import * as service from '../src/modules/current-event/service.js';
import * as view from '../src/modules/current-event/view.js';
import currentEvent from '../src/modules/current-event/public.js';

const deferred = () => { let resolve; const promise = new Promise((yes) => { resolve = yes; }); return { promise, resolve }; };

test('judgment directory is permanently visible and supports more than five perspectives', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<section[^>]+event-judgment-entry/);
  assert.doesNotMatch(html, /event-methods-list[^\n]*repeat\(5/);
  const cards = Array.from({ length: 6 }, (_, index) => ({ id: `view-${index}`, title: `角度${index}`, purpose: '看内容再判断', status: 'ready', order: index }));
  const rendered = view.renderJudgmentMethods(cards);
  assert.equal((rendered.match(/data-event-method=/g) || []).length, 6);
  assert.match(rendered, /进入判断/);
  assert.match(view.renderJudgmentMethods([{ ...cards[0], status: 'unavailable' }]), /尚未接通/);
});

test('context reads and explicit discussion use identity only; no save or collection endpoint is invoked', async () => {
  assert.equal(typeof api.fetchJudgmentContext, 'function');
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ answer: '只讨论', saved: false }), { headers: { 'content-type': 'application/json' } });
  };
  try {
    const identity = { event: 'S16', team: 'A', as_of: '2026-10-20T12:00:00', private_record: '不能外发' };
    await api.fetchJudgmentContext('version', identity);
    assert.match(calls[0].url, /judgment-context\?/);
    assert.match(calls[0].url, /method_id=version/);
    assert.doesNotMatch(calls[0].url, /private_record|不能外发/);
    assert.equal(calls[0].options.method, undefined);
    await api.requestJudgmentDiscussion('version', identity, '为什么？', [{ role: 'user', content: '上个问题' }]);
    assert.match(calls[1].url, /judgment-discussion$/);
    assert.deepEqual(JSON.parse(calls[1].options.body), { method_id: 'version', event: 'S16', team: 'A', as_of: identity.as_of, question: '为什么？', history: [{ role: 'user', content: '上个问题' }] });
    assert.ok(calls[1].options.signal);
    assert.doesNotMatch(JSON.stringify(calls), /collection|trade-plan|match-run\/start/);
  } finally { globalThis.fetch = original; }
});

test('replay context uses pre-match cutoff, never current data when cutoff is missing', () => {
  const identity = service.judgmentObject({ event: 'S16' }, { match_run: { mode: 'virtual_pre', result_unlocked: false, cutoff_at: '2026-10-19T12:00:00' }, match: { team_a: 'A', team_b: 'B', match_date: '2026-10-19' } });
  assert.equal(identity.as_of, '2026-10-19T12:00:00+08:00');
  assert.equal(service.judgmentObject({}, { match_run: { mode: 'virtual_pre', cutoff_at: '2026-10-19 12:00:00' } }).as_of, '2026-10-19T12:00:00+08:00');
  assert.equal(service.judgmentObject({}, { match_run: { mode: 'virtual_pre', cutoff_at: '2026-10-19T04:00:00Z' } }).as_of, '2026-10-19T04:00:00Z');
  assert.equal(identity.team_a, 'A');
  assert.equal(service.judgmentObject({}, { match_run: { mode: 'virtual_pre', result_unlocked: false } }).blocked, true);
});

test('switching perspectives or objects rejects stale context and stale discussions', async () => {
  assert.equal(typeof service.createJudgmentController, 'function');
  const old = deferred(); const answer = deferred(); const contexts = []; const discussions = [];
  const controller = service.createJudgmentController({
    load: (id) => id === 'old' ? old.promise : Promise.resolve({ method: { id }, discussion_available: true, revision: id }),
    discuss: () => answer.promise,
    onContext: (value) => contexts.push(value), onDiscussion: (value) => discussions.push(value),
  });
  controller.setObject({ event: 'S16' });
  const first = controller.open('old');
  await controller.open('new');
  old.resolve({ method: { id: 'old' } }); await first;
  assert.equal(contexts.at(-1).method.id, 'new');
  const pending = controller.ask('我的问题');
  controller.setObject({ event: 'S16', team: 'C' });
  const before = discussions.length;
  answer.resolve({ answer: '错误串场', saved: false }); await pending;
  assert.equal(discussions.length, before);
});

test('entering a perspective reads actual content, explicit questions alone invoke discussion, and drafts survive material polling', async () => {
  const calls = [];
  const controller = service.createJudgmentController({
    load: async () => ({ discussion_available: true, revision: 'r1' }),
    discuss: async (...args) => { calls.push(args); return { answer: '有依据的回答', saved: false }; },
  });
  controller.setObject({ event: 'S16' }); await controller.open('version');
  assert.equal(calls.length, 0);
  await controller.ask('为什么');
  assert.equal(calls.length, 1);
  assert.equal(calls[0][2], '为什么');
  const rendered = view.renderJudgmentContext({
    method: { title: '版本理解', save_target: 'version' }, object: { event: 'S16' }, status: 'ok', discussion_available: true,
    contents: [{ title: '正式版本', text: '**当前内容**\n- 有依据', recognition: 'confirmed', source_label: '已有版本理解' }],
    analysis: [{ title: '系统解释', text: '暂未确认的看法' }], limitations: [],
  });
  assert.match(rendered, /当前内容/); assert.match(rendered, /继续讨论/); assert.match(rendered, /未自动保存/);
  assert.doesNotMatch(rendered, /\*\*当前内容\*\*|save-judgment|确认采用/);
  const source = readFileSync(new URL('../src/modules/current-event/public.js', import.meta.url), 'utf8');
  const poll = source.match(/onUpdate\(payload\) \{([\s\S]*?)\n      \},/)[1];
  assert.doesNotMatch(poll, /renderJudgment|setObject/);
});

test('context rendering does not leak internal details or turn AI inference into user recognition', () => {
  const html = view.renderJudgmentContext({ method: { title: '画像' }, object: {}, status: 'needs_context', needed: ['team'],
    contents: [{ title: '事实', text: '<img src=x onerror=alert(1)>', recognition: 'unknown', source_label: '/home/private/file' }],
    analysis: [{ text: '候选推导' }], limitations: ['Traceback /home/private/file'] });
  assert.match(html, /队伍/); assert.match(html, /未标记认可/);
  assert.doesNotMatch(html, /<img|Traceback|\/home\/|已认可/);
});

test('material polling leaves the visible perspective, draft question and in-session conversation untouched', () => {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, { innerHTML: '', value: '', textContent: '', querySelector: node, querySelectorAll: () => [] });
    return nodes.get(key);
  };
  const root = { querySelector: node, querySelectorAll: () => [] };
  const current = view.createCurrentEventView(root);
  node('#event-judgment-question').value = '还未提交的问题';
  node('#event-judgment-content').innerHTML = '当前画像依据';
  node('#event-judgment-messages').innerHTML = '本次会话已有回答';
  current.renderMaterials({ result: { summary: '新的准备成果', sections: [] } });
  assert.equal(node('#event-judgment-question').value, '还未提交的问题');
  assert.equal(node('#event-judgment-content').innerHTML, '当前画像依据');
  assert.equal(node('#event-judgment-messages').innerHTML, '本次会话已有回答');
  assert.match(node('[data-match-materials]').innerHTML, /新的准备成果/);
});

test('source body is expandable with safe original links, not dumped into the primary conclusion', () => {
  const html = view.renderJudgmentContext({ contents: [
    { title: '作者分析', text: '筛选后的观点', url: 'https://example.org/analysis', published_at: '2026-10-20T12:00:00+08:00', evidence_quote: '原文连续证据' },
    { title: '不能执行的链接', text: '普通文字', url: 'javascript:alert(1)' },
  ] });
  assert.match(html, /<details class="judgment-origin"><summary>查看出处<\/summary>/);
  assert.match(html, /href="https:\/\/example.org\/analysis"/);
  assert.match(html, /发布于/);
  assert.match(html, /原文连续证据/);
  assert.doesNotMatch(html, /details class="judgment-origin" open|href="javascript:/);
});

test('an existing personal record is identified as the original record, not an unrecognized AI inference', () => {
  const html = view.renderJudgmentContext({ contents: [{ title: '本场判断', text: '我之前记录的想法', recognition: 'user_record' }] });
  assert.match(html, /你的原记录/);
  assert.doesNotMatch(html, /未标记认可|你已认可|已标记认可/);
});

test('historical stage reference is not presented as the current S16 framework', () => {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, { innerHTML: '', textContent: '', classList: { toggle() {} }, closest: () => null });
    return nodes.get(key);
  };
  view.createCurrentEventView({ querySelector: node }).render({ context: { event: 'S16', stage_framework: {
    status: 'historical', content: '旧阶段框架', summary: '已有旧预案', boundary: '只保留查阅，不作为本届当前框架。',
  } } });
  const html = node('#event-plan-status').innerHTML;
  assert.match(html, /历史赛段参考/);
  assert.match(html, /不作为本届当前框架/);
  assert.doesNotMatch(html, /<b>当前赛段框架<\/b>|阶段背景，不是每场必须照抄/);
});

test('perspective analysis removes private evidence IDs while retaining real team and patch names', () => {
  const html = view.renderJudgmentContext({ analysis: [{ text: '依据：I1、I3与P2、M7。T1的BO5表现与26.20版本需要核对。' }] });
  assert.doesNotMatch(html, /\b(?:I1|I3|P2|M7)\b/);
  assert.match(html, /T1的BO5表现与26\.20版本需要核对/);
});

test('multi-turn discussion obeys server question and history bounds without dropping the visible full answer', async () => {
  const calls = []; const updates = [];
  const controller = service.createJudgmentController({
    load: async () => ({ discussion_available: true }),
    discuss: async (...args) => { calls.push(args); return { answer: '长回答'.repeat(1800), saved: false }; },
    onDiscussion: (payload) => updates.push(payload),
  });
  controller.setObject({ event: 'S16' }); await controller.open('version');
  for (let index = 0; index < 6; index += 1) await controller.ask(`第${index}个问题`);
  assert.ok(calls.every((args) => args[3].length <= 8));
  assert.ok(calls.every((args) => args[3].every((row) => row.content.length <= 4000)));
  assert.match(calls[1][3][1].content, /节选/);
  assert.equal(updates.at(-1).answer.length, 5400);
  const count = calls.length;
  await controller.ask('超'.repeat(2001));
  assert.equal(calls.length, count);
  assert.match(updates.at(-1).error, /2000/);
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /id="event-judgment-question" maxlength="2000"/);
});

test('visible discussion translates internal input terminology without editing the returned answer', () => {
  const response = { question: '需要核对什么', answer: 'inputs没有当前首发、画像、三维和TK，不保存。', references: [] };
  const html = view.renderJudgmentDiscussion(response);
  assert.match(html, /现有资料没有当前首发、画像、旧资料项（现归队伍画像）和TK/);
  assert.doesNotMatch(html, /\binputs\b/);
  assert.equal(response.answer, 'inputs没有当前首发、画像、三维和TK，不保存。');
  assert.match(view.renderJudgmentContext({ contents: [{ text: response.answer }] }), /inputs没有当前首发、画像、三维和TK/);
});

test('a long one-paragraph discussion is grouped by complete sentences without deleting or inventing content', () => {
  const sentence = '这是保留全部具体依据和适用条件的一条较长判断，不增加标题，也不让用户只看缺口。';
  const answer = sentence.repeat(10);
  const formatted = view.discussionDisplayText(answer);
  assert.equal(formatted.replace(/\n/g, ''), answer);
  assert.equal(formatted.split('\n\n').length, 5);
  assert.equal(view.discussionDisplayText(`${answer}\n\n已经有的第二段。`), `${answer}\n\n已经有的第二段。`);
  assert.equal(view.discussionDisplayText('两句短答。仍保持原样。'), '两句短答。仍保持原样。');
  const rendered = view.renderJudgmentDiscussion({ answer, references: [{ title: '同一标题' }, { title: '同一标题' }, { title: '不同文章' }] });
  assert.equal((rendered.match(/同一标题/g) || []).length, 1);
  assert.match(rendered, /不同文章/);
  assert.equal((rendered.match(/<p>这是/g) || []).length, 5);
});

test('same-object perspectives share bounded conversation and preserve each answer basis', async () => {
  const calls = [];
  let versionRevision = 'version';
  const controller = service.createJudgmentController({
    load: async (id) => ({ method: { id, title: id === 'version' ? '版本理解' : '队伍画像' }, discussion_available: true, revision: id === 'version' ? versionRevision : id }),
    discuss: async (...args) => { calls.push(args); return { answer: `回答${calls.length}` }; },
  });
  controller.setObject({ event: 'S16', team: 'A' }); await controller.open('version');
  await controller.ask('版本问题'); controller.setDraft('还想追问');
  controller.setObject({ team: 'A', event: 'S16' }); await controller.open('team');
  assert.equal(controller.getSession().draft, '还想追问');
  await controller.ask('换个角度');
  assert.equal(calls[1][3].length, 2);
  assert.match(calls[1][3][0].content, /版本问题/);
  assert.equal(controller.getSession().exchanges[0].method_id, 'version');
  assert.equal(controller.getSession().exchanges[0].revision, 'version');
  assert.equal(controller.getSession().basisChanged, false);
  versionRevision = 'version-updated'; await controller.open('version');
  assert.equal(controller.getSession().basisChanged, true);
});

test('returning to a match restores draft and messages; stop, replay and eviction remain isolated', async () => {
  const controller = service.createJudgmentController({
    load: async () => ({ discussion_available: true, revision: 'r1' }),
    discuss: async () => ({ answer: '留在A场的回答' }),
  });
  const identity = { event: 'S16', team_a: 'A', team_b: 'B', match_date: '2026-10-24' };
  controller.setObject(identity); await controller.open('version');
  for (let index = 0; index < 6; index += 1) await controller.ask(`问题${index}`);
  controller.setDraft('A场未发的问题'); controller.stop();
  controller.setObject({ ...identity, team_a: 'C' }); await controller.open('version');
  assert.equal(controller.getSession().exchanges.length, 0);
  controller.setObject(identity);
  assert.equal(controller.getSession().draft, 'A场未发的问题');
  assert.equal(controller.getSession().exchanges.length, 4);
  controller.setObject({ ...identity, as_of: '2026-10-23T12:00:00+08:00' });
  assert.equal(controller.getSession().exchanges.length, 0);
  controller.setObject(identity);
  for (let index = 0; index < 10; index += 1) controller.setObject({ event: 'S16', team: `队${index}` });
  controller.setObject(identity);
  assert.equal(controller.getSession().exchanges.length, 0);
  assert.equal(controller.getSession().evicted, true);
});

test('equivalent normalized match identities retain discussion when source time or series format spelling changes', async () => {
  const controller = service.createJudgmentController({
    load: async () => ({ discussion_available: true }), discuss: async () => ({ answer: '同一场回答' }),
  });
  controller.setObject({ event: ' S16 ', team_a: 'A', team_b: 'B', match_date: '2026-10-24', match_time: '9:00', match_format: 'BO1' });
  await controller.open('version'); await controller.ask('同一场问题');
  controller.setObject({ event: 's16', team_a: 'a', team_b: 'b', match_date: '2026-10-24', match_time: '2026-10-24 09:00:00', match_format: 'BO3' });
  assert.equal(controller.getSession().exchanges[0].answer, '同一场回答');
  controller.setObject({ event: 's16', team_a: 'a', team_b: 'b', match_date: '2026-10-24', match_time: '10:00' });
  assert.equal(controller.getSession().exchanges.length, 0);
});

test('late same-object perspective answer cannot enter history and a failed question remains a draft', async () => {
  const late = deferred(); let attempts = 0;
  const controller = service.createJudgmentController({
    load: async () => ({ discussion_available: true }),
    discuss: async () => { attempts += 1; if (attempts === 1) return late.promise; throw new Error('offline'); },
  });
  controller.setObject({ event: 'S16' }); await controller.open('version');
  const first = controller.ask('旧视角问题'); await controller.open('team');
  late.resolve({ answer: '旧请求回答' }); await first;
  assert.equal(controller.getSession().exchanges.length, 0);
  assert.equal(controller.getSession().draft, '旧视角问题');
  await controller.ask('失败问题');
  assert.equal(controller.getSession().draft, '失败问题');
});

test('a completed answer retains a newer draft and notices evidence updated by the discussion response', async () => {
  const late = deferred(); let count = 0;
  const controller = service.createJudgmentController({
    load: async () => ({ method: { title: '版本理解' }, discussion_available: true, revision: 'r1' }),
    discuss: async () => { count += 1; return count === 1 ? { answer: '原依据回答', context_revision: 'r1' } : late.promise; },
  });
  controller.setObject({ event: 'S16' }); await controller.open('version'); await controller.ask('第一个问题');
  const pending = controller.ask('第二个问题'); controller.setDraft('我还在写的新问题');
  late.resolve({ answer: '新依据回答', context_revision: 'r2' }); await pending;
  assert.equal(controller.getSession().draft, '我还在写的新问题');
  assert.equal(controller.getSession().pending, false);
  assert.equal(controller.getSession().basisChanged, true);
  assert.equal(controller.getSession().exchanges[0].basis_updated, true);
  assert.equal(controller.getSession().exchanges[1].basis_updated, false);
});

test('view restores cached exchanges and draft after loading a perspective without duplicating messages', () => {
  const nodes = new Map();
  const node = (key) => {
    if (!nodes.has(key)) nodes.set(key, { innerHTML: '', value: '', textContent: '', querySelector: node, querySelectorAll: () => [] });
    return nodes.get(key);
  };
  const current = view.createCurrentEventView({ querySelector: node, querySelectorAll: () => [] });
  const session = { object: { team: 'A' }, draft: '还未提交', basisChanged: true, truncated: true,
    exchanges: [{ question: '旧问题', answer: '旧回答', method_title: '版本理解', revision: 'r1' }] };
  current.renderJudgmentLoading('team'); current.restoreJudgmentSession(session);
  assert.equal(node('#event-judgment-question').value, '还未提交');
  assert.match(node('#event-judgment-messages').innerHTML, /旧问题/);
  assert.match(node('#event-judgment-messages').innerHTML, /版本理解/);
  assert.match(node('#event-judgment-message').textContent, /依据.*更新/);
  assert.match(node('#event-judgment-message').textContent, /最近.*8/);
  current.restoreJudgmentSession(session);
  assert.equal((node('#event-judgment-messages').innerHTML.match(/旧问题/g) || []).length, 1);
});

test('mounted web workspace restores discussion and draft when switching perspectives and returning to a match', async () => {
  const originalDocument = globalThis.document; const originalFetch = globalThis.fetch;
  const nodes = new Map();
  const listeners = new Map();
  const makeNode = () => ({ innerHTML: '', textContent: '', value: '', dataset: {},
    classList: { toggle() {}, remove() {} }, addEventListener() {}, removeEventListener() {},
    querySelector: (selector) => node(selector), querySelectorAll: () => [], closest: () => null });
  const node = (selector) => { if (!nodes.has(selector)) nodes.set(selector, makeNode()); return nodes.get(selector); };
  const root = { ...makeNode(), addEventListener: (name, listener) => listeners.set(name, listener), removeEventListener: (name) => listeners.delete(name) };
  const match = { team_a: 'A', team_b: 'B', date: '2026-10-24', time: '12:00', stage: 'S16' };
  const other = { ...match, team_a: 'C' };
  const calls = [];
  const response = (data) => new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
  globalThis.document = { getElementById: () => root };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.startsWith('/api/current-event/dashboard')) return response({ context: { event: 'S16' }, matches: [] });
    if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [{ match }, { match: other }] });
    if (url.startsWith('/api/tk/search')) return response({ results: [] });
    if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
    if (url === '/api/trading-methods') return response({ methods: ['version', 'team'].map((id) => ({ id, title: id, status: 'ready' })) });
    if (url === '/api/version-understanding/global/current') return response({ data: null });
    if (url.startsWith('/api/current-event/match-desk')) {
      const selected = new URL(url, 'https://local.test').searchParams.get('team_a') === 'A' ? match : other;
      return response({ match: selected });
    }
    if (url === '/api/current-event/collection') return response({ task_id: 'done', state: 'completed', result: { sections: [] } });
    if (url.startsWith('/api/current-event/judgment-context')) {
      const method = new URL(url, 'https://local.test').searchParams.get('method_id');
      return response({ status: 'ok', method: { id: method, title: method === 'version' ? '版本理解' : '队伍画像' }, discussion_available: true, revision: method, contents: [] });
    }
    if (url === '/api/current-event/judgment-discussion') return response({ answer: 'A场已有回答', context_revision: 'version' });
    throw new Error(`Unexpected request ${url}`);
  };
  try {
    const { actions } = await currentEvent.mount(); await actions.refresh(); await actions.selectRecentMatch(0);
    await actions.openJudgment('version'); node('#event-judgment-question').value = 'A场问题'; await actions.askJudgment();
    node('#event-judgment-question').value = 'A场未发草稿';
    listeners.get('input')({ target: { id: 'event-judgment-question', value: 'A场未发草稿' } });
    await actions.openJudgment('team');
    assert.match(node('#event-judgment-messages').innerHTML, /A场已有回答/);
    assert.equal(node('#event-judgment-question').value, 'A场未发草稿');
    await actions.selectRecentMatch(1);
    assert.doesNotMatch(node('#event-judgment-messages').innerHTML, /A场已有回答/);
    await actions.selectRecentMatch(0); await new Promise((resolve) => setTimeout(resolve, 0));
    assert.match(node('#event-judgment-messages').innerHTML, /A场已有回答/);
    assert.equal(node('#event-judgment-question').value, 'A场未发草稿');
    assert.equal(node('#event-judgment-reader').hidden, false);
    actions.closeJudgment(); await actions.openJudgment('version');
    assert.match(node('#event-judgment-messages').innerHTML, /A场已有回答/);
    assert.equal(calls.filter((call) => call.url === '/api/current-event/judgment-discussion').length, 1);
    assert.ok(calls.every((call) => !/trade-plan|match-run\/start/.test(call.url)));
  } finally { currentEvent.unmount(); globalThis.document = originalDocument; globalThis.fetch = originalFetch; }
});
