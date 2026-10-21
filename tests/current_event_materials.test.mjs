import assert from 'node:assert/strict';
import test from 'node:test';

import * as service from '../src/modules/current-event/service.js';
import * as api from '../src/modules/current-event/api.js';
import * as view from '../src/modules/current-event/view.js';
import currentEvent from '../src/modules/current-event/public.js';
import { readFileSync } from 'node:fs';

const match = { team_a: 'A', team_b: 'B', stage: 'Worlds', date: '2026-10-19', time: '17:00', format: 'BO3' };
const result = (text) => ({ revision: text, summary: text, sections: [], limitations: [] });
const packet = (id, state, material = null) => ({ task: { id, state }, result: material });
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('collection integration preserves live trade-plan, Gol and version interfaces without reviving retired workspaces', () => {
  for (const name of ['fetchTradingMethods', 'fetchGlobalVersionUnderstanding', 'fetchGolSeriesEvidence',
    'saveTradePlanManual', 'createTradePlanItem', 'updateTradePlanItem', 'deleteTradePlanItem',
    'restoreTradePlanItem', 'reorderTradePlanItem']) assert.equal(typeof api[name], 'function', name);
  for (const name of ['loadGolSeriesEvidence', 'saveTradePlanManual', 'createTradePlanItem',
    'updateTradePlanItem', 'deleteTradePlanItem', 'restoreTradePlanItem', 'reorderTradePlanItem']) {
    assert.equal(typeof service[name], 'function', name);
  }
  for (const name of ['parseMatchJudgment', 'buildMatchWorkspacePayload', 'saveMatchWorkspace', 'saveMatchChange']) {
    assert.equal(service[name], undefined, name);
  }
  const { root, node } = fakeRoot();
  view.createCurrentEventView(root).renderMatch({ match, trade_plan: { final: { items: [] } } }, match);
  const html = node('#event-match-desk').innerHTML;
  assert.match(html, /赛前交易方案/);
  assert.match(html, /event-gol-game-id/);
  assert.match(html, /data-match-materials/);
  assert.doesNotMatch(html, /event-match-judgment|save-judgment|原有单场记录/);
});

test('project center explains development and delivery, without becoming a daily report reader', () => {
  const source = readFileSync(new URL('../src/modules/project-center/view.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /dailyReportLink|阅读今日日报|daily\.report\.url/);
  assert.match(source, /dailyNextStep\(daily\)/);
  assert.match(source, /项目开发书目录/);
  assert.match(source, /data-view="manual"/);
  assert.match(source, /data-pc-action="jump-module"/);
});

function clock() {
  let sequence = 0;
  const pending = new Map();
  return {
    pending,
    schedule: (callback) => { pending.set(++sequence, callback); return sequence; },
    cancel: (id) => pending.delete(id),
    async tick() { const [id, callback] = pending.entries().next().value; pending.delete(id); await callback(); },
  };
}

test('upcoming list distinguishes eight scheduled fixtures from eight finished reports', () => {
  const { root, node } = fakeRoot();
  view.createCurrentEventView(root).render({ matches: [{ match, ts: { available: false },
    preparation: { state: 'partial', reason: '首发尚未核实' } }],
  preparation: { confirmed_total: 8, prepared: 0, partial: 8, not_started: 0, pending_total: 0 } });
  const html = node('#event-match-list').innerHTML;
  assert.match(html, /近期确认 8 场/);
  assert.match(html, /已整理 0 · 部分整理 8/);
  assert.match(html, /资料：部分整理 · 首发尚未核实/);
  assert.doesNotMatch(html, /task_id|generation|checkpoint/);
});

test('registered squad including substitutes is not presented as the match starting lineup', () => {
  const { root, node } = fakeRoot();
  view.createCurrentEventView(root).renderMatch({ match,
    team_a: { team: 'IG', starters: Array.from({ length: 8 }, (_, i) => ({ name: `Player${i}`, role: 'TOP' })) },
  }, match);
  const html = node('#event-match-desk').innerHTML;
  assert.match(html, /登记名单/);
  assert.match(html, /不代表本场首发/);
  assert.match(html, /Player7/);
  assert.doesNotMatch(html, /<span>首发：/);
});

test('cross-region match cards show the comparison limit instead of a strength gap', () => {
  const { root, node } = fakeRoot();
  view.createCurrentEventView(root).render({ matches: [{ match, ts: { available: true,
    compare: { comparable: false, reason: '跨赛区TS不可直接比较', power_diff: null } } }] });
  const html = node('#event-match-list').innerHTML;
  assert.match(html, /跨赛区TS不可直接比较/);
  assert.doesNotMatch(html, /综合实力差/);
});

test('collection API uses only the existing match identity, not personal judgment', async () => {
  assert.equal(typeof api.prepareMatchMaterials, 'function');
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(packet('one', 'queued')), { headers: { 'content-type': 'application/json' } });
  };
  try {
    await api.prepareMatchMaterials({ ...match, direction: 'private', reasons: 'private', game: 'lol' });
    assert.equal(calls[0].url, '/api/current-event/collection');
    assert.equal(calls[0].options.method, 'POST');
    assert.deepEqual(JSON.parse(calls[0].options.body), {
      game: 'lol', team_a: 'A', team_b: 'B', event: 'Worlds', match_date: '2026-10-19', match_time: '17:00', match_format: 'BO3',
    });
    await api.fetchMatchMaterials('one/unsafe');
    assert.equal(calls[1].url, '/api/current-event/collection/one%2Funsafe');
  } finally { globalThis.fetch = original; }
});

