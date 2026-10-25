# 决策记录（ADR）

> 每做一次结构性决定，在这里记一段：为什么、什么时候、影响什么。
> 2026-10-25 起，这是三份正源之一（另两份：PROJECT-MAP 事实、progress 进度）。

## 2026-10-25 · 后端实现模块 20 → 7

- **决定**：按数据所有权归并，不按用户能力域硬拆。
- **做法**：team（team_data+profiles+fundamentals）、match（current_event+lol_scope+research_subjects）、knowledge（tk_knowledge+version_understanding）、methods（lineup+champion_static）、platform（platform+business_mutations+project_center）、external（gol_gg+football）；daily_content 保留。
- **删除**：analyst、weread_bridge、legacy_trades、market_notes；空目录 business_updates/pre_match/pro_stats。
- **边界**：用户能力域仍是合同里的 8 个；接口路径不变；数据表不动。
- **验证**：`/api/health` 7 模块 healthy；后端 425 通过 / 5 项改动前既有失败；前端 99 通过；合同校验通过。

## 2026-10-25 · 退役两个概念

- **沉淀候选**：页面、标签、路由、MCP 工具、能力树节点全部移除；候选状态只作为 TK 数据留存。
- **盘口记录**：页面、顶栏入口、模块、MCP 工具移除；内容归交易 TK，`/api/market-notes` 一并退役。
- **验证**：两个接口 404；全站源码 0 命中（除历史归档）。

## 2026-10-25 · 线上只保留一版

- 构建产物重新生成并对齐 `dist`；上一版备份在 `/home/ubuntu/dist-backup-20261025-150810.tar.gz`。
