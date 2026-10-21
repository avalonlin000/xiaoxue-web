import assert from 'node:assert/strict';
import test from 'node:test';

import { summarizeModuleHealth } from '../src/app/health-summary.js';


test('a broken daily module is shown without hiding healthy modules', () => {
  const summary = summarizeModuleHealth({
    status: 'degraded',
    modules: {
      daily: { id: 'daily', name: '每日准备', status: 'broken', message: '今日内容缺失' },
      teams: { id: 'teams', name: '队伍资料', status: 'healthy' },
    },
  });

  assert.equal(summary.status, 'degraded');
  assert.equal(summary.text, '1 可用 · 1 待修');
  assert.match(summary.details.join(' '), /每日准备：今日内容缺失/);
});

test('disabled modules are visible but do not degrade a healthy app', () => {
  const summary = summarizeModuleHealth({
    status: 'healthy',
    modules: {
      teams: { id: 'teams', name: '队伍资料', status: 'healthy' },
      analyst: { id: 'analyst', name: '双分析师', status: 'disabled' },
    },
  });

  assert.equal(summary.status, 'healthy');
  assert.equal(summary.text, '1 个模块可用');
  assert.match(summary.details.join(' '), /双分析师：暂未启用/);
});

test('a module waiting for today\'s scheduled data is not counted as broken', () => {
  const summary = summarizeModuleHealth({
    status: 'healthy',
    modules: {
      teams: { id: 'teams', name: '队伍资料', status: 'healthy' },
      daily: { id: 'daily', name: '日报', status: 'pending', message: '今日数据尚未生成：每天 05:30 自动刷新，05:45 前属正常等待' },
    },
  });

  assert.equal(summary.status, 'healthy');
  assert.equal(summary.text, '1 可用 · 1 待生成');
  assert.match(summary.details.join(' '), /日报：今日数据尚未生成/);
});