test('cached material is immediate; terminal response stops background polling', async () => {
  assert.equal(typeof service.createMatchMaterialsController, 'function');
  const timer = clock();
  const updates = [];
  const first = deferred();
  const controller = service.createMatchMaterialsController({
    prepare: () => first.promise,
    read: async () => packet('one', 'completed', result('新成果')),
    schedule: timer.schedule, cancel: timer.cancel,
    onUpdate: (value) => updates.push(value),
  });
  const start = controller.start(match, packet('one', 'running', result('原成果')));
  assert.equal(updates[0].result.summary, '原成果');
  first.resolve(packet('one', 'running'));
  await start;
  assert.equal(updates.at(-1).result.summary, '原成果');
  assert.equal(timer.pending.size, 1);
  await timer.tick();
  assert.equal(updates.at(-1).result.summary, '新成果');
  assert.equal(timer.pending.size, 0);
});

test('switching match rejects late responses and leaving cancels scheduled polls', async () => {
  assert.equal(typeof service.createMatchMaterialsController, 'function');
  const timer = clock();
  const old = deferred();
  const updates = [];
  const controller = service.createMatchMaterialsController({
    prepare: (value) => value.team_a === 'A' ? old.promise : Promise.resolve(packet('new', 'running', result('C成果'))),
    read: async () => packet('new', 'completed', result('C完成')),
    schedule: timer.schedule, cancel: timer.cancel,
    onUpdate: (value) => updates.push(value),
  });
  const first = controller.start(match);
  await controller.start({ ...match, team_a: 'C' });
  const count = updates.length;
  old.resolve(packet('old', 'completed', result('错误串场')));
  await first;
  assert.equal(updates.length, count);
  assert.equal(updates.at(-1).result.summary, 'C成果');
  controller.stop();
  assert.equal(timer.pending.size, 0);
});

test('a polling failure retains readable materials and ends with a human explanation', async () => {
  assert.equal(typeof service.createMatchMaterialsController, 'function');
  const timer = clock();
  const updates = [];
  const controller = service.createMatchMaterialsController({
    prepare: async () => packet('one', 'running', result('保留已核实资料')),
    read: async () => { throw new Error('Traceback /home/private/token'); },
    schedule: timer.schedule, cancel: timer.cancel,
    onUpdate: (value) => updates.push(value),
  });
  await controller.start(match);
  await timer.tick();
  assert.equal(updates.at(-1).result.summary, '保留已核实资料');
  assert.match(updates.at(-1).notice, /保留|已有/);
  assert.doesNotMatch(updates.at(-1).notice, /Traceback|home|token/);
  assert.equal(timer.pending.size, 0);
});

