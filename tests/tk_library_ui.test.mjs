import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/modules/tk-library/api.js', import.meta.url), 'utf8');
const publicSource = readFileSync(new URL('../src/modules/tk-library/public.js', import.meta.url), 'utf8');
const viewSource = readFileSync(new URL('../src/modules/tk-library/view.js', import.meta.url), 'utf8');


test('TK has a notebook workspace with one primary creation action and readable time controls', () => {
  assert.match(html, />TK资料库<\/button>/);
  assert.match(html, /id="card-tk-library"/);
  assert.match(html, /研究笔记/);
  assert.match(html, />新建资料<\/button>/);
  assert.match(html, /今天/);
  assert.match(html, /最近7天/);
  assert.match(html, /最近30天/);
  assert.match(html, /按月份/);
  assert.match(html, /全部/);
});


test('the TK library opens entries in a local reader with reader management actions', () => {
  assert.match(apiSource, /\/tk\/library\?/);
  assert.match(apiSource, /\/tk\/entry\//);
  assert.match(publicSource, /openReader/);
  assert.match(publicSource, /loadMore/);
  assert.match(publicSource, /getElementById\('tk-library-reader'\)/);
  assert.match(html, /id="tk-library-reader"/);
  assert.match(html, /data-tk-action="edit-reader"/);
  assert.match(html, /data-tk-action="delete-reader"/);
  assert.doesNotMatch(html, /tk-reader-overlay/);
  assert.match(viewSource, /root\.classList\.add\('tk-reader-open'\)/);
  assert.match(viewSource, /data-tk-action="open-reader"/);
});


test('team TK quick view uses the same team-filtered library records and refreshes both views after deletion', () => {
  assert.match(publicSource, /teamOverview/);
  assert.match(publicSource, /loadAllTeamLibraryEntries\(team\)/);
  assert.match(publicSource, /offset: String\(offset\), limit: '100'/);
  assert.match(publicSource, /while \(hasMore\)/);
  assert.match(publicSource, /if \(library\.initialized\) await actions\.load\(true\)/);
  assert.match(publicSource, /删除失败：\$\{error\?\.message/);
});


test('team TK is a compact two-entry quick view with contained expansion and library navigation', () => {
  const quickResultRenderer = viewSource.slice(viewSource.indexOf('renderQuickResults'), viewSource.indexOf('openEditor(draft'));
  assert.match(html, /当前队伍资料速览/);
  assert.match(html, /id="tk-quick-count"/);
  assert.match(html, /data-tk-action="toggle-quick-list"/);
  assert.match(html, /data-tk-action="go-to-library"/);
  assert.doesNotMatch(html, /id="tk-search"/);
  assert.match(viewSource, /const QUICK_VIEW_LIMIT = 2/);
  assert.match(quickResultRenderer, /readableEntries\.slice\(0, QUICK_VIEW_LIMIT\)/);
  assert.match(quickResultRenderer, /!entry\.isShell/);
  assert.match(viewSource, /quickSearchRoot\?\.classList\.add\('is-reading'\)/);
  assert.match(viewSource, /quickSearchRoot\?\.classList\.remove\('is-reading'\)/);
  assert.match(html, /#card-tk\.is-expanded #tk-results \{ max-height:300px;/);
  assert.match(publicSource, /document\.getElementById\('tab-tk'\)\?\.click\(\)/);
  assert.doesNotMatch(quickResultRenderer, /data-tk-action="edit-quick"/);
  assert.doesNotMatch(quickResultRenderer, /data-tk-action="delete-quick"/);
});
