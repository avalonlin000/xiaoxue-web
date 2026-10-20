import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const root = new URL('../', import.meta.url);
const read = filename => readFileSync(new URL(filename, root), 'utf8');


test('the narrow project-center basket stays in the page and provides a return path', () => {
  const html = read('index.html');
  const view = read('src/modules/project-center/view.js');

  assert.match(html, /@media \(max-width: 720px\)[\s\S]*?\.pc-drawer \{ position:static;[\s\S]*?width:auto;[\s\S]*?height:auto;/);
  assert.doesNotMatch(html, /@media \(max-width: 720px\)[\s\S]*?\.pc-drawer \{ position:fixed;[\s\S]*?height:100dvh;/);
  assert.match(view, /id="pc-change-basket" class="pc-drawer" role="region"/);
  assert.match(view, /← 返回项目中心/);
});


test('closing the project-center basket restores focus to the opener', () => {
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /data-pc-focus-key="header-basket"/);
  assert.match(view, /event\.key === 'Escape' && state\.drawerOpen/);
  assert.match(view, /data-pc-focus-key="\$\{CSS\.escape\(state\.lastFocusKey \|\| 'header-basket'\)\}"/);
});


test('the active project-center tab is revealed on narrow screens and hints that it can scroll', () => {
  const html = read('index.html');
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /revealCurrentTab\(state\)/);
  assert.match(view, /scrollIntoView\(\{ block: 'nearest', inline: 'nearest' \}\)/);
  assert.match(view, /pc-tab-scroll-hint/);
  assert.match(html, /\.pc-tab-scroll-hint/);
});


test('the development book opens one selected chapter from its directory while keeping every chapter available', () => {
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /expandedBookChapters: new Set\(\)/);
  assert.match(view, /if \(action === 'jump-book'\) return openBookChapter\(state, target\.dataset\.bookId\)/);
  assert.match(view, /state\.expandedBookChapters = new Set\(\[chapterId\]\)/);
  assert.match(view, /<details id="pc-book-\$\{escapeAttr\(chapter\.id\)\}"[\s\S]*?class="pc-book-chapter/);
  assert.match(view, /pc-directory-current/);
});

test('the project center exposes the system architecture and object directory views', () => {
  const view = read('src/modules/project-center/view.js');
  const shell = read('src/main.js');

  assert.match(view, /\['architecture', '系统结构图'\]/);
  assert.match(view, /\['objects', '交易对象目录'\]/);
  assert.match(view, /function architectureHtml\(\)/);
  assert.match(view, /function objectsHtml\(catalog\)/);
  assert.match(view, /objectCatalog/);
  assert.match(shell, /architecture\|objects\|modules/);
});

test('objects explain their real scope instead of treating registration as delivery', () => {
  const view = read('src/modules/project-center/view.js');
  const objects = view.slice(view.indexOf('function objectsHtml'), view.indexOf('function quickStartHtml'));
  for (const field of ['current_capability', 'limitations', 'entry', 'next_step']) {
    assert.ok(objects.includes(`item.${field}`));
  }
  assert.doesNotMatch(objects, /暂无登记缺口|对象标识|catalog.required_adapters/);
  assert.match(view, /module.runtime_details/);
});


test('expanded module content is user ordered and does not expose engineering-only fields', () => {
  const view = read('src/modules/project-center/view.js');
  const moduleNode = view.slice(view.indexOf('function moduleNodeHtml'), view.indexOf('function entryActionHtml'));

  assert.doesNotMatch(moduleNode, /解决什么/);
  assert.doesNotMatch(moduleNode, /pc-engineering/);
  assert.doesNotMatch(moduleNode, /engineering_details/);
  assert.match(moduleNode, /当前能做什么/);
  assert.match(moduleNode, /什么时候用/);
  assert.match(moduleNode, /从哪里进入/);
  assert.match(moduleNode, /下一步/);
  assert.match(moduleNode, /关联与使用边界/);
  assert.match(moduleNode, /加入待修改/);
});


test('all copy actions describe copying, and the basket explicitly hands the text to Xiaobai in Feishu', () => {
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /复制发给小白的话/);
  assert.match(view, /data-copy-recipient="小白"/);
  assert.match(view, /回飞书发给\$\{recipient\}就行/);
  assert.match(view, /复制发给小雪的话/);
  assert.match(view, /复制这句话/);
});


test('the ready daily hint gives a usable manual next step instead of an unavailable daily jump', () => {
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /function dailyNextStep\(daily\)/);
  assert.match(view, /今天内容已就绪，可按使用说明选择入口。/);
  assert.match(view, /按使用说明选择入口 →/);
  assert.doesNotMatch(view, /escapeHtml\(daily\.reason \|\| ''\)/);
});


test('every manual shortcut opens the matching scene before taking the reader there', () => {
  const view = read('src/modules/project-center/view.js');

  assert.match(view, /if \(action === 'jump-manual'\) return openManualSection\(state, target\.dataset\.manualId\)/);
  assert.match(view, /function openManualSection\(state, sectionId\)/);
  assert.match(view, /section\.open = true/);
});


test('manual extras render from the same content source and copy straight to Xiaoxue', () => {
  const view = read('src/modules/project-center/view.js');
  const html = read('index.html');

  assert.match(view, /manualExtrasHtml\(manual\.extras\)/);
  assert.match(view, /function manualExtrasHtml\(extras\)/);
  assert.match(view, /class="pc-manual-extras"/);
  assert.match(view, /data-pc-action="copy-chat" data-copy-recipient="小雪"/);
  assert.match(html, /\.pc-manual-extras \{/);
});
