import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const root = new URL('../', import.meta.url);
const activeModules = ['current-event', 'teams', 'tk-library', 'market-notes'];


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

test('market notes behavior is owned by its module instead of the shell', () => {
  const shell = readFileSync(new URL('src/main.js', root), 'utf8');
  const html = readFileSync(new URL('index.html', root), 'utf8');
  for (const legacyName of [
    'function loadTrades', 'function saveTradeRecord', 'function deleteTrade',
    'function tradeToTK', 'window.loadTrades', 'window.saveTradeRecord',
  ]) {
    assert.doesNotMatch(shell, new RegExp(legacyName.replace('.', '\\.')));
  }
  const marketCard = html.match(/<div class="card" id="card-trades">([\s\S]*?)<!-- TK Library/)?.[1] || '';
  assert.doesNotMatch(marketCard, /onclick="(?:loadTrades|saveTradeRecord|deleteTrade|tradeToTK|setTrade)/);
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