test('material renderer safely expands full sections and never links executable URLs', () => {
  assert.equal(typeof view.renderPreparedMaterials, 'function');
  const html = view.renderPreparedMaterials(packet('hidden-task-id', 'partial', {
    summary: '已准备 <img src=x onerror=alert(1)>', updated_at: '2026-10-19 15:00',
    sections: [{ id: 'news', title: '人员消息', items: [
      { text: '第一条 **消息**', source: '官方', url: 'javascript:alert(1)', verification: 'verified' },
      { text: '完整正文'.repeat(100), title: '新闻', source: '官网', url: 'https://example.org/news?a=1&b=2' },
      { text: '测试', source: '/home/private/file', url: 'file:///home/private/file' },
      { text: 'MVK is a [Vietnamese](/leagueoflegends/Category:Vietnam) team.', source: '原文' },
    ] }], limitations: ['本场 BP 尚未公布', 'Traceback /home/private/file'],
  }));
  assert.match(html, /<details/);
  assert.match(html, /完整正文完整正文/);
  assert.match(html, /https:\/\/example.org\/news\?a=1&amp;b=2/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /本场 BP 尚未公布/);
  assert.match(html, /MVK is a Vietnamese team\./);
  assert.doesNotMatch(html, /href="javascript:|file:\/\/|hidden-task-id|Traceback|\/home\/|<img|\*\*消息\*\*/);
});

test('material cards surface applicability and unverified basis in plain language', () => {
  const html = view.renderPreparedMaterials({ result: { sections: [{
    id: 'digest', title: '本场值得知道', selection_status: 'screened', items: [{
      title: '版本倾向', text: '后期团战价值可能上升。',
      source: '已有知识提炼整理（未复核原文）', verification: 'ai_summary',
      applicability: 'unverified_knowledge_extract',
      basis_note: '已有知识提炼，未复核原文；是否适用于当前比赛仍需核实。',
      conditions: '需要结合正式版本与实际 BP 确认。',
    }],
  }] } });
  assert.match(html, /知识提炼，适用性待核实/);
  assert.match(html, /已有知识提炼，未复核原文/);
  assert.match(html, /需要结合正式版本与实际 BP 确认/);
  assert.doesNotMatch(html, /unverified_knowledge_extract/);
});

function fakeRoot() {
  const nodes = new Map();
  const makeNode = () => ({
    innerHTML: '', textContent: '', value: '', dataset: {},
    classList: { toggle() {}, remove() {} }, addEventListener() {}, removeEventListener() {},
    querySelector: (selector) => node(selector), querySelectorAll: () => [], closest: () => null,
  });
  const node = (selector) => { if (!nodes.has(selector)) nodes.set(selector, makeNode()); return nodes.get(selector); };
  return { root: makeNode(), node };
}

test('pending fixtures never become selected match context or block event reading', async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const { root, node } = fakeRoot();
  const calls = [];
  const pending = { pending: true, match: { ...match, team_a: 'TBD', team_b: 'TBD' } };
  let matches = [pending];
  const response = (data) => new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
  globalThis.document = { getElementById: () => root };
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.startsWith('/api/current-event/dashboard')) return response({ context: { event: 'Worlds' }, matches });
    if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [] });
    if (url.startsWith('/api/tk/search')) return response({ results: [] });
    if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
    if (url === '/api/trading-methods') return response({ methods: [{ id: 'version', status: 'ready' }] });
    if (url === '/api/version-understanding/global/current') return response({ data: null });
    if (url.startsWith('/api/current-event/judgment-context')) return response({ status: 'ok', method: { id: 'version' }, contents: [] });
    if (url.startsWith('/api/current-event/match-desk')) return response({ match });
    if (url === '/api/current-event/collection') return response(packet('one', 'completed'));
    throw new Error(url);
  };
  try {
    const { actions } = await currentEvent.mount();
    await actions.refresh();
    await actions.selectMatch(0);
    assert.equal(calls.filter((url) => url.startsWith('/api/current-event/match-desk')).length, 0);
    await actions.openJudgment('version');
    assert.ok(calls.some((url) => url.includes('judgment-context')));
    assert.ok(calls.filter((url) => url.includes('judgment-context')).every((url) => !url.includes('team_a=')));
    matches = [pending, { match }];
    await actions.refresh();
    assert.match(node('#event-match-desk').innerHTML, /A <i>vs<\/i> B/);
    assert.ok(calls.every((url) => !url.includes('team_a=TBD')));
  } finally {
    currentEvent.unmount();
    globalThis.fetch = originalFetch;
    globalThis.document = originalDocument;
  }
});

