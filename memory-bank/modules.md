# 小雪工作台 — 模块边界声明

> 改任何模块前先读这里，防止改A炸B。

## 前端工作台（xiaoxue-web/）

| 属性 | 值 |
|------|-----|
| **职责** | 浏览器端电竞数据工作台：选队伍→看三维→搜TK→读画像 |
| **技术栈** | Vite(5173) + FastAPI(8880) + SQLite |
| **数据来源** | 只通过 FastAPI `/api/*` 端点获取数据 |
| **禁止** | 不直接读数据库文件，不调 RAG API，不写飞书文档 |
| **对外接口** | `/api/teams`, `/api/team-3d/{team}`, `/api/tk/search`, `/api/profile-full/{team}`, `/api/market-notes`, `/api/health` |

**文件清单：**
```
xiaoxue-web/
├── main.py          # FastAPI 后端（所有API端点 + 静态文件serve）
├── index.html       # v6 对话驱动布局（Vue3 CDN + 前端逻辑内嵌）
├── src/main.js      # 前端交互逻辑
├── SPEC.md          # 功能规格文档
└── memory-bank/     # 项目记忆库 ← 新对话先读这里
```

## 日报管道（daily-report cron）

| 属性 | 值 |
|------|-----|
| **职责** | 每日自动生成LOL电竞日报 → 输出飞书文档 |
| **数据来源** | SQLite数据库（matches/schedules/team_3d_data）+ RAG API（TK语义搜索）+ web搜索（anysearch） |
| **禁止** | 不改数据库表结构，不改前端代码，不碰前端的 FastAPI |
| **输出** | 飞书云文档（文件夹 FiyGfjl6ml7nIidfvhHc5LIvnod） |
| **脚本** | `build_daily_report.py`（已重构至511行） |

## 盘口手写判断工作区（market-notes）

| 属性 | 值 |
|------|-----|
| **职责** | 记录钧钧自己的盘口观察、判断链、分歧点、破相条件 |
| **主链路** | 前端盘口页 → FastAPI `/api/market-notes` → SQLite `market_notes` |
| **允许** | 新建、读取、删除手写草稿；把草稿沉淀为 TK 手动条目 |
| **禁止** | 不自动交易，不自动生成方向，不展示命中率/输赢统计，不把草稿当结论推送 |
| **验证** | 保存一条草稿后刷新仍能读到；删除后列表消失；`/api/health` 的 `market_notes.ok` 为 true |

## 数据库刷新（scoregg-import cron）

| 属性 | 值 |
|------|-----|
| **职责** | 从ScoreGG拉取最新赛程/比赛数据写入SQLite |
| **数据来源** | ScoreGG API |
| **禁止** | 不读RAG，不改前端，不生成飞书文档 |
| **写入目标** | `db/英雄联盟数据库.db` → schedules / matches 表 |

## B站/公众号知识导入（knowledge-import cron）

| 属性 | 值 |
|------|-----|
| **职责** | 从B站UP主视频+微信公众号文章提取结构化知识入库 |
| **数据来源** | B站API（字幕）+ 微信读书搜一搜 |
| **禁止** | 不改数据库表结构，不碰前端 |
| **写入目标** | knowledge-rag tk/ 目录 → RAG索引（port 8768） |

## TK搜索（RAG API）

| 属性 | 值 |
|------|-----|
| **职责** | 语义搜索TK知识库，返回相关条目 |
| **数据来源** | knowledge-rag 向量索引（ollama qwen3-embedding） |
| **对外接口** | `POST localhost:8768/api/search` |
| **禁止** | 不直接读SQLite |
| **依赖** | knowledge-rag.service + ollama |

## 版本理解聚合视图

| 属性 | 值 |
|------|-----|
| **职责** | 按当前队伍聚合三维版本理解与 TK 版本条目，方便快速阅读 |
| **主接口** | `/api/version-understanding/{team}` |
| **数据来源** | `team_3d_data.version_understanding` + TK 文件搜索结果 |
| **禁止** | 不生成新版本判断，不写 TK，不改三维数据 |
| **前端位置** | 基本面页“版本理解”面板 |

## 数据库（SQLite）

| 属性 | 值 |
|------|-----|
| **位置** | `/home/ubuntu/openclaw/db/英雄联盟数据库.db` |
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
