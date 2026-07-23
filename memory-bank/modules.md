# 小雪工作台 — 模块边界声明

> 改任何模块前先读这里，防止改A炸B。

## 前端工作台（xiaoxue-web/）

| 属性 | 值 |
|------|-----|
| **职责** | 小雪电竞交易助理的长期 LOL 资料本：队伍资料看宏观总览与单队画像/三维/队伍 TK，当前赛事看环境与完整大周期预案，TK资料库看长期知识；盘口记录是隐藏辅助 |
| **技术栈** | Vite(5173) + FastAPI(8880) + SQLite |
| **数据来源** | 只通过 FastAPI `/api/*` 端点获取数据 |
| **禁止** | 不直接读数据库文件，不调 RAG API，不写飞书文档 |
| **对外接口** | `/api/teams`, `/api/team-3d/{team}`, `/api/tk/search`, `/api/profile-full/{team}`, `/api/market-notes`, `/api/lineup-workflow/prepare`, `/api/health` |
| **当前边界** | 一级导航固定为“队伍资料 / 当前赛事 / TK资料库”，默认先看全部队伍；日报、BP/阵容、小雪聊天、预案生成、三层对照和复盘对话不进入工作台；盘口记录仅作隐藏辅助 |

**文件清单：**
```
xiaoxue-web/
├── main.py                 # 极薄启动入口，只创建应用
├── xiaoxue_api/app.py      # 后端组合根：装载模块、挂静态资源、汇总状态
├── xiaoxue_api/core/       # 模块装载、隔离配置、共享数据库连接
├── xiaoxue_api/modules/    # 后端功能模块；每个模块分 presentation/service/repository/public
├── index.html              # 工作台布局
├── src/app/                # 前端启动、模块装载与状态汇总
├── src/modules/            # 每日、赛事、队伍、TK、盘口记录、阵容交接独立目录
├── src/shared/             # 共享 API 与通用模块工具
└── memory-bank/            # 项目记忆库 ← 新对话先读这里
```

## 模块隔离与状态

| 状态 | 含义 |
|------|------|
| `healthy` | 该模块当前可用，可独立进入和验收 |
| `broken` | 该模块当前待修，必须显示原因，但不得阻断其他模块 |
| `disabled` | 非当前主线或旧兼容能力，明确暂停，不计为整站故障 |

- 应用外壳只有自身不可用时才判定整站不可用；非关键模块故障只进入降级状态。
- 各模块配置分别放在自己的目录，某个配置缺失或损坏只影响本模块。
- 后端表现层只处理 HTTP，请求交给业务层；业务层只通过仓储层访问文件、数据库和外部服务。
- 后端跨模块调用只允许导入目标模块的 `public.py`，不得访问对方内部层。
- 前端每个功能分别拥有 `view.js / service.js / api.js / public.js`；主入口只装载、导航和分发命令。
- 前端跨模块协作只通过 `public.js` 或语义事件，不读取其他模块页面节点和内部状态。
- 盘口记录主链只使用独立模块目录和按需建表；旧交易兼容模块仅按需提供历史接口，不做启动写入。
- 前端模块分别装载；一个模块加载或挂载失败后继续装载后续模块。
- 默认验收只读、逐模块继续执行；真实数据写入验收必须显式开启。

## Codex 项目主控与同步协议

| 属性 | 值 |
|------|-----|
| **职责** | 说明小雪 runtime 改动如何进入 Codex 主控、验证、Git 留痕和 sync 闭环 |
| **总协议** | `/home/ubuntu/.hermes/team/CODEX_PROJECT_CONTROL_AND_SYNC_PROTOCOL.md` |
| **默认开发关系** | 钧钧直接给 Codex Goal；Codex 负责方案、实现、验证和交付，不再区分设计期与定版开发期 |
| **小白职责** | 飞书入口、Hermes 运维、bot 恢复和 Codex 不可用时备用接手 |
| **小雪同步矩阵** | PRD/SSD、`xiaoxue-web`、memory-bank、skill、钧钧工作台、sync、GitHub |
| **禁止** | 不把 Codex 永久写成项目主控；不让小雪调度工程主线；不自动交易 |

## 日报管道（daily-report cron）