test('material-only updates leave unsaved trade-plan and discussion input intact', () => {
  const { root, node } = fakeRoot();
  const current = view.createCurrentEventView(root);
  current.renderMatch({ match, trade_plan: { final: { items: [] } } }, match);
  const outer = node('#event-match-desk').innerHTML;
  node('#event-trade-plan-statement').value = '尚未保存的新方案';
  node('#event-trade-content').value = '尚未保存的讨论';
  current.renderMaterials(packet('one', 'completed', result('新增资料')));
  assert.equal(node('#event-match-desk').innerHTML, outer);
  assert.equal(node('#event-trade-plan-statement').value, '尚未保存的新方案');
  assert.equal(node('#event-trade-content').value, '尚未保存的讨论');
  assert.match(node('[data-match-materials]').innerHTML, /新增资料/);
});

test('reselecting the active fixture keeps its editor and does not prepare again, while refresh still reloads', async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const { root, node } = fakeRoot();
  const calls = [];
  let matches = [];
  let pendingDesk = null;
  let failNextDesk = false;
  let deskWrites = 0;
  let deskHtml = '';
  Object.defineProperty(node('#event-match-desk'), 'innerHTML', {
    get: () => deskHtml,
    set(value) { deskHtml = value; deskWrites += 1; },
  });
  const response = (value) => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });
  globalThis.document = { getElementById: () => root };
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.startsWith('/api/current-event/dashboard')) return response({ context: { event: 'Worlds' }, matches });
    if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [] });
    if (url.startsWith('/api/tk/search')) return response({ results: [] });
    if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
    if (url === '/api/trading-methods') return response({ methods: [] });
    if (url === '/api/version-understanding/global/current') return response({ data: null });
    if (url.startsWith('/api/current-event/match-desk')) {
      if (failNextDesk) { failNextDesk = false; throw new Error('temporary read failure'); }
      return pendingDesk ? pendingDesk.promise : response({ match });
    }
    if (url === '/api/current-event/collection') return response(packet('one', 'completed', result('已有资料')));
    throw new Error(url);
  };
  const counts = () => ({ desk: calls.filter((url) => url.startsWith('/api/current-event/match-desk')).length,
    preparation: calls.filter((url) => url === '/api/current-event/collection').length, deskWrites });
  try {
    const { actions } = await currentEvent.mount();
    await actions.refresh();
    matches = [{ match }];
    await actions.refresh();
    const before = counts();
    await actions.selectMatch(0);
    await actions.selectMatch(0);
    assert.deepEqual(counts(), before, 'active editor must not be reconstructed or its materials resubmitted');

    pendingDesk = deferred();
    const refresh = actions.refresh();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const during = counts();
    await actions.selectMatch(0);
    await actions.selectMatch(0);
    assert.deepEqual(counts(), during, 'rapid clicks must not create competing reads');
    pendingDesk.resolve(response({ match }));
    await refresh;
    pendingDesk = null;
    assert.equal(counts().desk, before.desk + 1, 'explicit refresh still reloads');
    assert.equal(counts().preparation, before.preparation + 1);

    failNextDesk = true;
    await actions.refresh();
    const failed = counts();
    await actions.selectMatch(0);
    assert.equal(counts().desk, failed.desk + 1, 'a failed selection remains retryable');
    assert.equal(counts().preparation, failed.preparation + 1);
  } finally {
    currentEvent.unmount();
    globalThis.fetch = originalFetch;
    globalThis.document = originalDocument;
  }
});

test('only screened points are open by default; reasons are visible and full evidence stays expandable', () => {
  const html = view.renderPreparedMaterials({ result: { sections: [
    { id: 'digest', title: '本场值得知道', selection_status: 'screened', items: [
      { text: '已公布换人。', why_relevant: '本场中野搭档改变。', relevance: 'match_update', verification: 'ai_summary', evidence_quote: '原文依据不应铺在默认正文。' },
    ] },
    { id: 'news', title: '赛事相关原文', items: [{ text: '完整原文应按需看。' }] },
  ] } });
  assert.match(html, /<details class="event-context" open><summary>本场值得知道/);
  assert.match(html, /本场中野搭档改变。/);
  assert.match(html, /<details><summary>查看原文依据/);
  assert.doesNotMatch(html, /<details class="event-context" open><summary>赛事相关原文/);
});

test('empty screened result is readable and old untranslated selection is not presented as screened', () => {
  const empty = view.renderPreparedMaterials({ result: { sections: [
    { id: 'digest', title: '本场值得知道', selection_status: 'screened', summary: '未发现值得补充的新信息。', items: [] },
  ] } });
  assert.match(empty, /未发现值得补充的新信息。/);
  const legacy = view.renderPreparedMaterials({ result: { sections: [
    { id: 'digest', title: '中文资料要点', items: [{ text: '旧整理仍可追溯。' }] },
  ] } });
  assert.doesNotMatch(legacy, /<details class="event-context" open>/);
  assert.match(legacy, /历史摘录（未按本场粗筛）/);
});

