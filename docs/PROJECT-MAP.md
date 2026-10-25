# 小雪项目地图（AI 开发导航·改前必读第一份）

> 整体重构入口：[PRD](小雪整体重构-PRD.md) 与 [SSD](小雪整体重构-SSD.md)。本次约定快速收尾已上线，最终证据和限制见SSD第12节；批次及有限恢复合同仍见第3A节。8场均有可读要点，但均为部分整理；自然飞书入站、未来连续产出和研究质量不冒称通过。本地图不重复任务台账，也不因旧阶段状态续开已收尾工程。

> 这份文件的作用：**让任何 AI（小白、Codex、小雪）在改这个小雪项目前，只读一份就能看到全貌——项目分几块、每块在哪、正源是谁、改某功能牵连哪几处、哪些文档是权威哪些别信。**
>
> 它**不是**把所有实现塞进来，它是一根"导航指针"：看完它你该知道去哪看细节。细节在各自模块和对应的权威文档里。
>
> ⚠️ **改动前强制协议**：改任何代码/Skill/配置之前，先读本文件 + `AGENTS.md`，确认你要改的那一块的正源和影响面，再动手。不要只 grep 到一段就开始改。

---

## 一、项目是什么（一句话）

小雪 = 钧钧的 LOL 电竞交易助理工作台。前端（Vite + Vanilla JS）+ 后端（FastAPI）+ SQLite 数据库，配套一套 Hermes Skill 和自动化工件（日报、知识导入、数据刷新）。

## 二、同一项目全貌，两个视图（分工）

本项目的"全貌"只有一份，但用两个视图呈现，分别服务两个读者，**目的都是让修改更顺畅**：

| 视图 | 给谁看 | 在哪 | 回答什么 |
|---|---|---|---|
| **用户视图（给你/钧钧）** | 钧钧（非开发） | 前端「项目中心」`config/project-center-content.json` 的 `module_tree` | 这个项目能做什么、从哪里看、哪里值得改；按用户能懂的语言组织（资料与长期理解 / 当前赛事与单场准备 / 方法与判断 / …） |
| **开发视图（给 AI）** | 小白 / Codex / 小雪 | 本文件 `PROJECT-MAP.md` | 代码在哪、正源是谁、改某功能牵连哪几处；按技术实现组织 |

**两者必须对齐**：用户视图的每个"用户模块"（如 `methods-and-judgment`）都映射到开发视图的技术正源。改东西时两边对应着看——钧钧在项目中心说"版本理解这边要不要改"，AI 在 PROJECT-MAP 找到对应的 `version_understanding` 模块和 `shared_version_analysis` 表。**哪个视图都不单独成立，合起来才是完整全貌。**

**「小雪在飞书里会什么」的菜单也在这份内容里**：唯一正源是 `config/project-center-content.json` 的 `manual`（`sections` 场景 + `extras` 常用说法），模块清单的正源是同文件的 `module_tree`。小雪根 Skill 的「引导与菜单」和 `docs/小雪项目总使用说明.md` 都不抄功能清单/模块表，运行时由 `scripts/xiaoxue_menu.py` 读取（`--scenario <id>` 单场景、`--modules` 模块一览、`--module <id>` 单模块口径），项目中心「使用说明书」页尾也渲染同一份 `extras`。所以改内容 = 工作台页面、小雪菜单和模型使用说明同时改，不需要手工同步；`tests/test_project_center_menu_source.py` 守住这条契约。新增能力或说法时改内容文件即可，不要再往 Skill 或文档里加清单。

## 三、后端模块 → 正源 → 前端消费（改动影响面）

> 这是"改某功能会碰哪几处"的地图。每行的**用户模块**对应项目中心给人看的那棵树，**技术模块/正源**是 AI 改的地方。对应着看。

| 用户模块（项目中心） | 技术模块（后端+前端） | 主要正源/接口 | 改动牵涉 |
|---|---|---|---|
| teams-ts-profile（队伍资料） | `team_data`, `profiles`, `fundamentals`, `tk_knowledge` + `src/modules/teams` | `/api/teams`, `/api/profile-full/{team}`, `/api/team-3d/{team}`, `/api/tk/*` | 队伍画像+三维+TK |
| current-event-prep（当前赛事） | `current_event` + `src/modules/current-event` | `/api/current-event/*`（dashboard/match-desk/match-run*；`match-workspace` 仅兼容读） | 单场 `match_runs` 比赛容器 |
| tk-library-and-search（TK资料库） | `tk_knowledge` + `src/modules/tk-library` | `/api/tk/search`, `/api/tk/library` | TK 检索（MemPalace） |
| project-center-and-feedback（项目中心） | `project_center` + `src/modules/project-center` | `/api/project-center/*` | 开发模块树+待修改/交付；版本理解仅显示状态 |
| stage-review-candidates（阶段整理） | `current_event`, `tk_knowledge` + `src/modules/stage-review` | `/api/stage-review/*` | 长期候选 |
| market-and-live-records（盘口记录） | `tk_knowledge` 为写入正源；`market_notes` + `src/modules/market-notes` 保留兼容 | `/api/trading-tk`；`/api/market-notes` 仅只读投影 | 盘口/交易 TK；不恢复退役写接口 |
| pure-ten-lineup（阵容分析） | `lineup` + `src/modules/lineup-handoff` | `/api/lineup-workflow/prepare` | BP 阵容 |
| **version-understanding（版本理解）** | `version_understanding`（后端）+ current-event（前端展示） | `/api/version-understanding/global/current` | 数据库 `shared_version_analysis` |

