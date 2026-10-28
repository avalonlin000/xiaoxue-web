# 交易人生项目 — 技术导航

这份文件只帮助按任务定位实现，不提供另一套工作流程。项目定位、协作、数据边界和完成标准统一见 [AGENTS.md](../../AGENTS.md)。模块的正式接口与字段映射来自 [module-contract.json](../../config/module-contract.json)，下表是实现索引，不复制完整合同和能力状态。

## 目录方案

采用用户提供的 [项目架构模板](https://github.com/avalonlin000/vibe-coding-cn/blob/main/.github/docs/gongfa/project-architecture-template.md) 中的“全栈 Web 应用（Full-Stack Web）”，按现有 Vite / Vanilla JS + FastAPI / SQLite 轻量适配。`src/` 对应模板的前端区，`xiaoxue_api/` 对应后端区；保持现有包名、启动方式和部署路径，不引入 Next.js、React、Prisma 或新的运行框架。

```text
xiaoxue-web/
├── AGENTS.md          项目约定与定位
├── src/               前端代码（app / modules / shared）
├── xiaoxue_api/       后端代码（core / modules）
├── main.py            后端启动入口
├── index.html         前端页面入口
├── config/            项目与模块合同、可编辑配置
├── requirements/      各 Python 环境依赖
├── scripts/           业务任务、工具适配与检查
├── tests/             后端、前端和产品工具测试
├── deploy/            部署模板
├── docs/
│   ├── architecture/  当前实现导航
│   ├── requirements/  未标记冻结的需求资料
│   └── archive/       冻结设计、历史审计与旧规范快照
├── memory-bank/       进度和变更证据
└── data/              项目本地运行数据
```

`public/`、`static/` 与 `dist/` 是现有静态资源及发布产物；运行环境和缓存留在原位。主业务数据库与 Wiki 在仓库外，由项目依赖配置定位。目录分类不改变历史需求的完成状态，也不搬迁真实业务数据。

## 系统组成

```text
网页 ────────────┐
                 ├─ 项目 API / 能力实现 ─ 数据库、Wiki、TK 检索
Hermes / 飞书 ─ 产品 MCP ┘             └─ 项目任务、资料采集与生成

Codex 等工程工具 ─ 在授权范围内读取、审计或维护同一项目
```

云端部署、服务名、解释器和路径的简表在 [AGENTS.md 的当前入口与正源章节](../../AGENTS.md#当前入口与正源)。该图表示组件关系，不证明所有入口已具有同样的工具、写权限或聊天同步能力。

## 代码入口与消费者

| 要定位的部分 | 后端或正式实现 | 页面、工具或数据关联 |
|---|---|---|
| 应用组装 | `main.py`、`xiaoxue_api/app.py`、`xiaoxue_api/core/` | 路由、模块装载、静态 `dist/assets`、状态汇总 |
| 网页外壳 | `index.html`、`src/main.js`、`src/app/`、`src/shared/` | 导航、模块目录、公共 API 调用 |
| 队伍资料、画像、TS | `xiaoxue_api/modules/team/` | `src/modules/teams/`；`/api/teams`、`/api/profile-full/{team}`、`/api/team-3d/{team}` |
| 当前赛事与单场 | `xiaoxue_api/modules/match/` | `src/modules/current-event/`；`/api/current-event/*`、研究档案及单场工具 |
| TK、交易 TK、版本理解 | `xiaoxue_api/modules/knowledge/` | `src/modules/tk-library/`；`/api/tk/*`、`/api/trading-tk`、版本理解及队伍消费者 |
| 英雄和阵容 | `xiaoxue_api/modules/methods/` | `/api/lineup-workflow/prepare`、专业分析 Skill |
| 日报与维护状态 | `xiaoxue_api/modules/daily_content/` | `/api/daily-content`、项目 health、任务回执 |
| 项目中心与公共写入 | `xiaoxue_api/modules/platform/` | `src/modules/project-center/`；项目中心、业务写入口 |
| 足球及外部事实 | `xiaoxue_api/modules/external/` | `src/modules/football/`；`/api/football/matches`、单场详情及 Gol.gg 工具 |
| 产品 MCP | `scripts/hermes/xiaoxue_product_mcp.py` | Hermes 等已配置客户端调用 API；`config/agents/` 选择业务适配 |
| TK 检索服务 | `scripts/mempalace_tk_api.py` | Wiki 条目、MemPalace 索引、项目 TK API |
| 用户模块与菜单 | `config/project-center-content.json` | `module_tree` / `manual` 同时供项目中心与 `scripts/xiaoxue_menu.py` 使用 |

## 单场实现的定位线索

| 内容 | 位置或对象 |
|---|---|
| 近期窗口、时刻和赛事别名 | `xiaoxue_api/modules/match/event/preparation.py`；同目录 `config.json` 的 `preparation.upcoming_days` |
| 来源身份、引用与共享依据 | `xiaoxue_api/modules/match/event/evidence.py` |
| 预案存储兼容与条目合成 | `xiaoxue_api/modules/match/event/trade_plan.py` |
| 记录词汇、栏目与展示投影 | `xiaoxue_api/modules/match/event/match_records.py` |
| 身份、显式写入、暂停和恢复 | 同模块 `service` / `repository`；`match_runs`、`match_run_facts`、`match_run_entries`、`match_run_revisions` |
| 旧兼容对象 | `match_workspaces`、`match_observations` 等仅提供历史兼容，具体行为查实际路由和仓储 |

## 任务与外部依赖

| 任务或依赖 | 项目入口与下游 |
|---|---|
| 数据就绪与 TS | `scripts/tasks/xiaoxue_data_readiness.py` → `/home/ubuntu/lol_data/scripts/data_readiness_pipeline.py` |
| 日报生成与发布 | `scripts/tasks/xiaoxue_daily_report.py` → `/home/ubuntu/lol_data/scripts/daily_pipeline.py`；结构实现 `daily_report_contract.py` |
| 知识导入 | `scripts/tasks/` 内正式任务；Wiki TK、知识导入 manifest、TK 索引回执 |
| 普通资料搜索 | `scripts/search_web.py`；搜索服务地址来自配置，具体路由见对应搜索 Skill |
| 正式日报舆情 | `opinion-sources` 与日报材料包；`/home/ubuntu/lol_data/config/daily_online_sources.json` |
| Hermes 调度包装 | `/home/ubuntu/.hermes/scripts/` 同名任务，转发到项目实体 |
| 依赖声明 | `config/project-dependencies.json`、`requirements/`、模块 `config.json` |

表格说明入口关系，未验证当前调度是否开启、下次执行是否成功或外部来源是否完整。各任务的实际状态见当前回执和 `memory-bank/progress.md` 对应证据。

## 检查与部署说明的位置

- 依赖和入口只读检查：`.venv/bin/python scripts/health_check.py --json`。
- 迁移合同检查：`scripts/check_hermes_migration_contract.py`，覆盖配置与入口合同。
- 测试：`tests/`；运行环境、隔离构建和写回验证约定见根 `AGENTS.md`。
- 环境重建：`scripts/bootstrap.sh`；TK user systemd 模板：`deploy/xiaoxue-tk-mempalace.service.example`。
- TK 私有环境文件：`~/.config/xiaoxue/mempalace.env`，相关键为 `XIAOXUE_MEMPALACE_SITE_PACKAGES`、`XIAOXUE_MEMPALACE_PALACE`、`XIAOXUE_TK_SOURCE_DIR`、`XIAOXUE_MEMPALACE_WING`；模板参数、具体部署及授权边界分别由示例、当前服务配置和根约定说明。

## 历史与当前任务

当前任务证据在 [progress.md](../../memory-bank/progress.md)，历史决定在 [DECISIONS.md](../archive/DECISIONS.md)。冻结 PRD/SSD 在 [archive/designs](../archive/designs/)，是需求、方案和当时证据；本次收敛前的地图、边界说明、模型交接和 Loop 模板在 [2026-10-29-guidance](../archive/2026-10-29-guidance/)。它们不是额外的现行规范或自动续开的任务。