| 属性 | 值 |
|------|-----|
| **职责** | 每日自动生成LOL电竞日报 → 输出飞书文档 |
| **数据来源** | SQLite数据库（matches/schedules/team_3d_data）+ RAG API（TK语义搜索）+ DailyContext.web_sources.public_opinion（豆包搜索只采舆论） |
| **禁止** | 不改数据库表结构，不改前端代码，不碰前端的 FastAPI |
| **输出** | 飞书云文档（文件夹 FiyGfjl6ml7nIidfvhHc5LIvnod） |
| **材料包** | `collect_daily_context.py` 输出 `daily_context_YYYY-MM-DD.json`；`collect_online_sources.py` 输出 `online_sources_YYYY-MM-DD.json` 并写入 `web_sources.public_opinion` |
| **联网配置** | `/home/ubuntu/lol_data/config/daily_online_sources.json` 只管理舆论查询；BP/盘口/战报不得走豆包额度 |
| **结构契约** | `daily_report_contract.py` 固定 section 顺序、逐场模块、禁入项和来源校验 |
| **脚本** | `daily_pipeline.py` 是唯一生产入口；`postprocess_daily_report.py`/`inject_pre_match_trading_layer.py` 仅为停用兼容文件，不得进入生产 |
| **发布前门禁** | 读取 `data_readiness_manifest_YYYY-MM-DD.json`；仅当天 `mode=full / ok=true` 且 ScoreGG、TS 两阶段成功时放行，check-only/畸形清单一律阻断 |
| **运行态可见性** | `/api/health` 返回 `checks.data_readiness`，可区分 ready、diagnostic_only 与 missing_or_blocked |

## 日报联网资料层（daily-online-sources）

| 属性 | 值 |
|------|-----|
| **职责** | 在日报渲染前采集当天赛前舆论资料 |
| **主链路** | `scripts/collect_online_sources.py` → `scripts/online_sources_YYYY-MM-DD.json` → `DailyContext.web_sources` → `build_daily_report.py` |
| **搜索后端** | `byted-web-search`（豆包搜索），仅用于 `public_opinion` |
| **配置** | `/home/ubuntu/lol_data/config/daily_online_sources.json`，新增/修改查询词优先改配置 |
| **Skill** | `lol-daily-online-sources` 负责舆论材料契约；`lol-community-opinion` 负责社区舆论口径；`byted-web-search` 负责搜索能力 |
| **禁止** | 不让模型在 Markdown 正文里临时联网搜索；不把搜索结果手工 `content.replace()` 进日报；不使用豆包搜索采 BP/盘口/战报 |

## 小雪搜索路由（interactive search routing）

| 属性 | 值 |
|------|-----|
| **职责** | 将小雪的查询意图区分为内部事实、普通外部资料、正式日报舆情和分析判断 |
| **内部事实** | LOL 数据库 / ScoreGG / Wiki / TK-RAG 优先 |
| **普通联网** | `agent-reach`：Exa 搜索、Jina 正文、B站/YouTube/RSS 资料发现 |
| **正式舆情** | `lol-daily-online-sources` + 豆包冻结包，只写 `public_opinion` |
| **判断入口** | BP/阵容/盘口仍走 `lol-lineup-analysis` 和结构化数据，不由搜索器直接给结论 |
| **执行契约** | `/home/ubuntu/.agents/skills/xiaoxue-esports-toolkit/references/search-routing.md` |
| **当前边界** | Agent Reach 仅用于交互式查询和知识发现，不自动接入日报 cron，不修改 DailyContext schema |

## 赛前交易判断日报（pre-match trading report）

| 属性 | 值 |
|------|-----|
| **职责** | 在原 LOL 日报基础上增加交易判断层：今日主方向、入场点、市场分歧、备选方向、不碰项、BP 待确认 |
| **主链路** | `scripts/build_pre_match_trading_report.py` → `赛前交易判断日报_YYYY-MM-DD.md` → `/api/daily-content` 白名单 → 今日内容卡 `trading_report` 入口 |
| **日报关系** | 只作为独立今日内容产物；不得通过 `postprocess_daily_report.py` 或 `inject_pre_match_trading_layer.py` 嵌入 LOL 日报 v2 |
| **数据来源** | 当日 schedules + `/api/fundamentals/msi-match-context` 同源 TS 逻辑 + 队伍 TK 中 `type=trading_note` 的结构化块 |
| **禁止** | 不新增交易 TK 实体，不恢复 `tk_library`，不接旧 `/api/trades` 统计面板，不用 RAG 搜索作为主判断 |
| **降级** | 没有命中有效交易 TK 或基础面不足时写“暂不推荐”，不硬编方向 |