test('two-line outcomes show concise text and keep structured internals out of evidence', () => {
  const html = view.renderPreparedMaterials({ result: { sections: [
    { id: 'digest', selection_status: 'screened', title: '本场值得知道', items: [{ text: '公开分析认为中野联动重要。', kind: 'author_analysis', verification: 'ai_summary' }] },
    { id: 'analysis', title: '按我的方法看本场', items: [{ text: '自身方法判断：优势需要先确认版本适配。', verification: 'system_inference', conditions: '先确认本场版本', evidence: [
      { text: '已有画像说明中野配合影响前期。' }, { text: '{"mu":28,"input_id":"I1"}' },
      { text: { internal: '不应显示对象' } },
    ] }] },
    { id: 'comparison', title: '两边怎么看', items: [{ text: '公开观点与自身推导在中野节奏上相符。', verification: 'system_inference' }] },
  ] } });
  assert.match(html, /<details class="event-context" open><summary>按我的方法看本场/);
  assert.match(html, /<details class="event-context" open><summary>两边怎么看/);
  assert.match(html, /系统推导 · 未确认采用/);
  assert.match(html, /<details><summary>查看分析依据<\/summary>/);
  assert.match(html, /已有画像说明中野配合影响前期/);
  assert.doesNotMatch(html, /input_id|\bmu\b|\[object Object\]|不应显示对象/);
});

test('personal-analysis reference numbers stay behind evidence without swallowing team or patch names', () => {
  const html = view.renderPreparedMaterials({ result: { sections: [{ id: 'analysis', title: '按我的方法看本场', items: [{
    text: '依据：I1要求先看下路；I3、P2和M7把赢法与版本结合。T1的BO5样本与26.16版本仍需核对。',
    verification: 'system_inference', evidence: [{ text: '已有知识：BO5先核对具体支撑。' }],
  }] }] } });
  assert.doesNotMatch(html, /\b(?:I1|I3|P2|M7)\b/);
  assert.match(html, /要求先看下路/);
  assert.match(html, /把赢法与版本结合/);
  assert.match(html, /T1的BO5样本与26\.16版本/);
});

test('analysis sources show original links and limits while old background stays unverified', () => {
  const html = view.renderPreparedMaterials({ result: { sections: [{ id: 'analysis', title: '当前分析', items: [{
    text: '只作条件推导。', evidence: [
      { text: '原作者依据。', source: '作者甲', url: 'https://example.org/analysis', published_at: '2026-10-20',
        conditions: '仅旧版本样本', counterevidence: '本届尚未验证', evidence_quote: '原文中的具体表述' },
      { text: '旧版本认识。', kind: 'version_background', basis_note: '旧背景，适用性未核实' },
      { text: '公开条目', url: 'javascript:alert(1)', source: '<script>danger</script>' },
    ],
  }] }] } });
  assert.match(html, /href="https:\/\/example\.org\/analysis"/);
  assert.match(html, /2026[年/\-]10[月/\-]20/);
  for (const expected of ['作者甲', '仅旧版本样本', '本届尚未验证', '原文中的具体表述', '旧背景，适用性未核实']) {
    assert.ok(html.includes(expected), expected);
  }
  assert.doesNotMatch(html, /javascript:|<script>|version_background/);
});

test('original recent-match entry prepares materials without opening a trade run, and ignores a late desk', async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const { root, node } = fakeRoot();
  const old = deferred();
  const calls = [];
  const other = { ...match, team_a: 'C', team_b: 'D' };
  const response = (data) => new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
  globalThis.document = { getElementById: () => root };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.startsWith('/api/current-event/dashboard')) return response({ context: { event: 'Worlds' }, matches: [] });
    if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [{ match }, { match: other }] });
    if (url.startsWith('/api/tk/search')) return response({ results: [] });
    if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
    if (url === '/api/trading-methods') return response({ methods: [] });
    if (url === '/api/version-understanding/global/current') return response({ data: null });
    if (url.startsWith('/api/current-event/match-desk')) {
      if (new URL(url, 'https://local.test').searchParams.get('team_a') === 'A') return old.promise;
      return response({ match: other });
    }
    if (url === '/api/current-event/collection') return response(packet('new', 'completed', result('C资料')));
    throw new Error(`Unexpected request ${url}`);
  };
  try {
    const { actions } = await currentEvent.mount();
    await actions.refresh();
    const first = actions.selectRecentMatch(0);
    await actions.selectRecentMatch(1);
    old.resolve(response({ match }));
    assert.equal(await first, null);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.match(node('#event-match-desk').innerHTML, /C <i>vs<\/i> D/);
    assert.match(node('[data-match-materials]').innerHTML, /C资料/);
    assert.equal(calls.filter((call) => call.url === '/api/current-event/collection').length, 1);
    assert.ok(calls.every((call) => !call.url.includes('/match-run/start')));
  } finally {
    currentEvent.unmount();
    globalThis.fetch = originalFetch;
    globalThis.document = originalDocument;
  }
});

