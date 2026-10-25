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

## 2026-10-25（第三轮）· 工具归并的边界

- **做**：同一对象、参数形状相同的只读工具合并。已完成：Gol.gg 6→1（`xiaoxue_get_gol_facts`）、ScoreGG 3→1（`xiaoxue_get_score`）、判断目录与正文 2→1（`xiaoxue_open_judgment` 空参列目录）、讨论与续读 2→1（`xiaoxue_discuss_judgment` 传 reply_id 读后续页）。工具总数 48 → 37。
- **不做**：把参数异构的写入类工具合并成"万能工具"（如 start/pause/advance/record 合成一两个）。它们参数分别是 section、fact_id、phase、direction 等，合并后签名会膨胀，模型更容易选错参数，反而更差。
- **原则**：合并只在"同一对象、同一参数形态、同一副作用等级"时进行；其余保持单一职责。
- **验证**：MCP 单测 43 通过；后端 425 通过 / 5 项既有失败；合同校验通过。

## 2026-10-25 · 线上只保留一版（补充）

- 本轮再次重建 `dist`（移除沉淀候选残留后），未保留旧别名页面。
