# Codex · 小雪工作台开发规则

## 身份和边界

- Codex 是本仓库默认开发主力，钧钧直接给 Codex Goal。
- 小雪是电竞交易辅助业务身份，不是工程主控；小白只做备用接手和 Hermes 运维。
- 总主控协议：`/home/ubuntu/.hermes/team/CODEX_PROJECT_CONTROL_AND_SYNC_PROTOCOL.md`。
- 小雪业务总纲：`/home/ubuntu/life-os-frontend-v2/docs/products/xiaoxue-esports-life/PRD/04-trading-methodology-and-taxonomy.md`。
- 小雪只提供证据、分歧、风险和复盘校准，不自动交易。

## 当前真实工程

- 本目录是钧钧实际使用的小雪主工作台。
- 前端：`index.html` + `src/main.js`，Vite/Vanilla JS。
- 后端：`main.py`，FastAPI。
- 数据库：`/home/ubuntu/lol_data/英雄联盟数据库.db`。
- 稳定入口：`http://127.0.0.1:8880/`；开发入口：`http://127.0.0.1:5173/`。
- `/home/ubuntu/life-os-frontend-v2/packages/xiaoxue-web/` 不是当前主入口。

## 编码行为

- 开始实现前先写清成功标准和关键假设。技术事实能从代码、数据或运行态查清就自己查；只有会改变产品结果的歧义才让钧钧选择，不能默默猜。
- 简单方案优先：只实现 Goal 明确需要的能力，不增加没要求的抽象、配置、扩展点或“以后可能有用”的功能；能用简单方案解决就不用复杂架构。
- 精准修改：每一行改动都必须能追溯到当前 Goal。不顺手重构、格式化或清理相邻代码；只移除本次修改自己造成的无用 import、变量、函数或文件，原有问题只报告不擅自删除。
- 修改前先建立基准：修 bug 先复现，性能优化先记录当前数据，重构前后运行同一套验证。没有改前证据，不能声称问题已修复或效果已提升。

## 修改规则

- 开始前运行 `git status --short --branch`，保留现有不明改动。
- 前端通过相对 `/api/...` 调用后端，不让浏览器直接读取 SQLite。
- 缺数据时返回明确空态或“暂不推荐”，不伪造队伍、BP、盘口或比赛事实。
- `/api/market-notes` 是当前盘口/交易记录主链路；旧 `/api/trades` 只保留兼容，不重新升为主流程。
- 队伍交易备注跟随队伍 TK，`type=trading_note`；队伍不明确时不落库。
- BP 后阵容分析以 `lol-lineup-analysis` 八步法为判断引擎，前端只负责信息整理、复制提示和复盘沉淀。
- 固定工作流配置以 `config/workflows.json` 为正源；今日内容、队伍别名、市场枚举优先改配置，不回写 `main.py` 常量。
- `/api/lineup-workflow/prepare` 只校验八步法输入和允许的升降权状态，不在 API 内硬编码比赛结论。
- market_notes 复盘先预览，`confirmed=true` 后只写回原记录；不得自动写 TK、画像或三维。
- 真实业务数据写入、数据库迁移、生产 cron、外部消息和系统配置必须先让钧钧确认。

## 最小验证

按本次影响范围至少执行：

```bash
npm run build
python3 -m py_compile main.py
curl http://127.0.0.1:8880/
curl http://127.0.0.1:8880/api/teams
curl http://127.0.0.1:5173/
```

- `8880` 对 HEAD 可能返回 405；必须使用普通 GET 或浏览器验证。
- 修改写回能力时必须验证：写入成功、重新读取成功、无效输入不污染数据。
- 完成汇报用人话说明：改了什么、现在怎么用、实际检查了什么、剩余风险。