> 注意「版本理解」是最近重点：唯一正源 = 数据库 `shared_version_analysis` 表。正文在**当前赛事页**展示，并作为单场判断的共用依据；项目中心只保留开发状态。在开发视图里由 `version_understanding` 模块 + `read_version_context.py` 阵容分析脚本消费。三方（当前赛事前端/后端模块/阵容脚本）对齐着改。

## 四、文档权威等级（AI 该信谁、别信谁）

| 文档 | 读者 | 权威程度 | 说明 |
|---|---|---|---|
| `docs/小雪整体重构-PRD.md` | 钧钧/产品方向 | **本次整体重构专项 PRD** | 本轮讨论收束，继承总体产品，不另建系统 |
| `docs/小雪整体重构-SSD.md` | 执行者 | **本次整体重构专项 SSD** | 第3A节规定关注窗口逐场补齐、有限恢复、批次结果和验收；单场与页面历史证据见第10节 |
| `docs/足球滚大球赛前筛选-PRD.md` | 钧钧/产品方向 | **足球专项 PRD** | 小雪内半破/75分钟后观察、开赛保留与一句话交易TK；不是已上线清单 |
| `docs/足球滚大球赛前筛选-SSD.md` | 执行者 | **足球专项 SSD** | 规则映射、来源、资料版本、原TK接点与验收；足球对象仍为planned |
| `docs/交易信息系统-总体设计.md` | 钧钧/产品方向 | **唯一 PRD 正源** | 统一骨架、内容归位、角色边界、对象扩展和产品完成标准 |
| `docs/LOL信息与自动化整合-PRD.md` | 钧钧/产品方向 | **本立项 PRD（范围展开）** | LOL 线的信息收拢与自动化跟随赛程；骨架以总体设计为准，不另立平行产品 |
| `docs/当前赛事信息收集能力重构-PRD.md` | 钧钧/小白 | **当前赛前整合 PRD（2026-10-20，已确认）** | 标题《小雪赛前内容整合与自动准备》；内容补齐、实质合并、可见判断入口与赛前可读，纯阵容/BP不在本次范围；未按本版验收 |
| `docs/当前赛事信息收集能力重构-SSD.md` | 小白/执行者 | **当前赛前整合实施规范（2026-10-20）** | 第1—8节规定责任、原接点合并、判断入口及预算；8.1记录本次授权后的代码与真实隔离验证，未完成S16全覆盖/生产激活；第9—10节仅历史证据 |
| `docs/交易信息系统-工程实现.md` | 小白/执行者 | **唯一 SSD 正源** | 系统分层、正源、迁移映射、缺口登记、施工和验证 |
| `docs/LOL信息与自动化整合-工程实现.md` | 小白/执行者 | **本立项 SSD** | LOL 线的范围派生、事实收拢、排程器与出口；增量登记，不复制全项目 SSD |
| `config/module-contract.json` | 所有 | **模块合同唯一事实** | 模块 ID/正源/入口/映射 |
| `config/project-contract.json` | 所有 | 项目合同 | 能力与兼容命名 |
| `memory-bank/modules.md` | 改模块前 | 模块边界（活） | 防改A炸B |
| `memory-bank/progress.md` | 汇报/接续 | 进度（活） | 上次做到哪 |
| `/home/ubuntu/life-os-frontend-v2/docs/products/xiaoxue-esports-life/CURRENT-CAPABILITY-MAP.md` | 所有 | 当前能力底图 | 记录真实入口、读写正源、可用状态 |
| `docs/小雪项目总使用说明.md` | 小雪 | 产品语言 | 给小雪按需读；模块清单指向正源，不另列模块表 |
| ⚠️ `docs/archive/`（含 `SPEC.md`、`docs/archive/小雪1.0版本.md`、`docs/archive/小雪2.0模块化版本.md`、`docs/archive/README.md`、`docs/archive/交易方法重组执行.md`） | — | **历史归档，勿当当前事实** | 已过期/快照，已从默认阅读面移出，AI 别再被带偏 |

