# 小雪工作台项目事实

本文件只保存小雪工作台的项目事实；Codex 通用开发纪律、Hermes 身份和 Skill 总规则由上层继承。

## 真实入口

- 本目录是钧钧实际使用的小雪主工作台，不是实验副本。
- 前端：`index.html`、`src/main.js`；后端：`main.py`；前端使用 Vite/Vanilla JS，后端使用 FastAPI。
- 稳定入口：`http://127.0.0.1:8880/`；开发入口：`http://127.0.0.1:5173/`。
- 数据库：`/home/ubuntu/lol_data/英雄联盟数据库.db`。
- `/home/ubuntu/life-os-frontend-v2/packages/xiaoxue-web/` 不是当前主入口。
- Hermes 产品入口：`scripts/hermes/xiaoxue_product_mcp.py` 是唯一 `xiaoxue-product` MCP Server；Agent 新功能作为其中命名明确的工具接入，不新增平行 Server。

## 沙箱禁令（2026-10-21 钧钧明确要求）

- 本机 Codex 沙箱（bubblewrap / user namespaces）有兼容问题，可能反复卡在授权或执行失败；禁止使用任何带沙箱的执行方式。
- 执行命令一律走普通路径：不加 `sandbox_permissions: require_escalated`，不申请提权，不触发 approval 弹窗。
- 默认配置已固定为 `sandbox_mode = "danger-full-access"` + `approval_policy = "never"`；后续任何客户端、插件或 Skill 不得改回沙箱模式。

## 项目事实

- 盘口/交易记录正源是交易 TK，正式写入使用 `/api/trading-tk`；`/api/market-notes` 是只读投影，旧 `/api/trades` 只读兼容，均不恢复旧表写入。
- 队伍交易备注跟随队伍 TK，使用 `type=trading_note`；队伍不明确时不落库。
- BP 后阵容分析由 `lol-lineup-analysis` 提供判断，前端只整理输入、复制提示和复盘沉淀。
- 固定工作流配置以 `config/workflows.json` 为准；今日内容、队伍别名和市场枚举优先改配置，不回写 `main.py` 常量。
- 交易 TK 的复查经明确确认后用原入口更新原条目；不因普通讨论自动写入、认可或修改画像、三维。
- 当前赛事近期准备窗口由 `xiaoxue_api/modules/current_event/config.json` 的 `preparation.upcoming_days` 声明；源码默认 7 天。生产是否已采用该版本以交付证据为准。
- `dist/` 由正式服务直接提供；未授权发布时，构建使用独立 `--outDir`，不能把默认构建当成无副作用检查。

## 边界与验收

- 缺数据时返回明确空态或“暂不推荐”，不伪造队伍、BP、盘口或赛果。
- 真实业务数据、数据库迁移、生产 cron、外部消息和系统配置必须先得到钧钧确认。
- 按影响范围使用 `npm run build`、`python3 -m py_compile main.py`、相关 GET/API smoke 和真实页面路径；写回能力还要重新读取并检查无效输入不污染数据。
