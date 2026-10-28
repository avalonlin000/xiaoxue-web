import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const root = new URL('../', import.meta.url);
const activeModules = ['current-event', 'teams', 'tk-library', 'project-center'];


test('active frontend modules have view service data and public layers', () => {
  for (const moduleName of activeModules) {
    for (const filename of ['view.js', 'service.js', 'api.js', 'public.js']) {
      const url = new URL(`src/modules/${moduleName}/${filename}`, root);
      assert.doesNotThrow(() => readFileSync(url, 'utf8'), `${moduleName}/${filename} is missing`);
    }
  }
});

test('the frontend shell only enters feature modules through public interfaces', () => {
  const source = readFileSync(new URL('src/main.js', root), 'utf8');
  const featureImports = [...source.matchAll(/from ['"]\.\/modules\/([^'"]+)['"]/g)]
    .map((match) => match[1]);
  assert.ok(featureImports.length > 0);
  for (const imported of featureImports) {
    assert.match(imported, /\/public\.js$/);
  }
});

test('cross-module imports target public interfaces only', () => {
  for (const moduleName of activeModules) {
    for (const filename of ['view.js', 'service.js', 'api.js', 'public.js', 'index.js']) {
      const url = new URL(`src/modules/${moduleName}/${filename}`, root);
      let source = '';
      try { source = readFileSync(url, 'utf8'); } catch { continue; }
      const imports = [...source.matchAll(/from ['"]([^'"]+)['"]/g)].map((match) => match[1]);
      for (const imported of imports) {
        if (!imported.includes('/modules/')) continue;
        assert.match(imported, /\/public\.js$/);
      }
    }
  }
});

test('business services do not touch browser presentation globals', () => {
  for (const moduleName of activeModules) {
    const source = readFileSync(new URL(`src/modules/${moduleName}/service.js`, root), 'utf8');
    assert.doesNotMatch(source, /\bdocument\b|\bwindow\b|querySelector|innerHTML/);
  }
});

test('views never call feature data adapters directly', () => {
  for (const moduleName of activeModules) {
    const source = readFileSync(new URL(`src/modules/${moduleName}/view.js`, root), 'utf8');
    assert.doesNotMatch(source, /from ['"].*\/api\.js['"]/);
  }
});

test('market notes surface is retired', () => {
  const html = readFileSync(new URL('index.html', root), 'utf8');
  const shell = readFileSync(new URL('src/main.js', root), 'utf8');
  const event = readFileSync(new URL('src/modules/current-event/view.js', root), 'utf8');
  assert.doesNotMatch(html, /id="card-trades"|open-market-helper|盘口记录/);
  assert.doesNotMatch(shell, /market-notes/);
  assert.doesNotMatch(event, /open-market-helper|记录盘口/);
  assert.match(event, /data-event-action="open-trade-record">记录交易/);
});

test('the shell stays a composition layer without legacy feature handlers', () => {
  const shell = readFileSync(new URL('src/main.js', root), 'utf8');
  const html = readFileSync(new URL('index.html', root), 'utf8');
  assert.ok(shell.split('\n').length <= 230, 'src/main.js is growing back into a feature monolith');
  assert.doesNotMatch(html, /\son(?:click|change|input|keydown)=/);
  for (const legacyName of [
    'function selectTeam', 'function loadFundamentals', 'function render3D',
    'function save3D', 'function loadAnalyst', 'function openTKReader',
  ]) {
    assert.doesNotMatch(shell, new RegExp(legacyName));
  }
});

test('daily and lineup modules are not mounted inside the long-term workbench', () => {
  const catalog = readFileSync(new URL('src/app/module-catalog.js', root), 'utf8');
  const shell = readFileSync(new URL('src/main.js', root), 'utf8');
  assert.doesNotMatch(catalog, /modules\/(?:daily|lineup-handoff)/);
  assert.doesNotMatch(shell, /lineupActions|page === 'today'|showPage\('today'\)/);
});

test('every packaged workbench page has a mount root', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const source = readFileSync(new URL('../src/app/module-catalog.js', import.meta.url), 'utf8');
  for (const id of ['teams', 'current-event', 'football', 'tk-library', 'project-center']) {
    assert.match(source, new RegExp(`id: '${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}'`));
  }
  for (const root of ['content-area', 'card-current-event', 'card-football']) {
    assert.match(html, new RegExp(`id="${root}"`));
  }
});

test('project center stays inside the workbench shell with a stable deep link', () => {
  const html = readFileSync(new URL('index.html', root), 'utf8');
  const shell = readFileSync(new URL('src/main.js', root), 'utf8');
  assert.match(html, /id="tab-project-center"/);
  assert.match(html, /id="project-center"/);
  assert.match(shell, /project-center/);
  assert.match(shell, /book\|architecture\|objects\|modules\|requests\|deliveries\|manual/);
  assert.doesNotMatch(html, /project-center[^\n]*<iframe/i);
});

test('project-level copy describes the assistant without making it the project identity', () => {
  const view = readFileSync(new URL('src/modules/project-center/view.js', root), 'utf8');
  const event = readFileSync(new URL('src/modules/current-event/view.js', root), 'utf8');
  const content = readFileSync(new URL('config/project-center-content.json', root), 'utf8');

  assert.match(view, /项目负责什么/);
  assert.match(view, /当前接入助手共同维护的一条主线/);
  assert.doesNotMatch(view, /小雪负责什么|人和小雪共同维护|看懂小雪项目/);
  assert.doesNotMatch(content, /看懂小雪项目/);
  assert.doesNotMatch(event, /<b>小雪<\/b>|先和小雪聊清|还没和小雪聊到这里/);
  assert.match(event, /data-event-action="copy-match">复制给小雪<\/button>/);
});