test('AI summaries retain their interpretation label and safely expandable original evidence', () => {
  const html = view.renderPreparedMaterials(packet('one', 'completed', {
    summary: '中文整理', sections: [{ id: 'digest', title: '中文资料要点', items: [{
      text: '归纳后的中文', source: '公开原文', url: 'https://example.org/a', verification: 'ai_summary',
      evidence_quote: 'Original evidence <script>alert(1)</script>',
    }] }], limitations: [],
  }));
  assert.match(html, /AI整理 · 请结合原文/);
  assert.match(html, /<details[^>]*><summary>查看原文依据<\/summary>/);
  assert.match(html, /Original evidence &lt;script&gt;/);
  assert.doesNotMatch(html, /<script>|已核实/);
});

test('withdrawn automatic preparation keeps the last readable result and explains the pause', () => {
  const html = view.renderPreparedMaterials({ task: { state: 'paused', message: '赛程已调整，保留原资料。' },
    result: { summary: '此前已取得的材料', sections: [] } });
  assert.match(html, /自动准备已暂停/);
  assert.match(html, /赛程已调整，保留原资料/);
  assert.match(html, /此前已取得的材料/);
  assert.doesNotMatch(html, /正在准备|正在核对最新变化/);
});

test('sealed pre-match replay hides post-match material even when passed directly to the view', () => {
  const { root, node } = fakeRoot();
  const current = view.createCurrentEventView(root);
  const desk = {
    match, match_run: { exists: true, id: 1, mode: 'virtual_pre', result_unlocked: false, guide: {} },
    prepared_materials: packet('old', 'completed', result('赛后比分不能泄露')),
  };
  current.renderMatch(desk, match);
  assert.doesNotMatch(node('#event-match-desk').innerHTML, /赛后比分不能泄露/);
  assert.match(node('#event-match-desk').innerHTML, /赛前回放不采用赛后收集资料/);
  current.renderMatch({ ...desk, match_run: { ...desk.match_run, result_unlocked: true } }, match);
  assert.match(node('#event-match-desk').innerHTML, /赛后比分不能泄露/);
});

test('switching run modes suppresses replay collection and invalidates a late live result', async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const { root, node } = fakeRoot();
  const oldCollection = deferred();
  let mode = 'virtual_pre';
  let prepares = 0;
  const run = () => ({ exists: true, id: 1, match, mode, result_unlocked: false, guide: {} });
  const response = (data) => new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
  globalThis.document = { getElementById: () => root };
  globalThis.fetch = async (url) => {
    if (url.startsWith('/api/current-event/dashboard')) return response({ context: {}, matches: [] });
    if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [{ match }] });
    if (url.startsWith('/api/tk/search')) return response({ results: [] });
    if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
    if (url === '/api/trading-methods') return response({ methods: [] });
    if (url === '/api/version-understanding/global/current') return response({ data: null });
    if (url.startsWith('/api/current-event/match-desk')) return response({ match, match_run: run(), prepared_materials: packet('old', 'completed', result('赛后泄露资料')) });
    if (url === '/api/current-event/match-run/focus') return response(run());
    if (url === '/api/current-event/collection') {
      prepares += 1;
      return prepares === 1 ? oldCollection.promise : response(packet('new', 'completed', result('新live资料')));
    }
    throw new Error(url);
  };
  try {
    const { actions } = await currentEvent.mount();
    await actions.refresh();
    const desk = await actions.selectRecentMatch(0);
    assert.equal(prepares, 0);
    assert.equal(desk.prepared_materials, null);
    assert.match(node('#event-match-desk').innerHTML, /赛前回放不采用赛后收集资料/);
    assert.match(node('#event-prepared-content').innerHTML, /赛前回放不采用当前赛事资料/);
    mode = 'live';
    await actions.focusRun();
    assert.equal(prepares, 1);
    assert.doesNotMatch(node('#event-prepared-content').innerHTML, /赛前回放不采用当前赛事资料/);
    mode = 'virtual_pre';
    await actions.focusRun();
    const before = node('[data-match-materials]').innerHTML;
    oldCollection.resolve(response(packet('late', 'completed', result('晚到赛后资料'))));
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(node('[data-match-materials]').innerHTML, before);
    assert.equal(desk.prepared_materials, null);
    mode = 'live';
    await actions.focusRun();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(prepares, 2);
    assert.match(node('[data-match-materials]').innerHTML, /新live资料/);
  } finally {
    currentEvent.unmount(); globalThis.fetch = originalFetch; globalThis.document = originalDocument;
  }
});