> 规则：新代码、新正源、新接口以 `module-contract.json` 和真实运行结果为准；历史版本文档只当背景，不得作为当前修改依据。

## 五、当前事实快照（2026-10-07）

本轮按真实代码和运行入口核对后的基线，供后续改动判断“缺能力”还是“只是展示需要调整”：

- `config/project-center-content.json` 当前有 8 个一级用户模块、37 个树节点；8 个 `ability_ids` 全部有合同定义，树上没有无效能力引用。
- **2026-10-25 模块归并后：后端实现模块 7 个** —— `team`（队伍事实/画像/TS）、`match`（比赛：赛前工作区/范围覆盖/研究档案）、`knowledge`（TK 与版本理解）、`methods`（阵容与英雄资料）、`daily_content`（日报）、`platform`（外壳/统一写入口/项目中心）、`external`（Gol.gg 与足球）。
- `src/app/module-catalog.js` 当前 6 个活动前端 loader：队伍资料、当前赛事、沉淀候选、足球、TK 资料库、项目中心；`market-notes` 已下线。
- `src/main.js` 主页面为 `teams`、`event`、`stage`、`football`、`tk`、`project`；隐藏页 `market` 已移除。
- 已删除：`analyst`、`weread_bridge`、`legacy_trades`、`market_notes`；空目录 `business_updates`、`pre_match`、`pro_stats` 已清理。用户能力域仍是合同里的 8 个，只是实现模块由 20 收敛为 7。
- 稳定入口 `/api/project-center/overview` 与 `/api/project-center/modules` 当前可读，项目中心内容版本已更新为 `2026-10-12.1`（2026-10-12 增量核对：无节点漂移，仅版本标记随核对写回）；本快照不代表后续内容版本必须变更，只有实际写回内容时才升级版本。

因此，后续“更新项目地图/项目中心”默认先做程序化对照；无真实漂移时不新增节点，若用户体验有问题则优先调整用户视图的信息层级和入口表达。

## 六、改前的通用流程（防只见局部）

- 当前事实快照（2026-10-07）：单场主链统一为 `match_runs` / facts / entries / revisions；`match-workspace`、研究档案和旧观察表只保留兼容读与退役观察，不再作为活跃容器。
- 整体重构接点：`current_event/preparation.py` 管近期窗口、开赛时刻与明确赛事别名，`evidence.py` 管共享公开依据及可读来源投影，`trade_plan.py` 管预案存储兼容与条目合成，`match_records.py` 管记录词汇、栏目和纯展示投影。身份、明确写入、暂停恢复和冻结编排仍由原 service／repository 承担；不新增产品入口或正源。批次施工合同见《小雪整体重构-SSD》第3A节；局部结果和缺口见第10节。

1. 读 `AGENTS.md`（项目事实）+ 本文件（项目地图）
2. 定位要改的是哪块（前端/后端/数据/Skill/配置）→ 找上面对应的正源
3. 读 `memory-bank/modules.md` 里那一块的边界（"不动什么"）
4. 确认改动影响面（牵了哪些模块/表/接口，见第三节）
5. 小步改 → 隔离 outDir 构建 / `py_compile` → 相关测试 → 授权范围内真实入口验证 → 更新现有 sync；`memory-bank/progress.md` 保留导航。根 `dist/` 由正式服务直接提供，未授权发布不得覆盖。

### 跨模块改造如何实际使用地图

项目地图不是“读过即可”的说明书。**任何涉及多个既有模块的大改**——无论是赛制、数据链、算法、前后端、资料调用、入口或流程调整——执行状态只记录在现有 `memory-bank/progress.md`：以本文件第三节的**用户模块 ID**为行，逐项标注 `不受影响 / 已适配 / 待处理` 与真实证据。不得另建任务合同或平行路线图。

后续“继续”时先读取该矩阵，从首个 `待处理` 模块恢复；技术文件、脚本或单点异常只能作为该模块下的实现线索，不能反过来决定任务顺序。一次性重构期间，这个矩阵用于记录统一骨架对各模块的归位状态和缺口，不表示产品要按模块逐个发布。这样项目地图始终决定改造覆盖面，进度文件只保存本轮事实状态。

## 七、一句话收尾

**这个项目的可读性，靠的是"薄入口看全貌（本文件+AGENTS）+ 按需钻取（模块文件）+ 契约管影响面（module-contract+modules.md）+ 语义按需取（MemPalace）"——不是把文档合并成一个长文件。** AI 读完本文件就有了全貌，不会再只见局部去改。
