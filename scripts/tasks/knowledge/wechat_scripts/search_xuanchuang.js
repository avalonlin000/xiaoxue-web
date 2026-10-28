#!/usr/bin/env node

/**
 * 轩窗少年免登录批量搜索。
 *
 * 搜索阶段先用多关键词扩大覆盖，只在合并去重后解析一次真实链接，
 * 避免对重复结果反复请求并触发搜狗限流。
 */

const fs = require('fs');
const { resolveRealUrls, searchWechatArticles } = require('./search_wechat');

const QUERIES = [
  'LPL 轩窗少年',
  'LCK 轩窗少年',
  'BLG 轩窗少年',
  'T1 轩窗少年',
  '版本 轩窗少年',
  'WE 轩窗少年',
  'JDG 轩窗少年',
  'TES 轩窗少年',
  'MSI 轩窗少年',
  'AL 轩窗少年',
];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function outputPath(args) {
  const index = args.findIndex(value => value === '-o' || value === '--output');
  return index >= 0 ? args[index + 1] || '' : '';
}

async function main() {
  const articles = [];
  const seen = new Set();
  const queryStats = {};

  for (const query of QUERIES) {
    const found = await searchWechatArticles(query, 10, false);
    const matching = found.filter(item => item.source === '轩窗少年');
    queryStats[query] = matching.length;
    const fresh = [];
    for (const item of matching) {
      const key = `${item.title || ''}\u0000${item.datetime || ''}`;
      if (!item.title || seen.has(key)) continue;
      seen.add(key);
      fresh.push(item);
    }
    // 搜狗跳转票据寿命很短，必须在本次搜索后立刻解析，不能等十组搜索结束。
    const resolved = fresh.length ? await resolveRealUrls(fresh) : [];
    articles.push(...resolved);
    await sleep(350);
  }

  const directCount = articles.filter(item =>
    String(item.url || '').includes('mp.weixin.qq.com')
  ).length;
  const result = {
    source: 'sogou_no_login',
    queries: QUERIES,
    query_stats: queryStats,
    total: articles.length,
    direct_count: directCount,
    articles,
  };
  const serialized = JSON.stringify(result, null, 2);
  const path = outputPath(process.argv.slice(2));
  if (path) fs.writeFileSync(path, serialized, 'utf-8');
  console.log(serialized);
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