## 交易 TK（归属队伍 TK）

| 属性 | 值 |
|------|-----|
| **职责** | 记录钧钧对某支队伍的盘口/交易观察，例如“HLE 虐菜大人头” |
| **归属** | 仍挂在现有队伍 TK 下；队伍是实体，交易 TK 是优先用途标签 |
| **结构标签** | `team`, `type=trading_note`, `market`, `scenario`, `status=active/inactive`, `source=junjun_manual` |
| **写入入口** | `POST /api/team-trading-notes` / `POST /api/team-trading-notes/from-text` 会先标准化队伍名，失败则拒绝写入 |
| **读取入口** | `GET /api/team-trading-notes/{team}` 只读解析 TK 文件中的结构化块 |
| **日报使用** | 日报按每场对阵双方精确读取 active trading_note，并放在“交易 TK”段落，优先于普通队伍 TK |
| **日常口语** | “小雪记到 HLE：虐菜大人头”会解析为 HLE 的交易 TK；“这个队…”等队伍不明确时不写正式 TK |

## 盘口手写判断工作区（market-notes）

| 属性 | 值 |
|------|-----|
| **职责** | 记录钧钧自己的交易时原始判断：盘口观察、判断链、分歧点、不碰项、备注和后续复盘文本 |
| **主链路** | 前端盘口页 → FastAPI `/api/market-notes` → SQLite `market_notes` |
| **允许** | 新建、读取、删除手写草稿；把草稿沉淀为 TK 手动条目；前端对已加载原始记录做 7 天 / 30 天 / 关键词 / 结果轻量筛选 |
| **复盘接口** | `POST /api/market-notes/{id}/review-preview` 只预览；`PUT /api/market-notes/{id}/review` 必须 `confirmed=true`，且只写回原 market_note |
| **禁止** | 不自动交易，不自动生成方向，不展示命中率/输赢统计，不把草稿当结论推送 |
| **保存字段** | `match_name`, `direction`, `total_lean`, `score_note`, `reason`, `confidence`, `review`, `linked_team`, `created_at`, `updated_at`；结果先写入 `review` 固定行 `结果：未结算/赢/输/走水/放弃`，不改数据库结构 |
| **验证** | 保存一条草稿后刷新仍能读到；列表可显示结果标签并本地筛选最近 7 天 / 30 天 / 结果 / 关键词；`/api/health` 的 `market_notes.ok` 为 true |

## 数据就绪（scoregg + TS cron）

| 属性 | 值 |
|------|-----|
| **职责** | 顺序执行 ScoreGG 刷新 → TS 更新 → 表计数/新鲜度/TS 覆盖校验 → 原子写入 readiness manifest；缺库、坏库、超时也留失败清单 |
| **数据来源** | ScoreGG API |
| **禁止** | 不读RAG，不改前端，不生成飞书文档 |
| **主入口** | `/home/ubuntu/.hermes/scripts/xiaoxue_data_readiness.py` → `/home/ubuntu/lol_data/scripts/data_readiness_pipeline.py` |
| **写入目标** | `/home/ubuntu/lol_data/英雄联盟数据库.db` 与 `scripts/data_readiness_manifest_YYYY-MM-DD.json` |

## B站/公众号知识导入（knowledge-import cron）

| 属性 | 值 |
|------|-----|
| **职责** | 从B站UP主视频+微信公众号文章提取结构化知识入库 |
| **数据来源** | B站API（字幕）+ 微信读书搜一搜 |
| **禁止** | 不改数据库表结构，不碰前端 |
| **写入目标** | Wiki TK 目录 → MemPalace `xiaoxue-tk` 分区（本机 `8770` 增量入口）；旧 RAG `8768` 服务已停用 |
| **固定计划** | `xiaoxue_knowledge_import.py` 先生成 `knowledge_import_manifest_YYYY-MM-DD.json`；模型只处理 `bilibili_candidates`，不得自行扩大范围 |

## TK搜索（MemPalace 入口）

