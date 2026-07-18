import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/modules/tk-library/api.js', import.meta.url), 'utf8');
const publicSource = readFileSync(new URL('../src/modules/tk-library/public.js', import.meta.url), 'utf8');


test('TK has its own primary workspace with readable time controls', () => {
  assert.match(html, />TK资料库<\/button>/);
  assert.match(html, /id="card-tk-library"/);
  assert.match(html, /今天/);
  assert.match(html, /最近7天/);
  assert.match(html, /最近30天/);
  assert.match(html, /按月份/);
  assert.match(html, /全部/);
});


test('the TK library loads chronological pages and opens a dedicated full reader', () => {
  assert.match(apiSource, /\/tk\/library\?/);
  assert.match(apiSource, /\/tk\/entry\//);
  assert.match(publicSource, /openReader/);
  assert.match(publicSource, /loadMore/);
  assert.match(html, /id="tk-reader-overlay"/);
});