test('every delayed live action ignores success and error after the selected match changes', async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const originalCSS = globalThis.CSS;
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  globalThis.CSS = { escape: (text) => text };
  const mutations = [
    ['startRun', []], ['pauseRun', []], ['focusRun', []], ['saveTradeEntry', []],
    ['loadGolEvidence', []], ['saveTradePlanItem', []], ['deleteTradePlanItem', ['old']],
    ['restoreTradePlanItem', ['old']], ['reorderTradePlanItem', ['old', 'up']],
    ['copyMatch', []],
  ];
  try {
    for (const [action, args] of mutations) {
      for (const reject of [false, true]) {
        const { root, node } = fakeRoot();
        const delayed = deferred();
        const other = { ...match, team_a: 'C', team_b: 'D' };
        const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
        globalThis.document = { getElementById: () => root };
        Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: {
          writeText: async () => {
            const response = await delayed.promise;
            if (!response.ok) throw new Error('旧比赛复制失败');
          },
        } } });
        globalThis.fetch = async (url) => {
          if (url.startsWith('/api/current-event/dashboard')) return response({ context: {}, matches: [] });
          if (url.startsWith('/api/current-event/match-runs')) return response({ matches: [{ match }, { match: other }] });
          if (url.startsWith('/api/tk/search')) return response({ results: [] });
          if (url.startsWith('/api/current-event/scope-materials')) return response({ result: null });
          if (url === '/api/trading-methods') return response({ methods: [] });
          if (url === '/api/version-understanding/global/current') return response({ data: null });
          if (url.startsWith('/api/current-event/match-desk')) return response({
            match: new URL(url, 'https://fixture.test').searchParams.get('team_a') === 'A' ? match : other,
            match_run: { exists: true, id: 11, guide: {} },
          });
          if (url === '/api/current-event/collection') return response(packet('done', 'completed'));
          return delayed.promise;
        };
        const { actions } = await currentEvent.mount();
        await actions.refresh();
        await actions.selectRecentMatch(0);
        node('#event-gol-game-id').value = '123';
        node('#event-trade-plan-direction').value = '做多';
        node('#event-trade-content').value = 'A场记录';
        const pending = actions[action](...args);
        await actions.selectRecentMatch(1);
        const before = node('#event-match-desk').innerHTML;
        const recentBefore = node('#event-recent-runs').innerHTML;
        const messageBefore = node('#event-match-message').textContent;
        delayed.resolve(reject ? response({ detail: 'A场失败不得显示' }, 500) : response({
          id: 12, exists: true, match, guide: {}, activity_status: 'active',
          facts: [{ label: 'A独有', value: 'A事实不能出现在C', status: 'active' }],
          final: { items: [] }, auto: { items: [] }, manual: { items: [] },
        }));
        assert.equal(await pending, null, `${action} ${reject ? 'error' : 'success'}`);
        assert.equal(node('#event-match-desk').innerHTML, before, action);
        assert.equal(node('#event-recent-runs').innerHTML, recentBefore, action);
        assert.equal(node('#event-match-message').textContent, messageBefore, action);
        currentEvent.unmount();
      }
    }
  } finally {
    currentEvent.unmount();
    globalThis.fetch = originalFetch;
    globalThis.document = originalDocument;
    globalThis.CSS = originalCSS;
    if (originalNavigator) Object.defineProperty(globalThis, 'navigator', originalNavigator);
    else delete globalThis.navigator;
  }
});