| 属性 | 值 |
|------|-----|
| **职责** | 语义搜索TK知识库，返回相关条目 |
| **数据来源** | MemPalace `xiaoxue-tk` wing（714 份 Wiki TK 条目） |
| **对外接口** | `POST localhost:8770/api/search`；小雪工作台通过 `/api/tk/search` 使用 |
| **禁止** | 不直接读SQLite |
| **依赖** | `xiaoxue-tk-mempalace.service`；旧 `knowledge-rag.service` unit、索引、日志和专属环境已删除，仅留离线代码归档 |

## TK资料库（按时间阅读）

| 属性 | 值 |
|------|-----|
| **职责** | 给钧钧按时间浏览可读 TK 正文，研究队伍、选手、战术与比赛判断 |
| **主接口** | `/api/tk/library`（时间/关键词/队伍筛选与分页）、`/api/tk/entry/{filename}`（完整正文） |
| **前端位置** | 顶部独立“TK资料库”页面 |
| **阅读口径** | 正文与结论优先；明确显示 TK 日期；来源、文件名和导入字段不进入阅读界面 |
| **完整性** | 有实际正文的短条目也保留；只过滤空白或失败导入指针；全文不得截断为 800 字 |
| **排序** | 按 `created` 日期降序，缺日期时用文件更新时间；每次 30 条，可继续加载更早内容 |

## 旧版本字段迁移兼容

| 属性 | 值 |
|------|-----|
| **职责** | 记录旧 `team_3d_data.version_understanding` 字段已完成迁移 |
| **迁移结果** | 30 条有效内容进入对应队伍 TK；1 条测试内容跳过；原字段清空并保留内部兼容 |
| **用户可见** | 不再有队伍版本栏目；全局版本统一叫版本理解 |
| **保留接口** | `/api/version-understanding/{team}` 仅作旧客户端兼容，不接入工作台主路径 |

## 数据库（SQLite）

| 属性 | 值 |
|------|-----|
| **位置** | `/home/ubuntu/lol_data/英雄联盟数据库.db` |
| **核心表** | teams, rosters, schedules, matches, team_3d_data |
| **禁止** | 不在 scripts/ 下创建同名影子文件（会遮蔽真实DB） |
| **访问方式** | 必须通过 `config.DB_PATH` 或 `db_util.get_db()` |

## 队伍画像（SKILL.md）

| 属性 | 值 |
|------|-----|
| **读取顺序** | Wiki 实体画像 → xiaobai/main SKILL.md → 数据库只读兜底画像 |
| **SKILL位置** | `~/.hermes/skills/{队伍}-team-profile/SKILL.md` 或 xiaobai profile skills |
| **基础覆盖** | teams/team_3d_data 当前覆盖 31 支；LPL+LCK 基础数据 24 支 |
| **手工画像** | AL, BLG, JDG, WE, TES, DK, BRO, KT（8支）为旧口径手工覆盖 |
| **兜底边界** | 没有 Wiki/SKILL 时，只拼接 teams、rosters、team_3d_data、msi_ts_seed；不推断队伍风格，不冒充人工画像 |

## 飞书附件发送

| 属性 | 值 |
|------|-----|
| **推荐路径** | Hermes `send_message` 工具正文里使用 `MEDIA:/absolute/path/to/file` |
| **适用** | 私聊发送二维码、截图、图片、文件附件 |
| **禁止** | 不把图片/base64/JSON 当正文发给钧钧；不优先折腾 lark-cli 用户 OAuth scope |
| **参考** | `/home/ubuntu/.hermes/profiles/xiaobai/skills/devops/hermes-team-ops/references/feishu-private-media-send.md` |

---

## 三条硬规矩（每次开发对话开头提醒AI）

1. **一个文件一个职责** — 别把日报生成和数据库导入写在同一个Python文件里
2. **盘口只存手写草稿** — 不自动交易、不自动生成方向、不展示收益率幻觉
3. **画像缺口要标来源** — 数据库兜底画像必须说明来源，不能冒充手工 SKILL
4. **能改配置就不改代码** — 新增数据项用JSON/YAML配置，不写死在代码里
5. **日报只走单流水线** — 不让模型手工改 Markdown，不运行停用后处理链；模块顺序、来源、缺失和禁入项由 `daily_report_contract.py` 校验
6. **舆论资料先采集再写作** — 舆论必须先进入 `online_sources_YYYY-MM-DD.json` / `DailyContext.web_sources.public_opinion`，正文只能引用材料包；BP/盘口/战报另接专用来源
