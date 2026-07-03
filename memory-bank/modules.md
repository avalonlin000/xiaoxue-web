# 小雪工作台 — 模块边界声明

> 改任何模块前先读这里，防止改A炸B。

## 前端工作台（xiaoxue-web/）

| 属性 | 值 |
|------|-----|
| **职责** | 浏览器端电竞数据工作台：选队伍→看三维→搜TK→读画像 |
| **技术栈** | Vite(5173) + FastAPI(8880) + SQLite |
| **数据来源** | 只通过 FastAPI `/api/*` 端点获取数据 |
| **禁止** | 不直接读数据库文件，不调 RAG API，不写飞书文档 |
| **对外接口** | `/api/teams`, `/api/team-3d/{team}`, `/api/tk/search`, `/api/profile-full/{team}` |

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
| **位置** | `~/.hermes/skills/{队伍}-team-profile/SKILL.md` |
| **已覆盖** | AL, BLG, JDG, WE, TES, DK, BRO, KT（8支） |
| **数据来源** | 手工维护（钧钧录入），无自动化数据源 |

---

## 三条硬规矩（每次开发对话开头提醒AI）

1. **一个文件一个职责** — 别把日报生成和数据库导入写在同一个Python文件里
2. **改之前先列出会动哪些文件** — 等我确认再动手
3. **能改配置就不改代码** — 新增数据项用JSON/YAML配置，不写死在代码里
