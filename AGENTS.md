# 小雪工作台项目事实

本文件只保存小雪工作台的项目事实；Codex 通用开发纪律、Hermes 身份和 Skill 总规则由上层继承。

## 真实入口

- 本目录是钧钧实际使用的小雪主工作台，不是实验副本。
- 前端：`index.html`、`src/main.js`；后端：`main.py`；前端使用 Vite/Vanilla JS，后端使用 FastAPI。
- 稳定入口：`http://127.0.0.1:8880/`；开发入口：`http://127.0.0.1:5173/`。
- 数据库：`/home/ubuntu/lol_data/英雄联盟数据库.db`。
- `/home/ubuntu/life-os-frontend-v2/packages/xiaoxue-web/` 不是当前主入口。
- Hermes 产品入口：`scripts/hermes/xiaoxue_product_mcp.py` 是唯一 `xiaoxue-product` MCP Server；Agent 新功能作为其中命名明确的工具接入，不新增平行 Server。

## 项目事实

- `/api/market-notes` 是当前盘口/交易记录主链路；旧 `/api/trades` 仅作兼容。
- 队伍交易备注跟随队伍 TK，使用 `type=trading_note`；队伍不明确时不落库。
- BP 后阵容分析由 `lol-lineup-analysis` 提供判断，前端只整理输入、复制提示和复盘沉淀。
- 固定工作流配置以 `config/workflows.json` 为准；今日内容、队伍别名和市场枚举优先改配置，不回写 `main.py` 常量。
- `market_notes` 复盘先预览，确认后只写回原记录；不自动写 TK、画像或三维。

## 边界与验收

- 缺数据时返回明确空态或“暂不推荐”，不伪造队伍、BP、盘口或赛果。
- 真实业务数据、数据库迁移、生产 cron、外部消息和系统配置必须先得到钧钧确认。
- 按影响范围使用 `npm run build`、`python3 -m py_compile main.py`、相关 GET/API smoke 和真实页面路径；写回能力还要重新读取并检查无效输入不污染数据。
