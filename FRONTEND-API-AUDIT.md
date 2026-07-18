# FRONTEND API AUDIT

## 2026-07-12 · Fixed Workflow API

- `/api/lineup-workflow/prepare`：结构化校验蓝红方、双方五位置、ban/pick、首发、盘口和赛前判断，返回固定八步与 `保留/降权/取消/等待`；不执行自动交易。
- `/api/market-notes/{id}/review-preview`：生成 managed review block，不写库。
- `/api/market-notes/{id}/review`：必须 `confirmed=true`，只写回原 `market_notes.review`，不自动写 TK/画像/三维。
- `config/workflows.json`：今日内容产物、队伍别名、市场枚举、八步法和复盘边界的统一配置正源。

## 2026-07-03 · BP 后问小雪轻量 BP 输入器（历史阶段）

- 入口：`index.html` 的「BP 后问小雪」卡片。
- 新增前端控件：`#analyst-bp-input` 文本框 + 「整理阵容」/「生成分析提示」按钮。
- 前端行为：点击按钮后调用 `generateAnalystPrompt()`，只在浏览器本地把粘贴的 BP/阵容整理成结构化提示文本。
- API 影响（当时）：不新增 API；2026-07-12 已增加结构化契约 API。
- 现有接口保持：原「中年电竞人」/「心语悦无言」按钮仍调用 `/api/analyst/{team}?analyst=...`，未改动调用链。
- 输出提示固定包含：阵容确认、控制量化待算、基本面/TS待带入、线权时间边界待判断、核心链/24场景待定位，以及“复制这段去问小雪”。
