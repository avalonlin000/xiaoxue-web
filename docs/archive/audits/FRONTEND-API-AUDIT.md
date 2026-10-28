> 状态：历史审计，2026-10-28 校正。以下保留 2026-07 当时记录，不是当前接口合同；当前入口以 `AGENTS.md`、`docs/PROJECT-MAP.md`、`config/module-contract.json` 和真实 HTTP 检查为准。

# FRONTEND API AUDIT（历史）

## 2026-07-12 · Fixed Workflow API

- `/api/lineup-workflow/prepare`：结构化校验蓝红方、双方五位置、ban/pick、首发、盘口和赛前判断，返回固定八步与 `保留/降权/取消/等待`；不执行自动交易。
- 历史阶段曾使用 `/api/market-notes/{id}/review-preview` 与 `/api/market-notes/{id}/review`；两者随盘口记录模块于 2026-10-25 退役，当前不可调用。交易记录现统一使用 `/api/trading-tk`。
- `config/workflows.json`：今日内容产物、队伍别名、市场枚举、八步法和复盘边界的统一配置正源。

## 2026-07-03 · BP 后问小雪轻量 BP 输入器（历史阶段）

- 入口：`index.html` 的「BP 后问小雪」卡片。
- 新增前端控件：`#analyst-bp-input` 文本框 + 「整理阵容」/「生成分析提示」按钮。
- 前端行为：点击按钮后调用 `generateAnalystPrompt()`，只在浏览器本地把粘贴的 BP/阵容整理成结构化提示文本。
- API 影响（当时）：不新增 API；2026-07-12 已增加结构化契约 API。
- 现有接口保持：原「中年电竞人」/「心语悦无言」按钮仍调用 `/api/analyst/{team}?analyst=...`，未改动调用链。
- 输出提示固定包含：阵容确认、控制量化待算、基本面/TS待带入、线权时间边界待判断、核心链/24场景待定位，以及“复制这段去问小雪”。
