# 个人电竞交易辅助系统 — 任务进度

> 导航更新：2026-10-29 | 本次授权：项目规范合并与按模板整理目录

## 2026-10-29 · 规范与目录收敛

- Goal / Locked decisions：项目是部署在腾讯云的自用电竞交易辅助系统，包含前端、后端、数据库、知识和自动化；网页只是一个入口。体验、效率和实用性优先，沿同一项目正源服务网页与已接入的 Agent。项目规则统一在根 `AGENTS.md`，上位角色规则、专业 Skill 与机器合同各保留原职责。
- Current stage：规范合并和目录整理已完成；本轮测试与合同检查通过，活跃文档引用已核对。`AGENTS.md` 暂时完整收拢现行项目规则，后续由高级模型继续取舍和优化措辞。本次不实施历史 PRD、不迁移数据库、不发布前端、不重启服务或修改调度。
- Changed：有效项目约定由 AGENTS、旧地图流程、模块边界、总使用说明和 Loop 收敛到唯一根 `AGENTS.md`。旧地图、模块和使用说明路径只留兼容指针；旧需求卡、Loop、模型交接和 SPEC 原文保留在 `docs/archive/2026-10-29-guidance/`。`project-contract.json` 的通用规则改为章节引用，`module-contract.json` 的模型使用说明直接指向 `AGENTS.md`。
- Layout：选择用户提供架构模板中的 Full-Stack Web，轻量适配现有 `src/` 前端与 `xiaoxue_api/` 后端；技术导航归 `docs/architecture/`，1 份未标冻结的需求资料归 `docs/requirements/`，17 份已冻结设计原文归 `docs/archive/designs/`，历史审计归 `docs/archive/audits/`。其他脚本、配置、测试、部署与运行路径保留。旧进度中的文档路径仅机械重定位，未改历史结论或能力状态。
- Verified：`.venv/bin/python -m pytest` 运行项目模块、菜单来源和小雪 Skill 合同共 27 项通过，1 项无关 API 启动测试未运行；`scripts/verify_module_contract.py` 校验 9 个能力域与前后端映射通过，模型使用说明为 `AGENTS.md`。技术地图已改指向 `AGENTS.md` 的现行章节，活跃 Markdown 引用检查未发现仓库内断链。相关测试验证新正文和旧引用的兼容，不依赖历史 PRD 当现行规范。
- Rollback：保留本次开始时的未提交内容；AGENTS 原文包位于 `/tmp/xiaoxue-agents-consolidation-20261029-njhiIN/before-agents-full.tar.gz`，目录整理包位于 `/tmp/xiaoxue-guidance-consolidation-20261029-gCVq74/`，含 `before.tar.gz`、`project-contract-before.tar.gz`、`before-layout.tar.gz`、`changelog-before.tar.gz`。仅用于本轮文件恢复，不覆盖其他既有改动。
- Next / Blockers：后续由高级模型审阅 `AGENTS.md` 的规则取舍和措辞；外部访问入口、跨端对话同步和未来自动化不在本次验收范围。本轮未改变业务能力的既有 partial / 未验证状态。

## 2026-10-28 · 项目与 Hermes 解耦（已部署大部分，整体验收未完成）

- 私人系统补验：当前正式前端资产配临时后端/数据库，在390宽浏览器完成课题→方法→实践→反馈→沉淀，刷新及后端重启后均读回1个方法版本。明确使用虚构测试样例、生产API访问0；只补隔离页面证据，不冒充真实私人数据或飞书。见Delivery的jieyi-isolated-page-journey-20261028.json，临时服务已停止。
- 足球详情续验修复：真实比赛espn:esp.1:401882829详情曾将赛季年份2026作为kickoff；现改为上游competition.date，缺失保持空。新回归先失败后足球4项全通过，项目API重启后正式详情两次读回2026-10-25T17:30Z，health healthy；回退文件见Delivery backups/football-service-before-kickoff-fix.py。卡塔尔ESPN来源400仍保留partial；未改页面、范围、模型或飞书，整体未完成。
- Goal：按 `life-os-frontend-v2/docs/PROJECT_DECOUPLING_PLAN.md` 完成项目运行环境、业务任务、项目资料与 Hermes 的平台职责分离；保留原页面、URL、导航和飞书入口的使用方式，使电竞和私人系统能够独立运行，并让小白可按正式入口继续维护。
- Page fix（15:29）：按钧钧要求将飞书验收放最后，先处理独立项目。已修赛事主读取被参考检索超时拖垮、足球卡跨页显示及手机选队布局；原8880入口看到赛事正文、6场比赛和6个判断入口，桌面/390宽读回AL同一446字TK。手机表内横滑可到右侧列，文档宽度仍390。前端101项通过、隔离构建成功、dist已替换，未重启服务；回退包和证据见Delivery的 `a02-read-fix-20261028.json`。
- Production import（16:47）：项目模型读取显式引用既有私有model.env，环境变量优先、不插值、不注入其他键；lol_data声明并安装openai2.24.0、python-dotenv1.2.2，不改模型/Provider/推理参数/密钥值。09:24生产导入旧回执为partial，经正式 `apply_knowledge_import.py` 补跑后恢复为complete：B站4项中3篇写入、1条音乐视频not_applicable，微信26项中1篇写入、25项去重，两源失败均为0；四篇新TK与回执哈希一致。回执reindex为not_needed，正式8880 `/api/tk/search` 已实际读回新文章和视频，36项导入回归通过。证据为Delivery的 `a05-import-runtime-20261028.json` 和 `a05-production-import-retry-20261028.json`。
- Navigation followup：16:04原8880的TK资料库和项目中心双端可见，无页面/HTTP错误或文档横溢，补齐此前赛事、队伍、足球以外的两个主导航；探针拦截既有自动准备POST。结衣四页与知识摘要读回仍有效，全文入口缺失是既有设计。证据为 `a02-retained-navigation-20261028.json`。
- TK recovery：停止旧进程四个并发隐式下载，去掉外部uv工具site-packages借用，直接使用项目.venv-tk，服务PID1162841。15:54的503/degraded及1.3369秒返回12条文件资料只是修复中间态；唯一有界任务已完整下载83,178,821 bytes官方原MiniLM归档，SHA256 `913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3`匹配后原子发布六文件并自然退出，TK未再次重启。最新8770 health为200/ready，正式检索来源含mempalace/wechat/file；赛事页桌面7.434秒、390宽3.701秒显示12条/3511字参考，双端正文哈希一致，主要内容和6个方法按钮可读。无pageerror，唯一requestfailed是探针拦截既有自动准备POST。证据为 `a02-tk-runtime-repair-20261028.json`。
- Natural automation（15:20观察）：已只读核对14:40、14:50、15:00、15:10四次自然排程输出与15:10项目回执；6场确认比赛，两项受管计划changed:false，未手动触发或改排程。次日赛前/赛后实际执行和下游消费仍待发生。
- Deployed：小雪主站 API、TK 和产品 MCP 已分别使用 `xiaoxue-web/.venv`、`.venv-tk`、`.venv-mcp`；`lol_data` 使用自身 `.venv`。四个环境都没有加载 Hermes 私有 `sys.path`。14 个项目任务实体已归入 `scripts/tasks/`，Hermes 同名脚本改为 `os.execv` 薄转发；模型配置已移入 `config/model-runtime.json`。页面、原地址和一级导航未替换；两个无引用旧环境只移到交付包归档，未删除。
- Verified：13:05历史基线为前端99、后端432（另1 skipped）、TK4、产品MCP68、lol_data218（另6 skipped），早前补验项目中心/内容/菜单/健康20和TK adapter4均通过；当时health_check为ok:true/退出码0、迁移合同ok:true、八个用户服务active。15:29前端101项仍有效；16:08新增凭据4项、两个项目解释器各19项导入回归、.venv-tk的TK adapter6项通过。未重跑无关套件，不把旧健康当当前全绿；systemd用ubuntu的XDG_RUNTIME_DIR=/run/user/1000 systemctl --user检查。
- Historical health/resources：13:05完整API/页面快照和14:09资源复查均为历史采样；后者根分区82%/约6.87GiB可用，内存available约2.01GiB、Swap约2.13GiB，gateway cgroup约398MiB/峰值991MiB。网关当时有elevated memory pressure警告。后续只补TK恢复与页面证据，未重采全套资源，不据旧数字宣称压力已解除或全部health200。
- Test isolation incident：统一测试最初运行时，API 测试会启动 FastAPI lifespan 并恢复采集队列，测试没有全局隔离，05:50—06:08 期间生产采集目录出现了与测试时段高度吻合的新写入。已新增 `tests/conftest.py`，以 `XIAOXUE_COLLECTION_DIR` 强制所有测试进程进入临时目录，修复后完整测试才重新通过。已记录 9 个关联任务 ID，当前可定位 8 个，另 1 个 `787a6b0cde2ac94e79c2cea7` 未定位；没有删除或回滚。生产 API journal 只见 health 请求，旧测试 worker 子进程缺少完整日志，因此不能声称已完全归因。
- Acceptance（16:53最终证据收口，状态不升级）：A01 partial；A02/A05/A06/A07/A08/A11/A12和R1/R2/R3/R4 passed-with-limit；A03/A04/A10 passed；A09 unverified。五主导航双端、独立与生产导入、原模型补齐、正式8880检索读回及最后飞书只读复核均有新证据；A03仍只证明隔离副本写读回，结衣无知识全文入口属既有设计限制。overall_complete:false/released:false保持。
- A09 final read-only refresh（16:52）：网关PID1088277仍active；4个已知chat中默认主chat重启后有8条应用消息、用户消息0，默认次chat/小白/结衣均为0；三个Profile仅保留已知oneshot会话，无新增非CLI业务会话。未发送测试消息、未改配置。查询范围仅限既有已知chat与本地会话库，不代表查遍全部飞书会话；应用消息和CLI不能替代真实业务入站。
- Jieyi recovery：经钧钧当次明确授权，只把结衣默认模型和 `flash` 别名从已下线 `deepseek-v4-flash` 换成小雪同款 `deepseek-v4.1-flash`，Provider 仍为 `opencode-go`，未改密钥值；精确备份保留。单网关 PID 1088277 已加载新模型并连接 `jieyi:feishu`。网关最终重启后的 fresh CLI 已在 default/xiaobai/jieyi 三 Profile 复验；结衣 `20261028_124943_caee90` 完成 5 条消息/2 次工具调用，实际读取结衣产品知识库 40 条/已处理 40/待处理 0。A07/R2 为受限通过；A09 保留真实飞书业务链待验，按钧钧要求放最后，不阻止独立项目继续验收。
- Data safety：切换前回退包为 `.../backups/prechange.tgz`，152,671,382 bytes、19,335 entries、SHA-256 `21b0bd...53ef`。安全恢复主体得到 16,933 个普通文件/531,640,654 bytes，随机样本哈希一致；但含 19 个不安全链接且缺少四项历史材料。补充包只含四个当前状态文件，不是完整历史快照；生产恢复未执行。三个仓库既有脏工作树全部保留；没有 reset、checkout、clean、全局格式化或 push。
- Still unverified：真实飞书inbound→项目资料→工具→回复按要求最后验，有限CLI不能替代。五主导航与结衣四页/知识摘要已有双端证据，但未穷尽全部交互，结衣知识全文入口属既有设计。原MiniLM和赛事语义参考已恢复；当天生产导入及正式8880检索已闭环，远期次日赛前/赛后自然任务与消费仍待发生，旧失败不能由该闭环外推为全部同因。四次自然排程/15:10项目回执已观察；足球coverage仍partial。正式版本理解路由已200，旧version-analysis不是目标；当前磁盘约84%、内存仍紧，资源保留各自采样时间。
- Delivery：当前证据、事故边界、服务快照和 A01—A12 逐项结论见 `/home/ubuntu/.hermes/team/deliveries/verified-changes/decoupling-20261028/`。状态是 `deployed-partial` / `activated-partial`，`overall_complete:false`，不是 Released。

## 2026-10-25（第四轮）· 首发来源接通 + 网关重启

- 首发来源解决：新增 `scripts/sync_rosters_from_lolesports.py`，从 lolesports 官方接口同步 19 支 S16 队伍名单；保留已知首发，空位置按位置补；旧记录置 inactive 保留历史。默认 dry-run，`--apply` 才写库。
- 已执行 --apply：19 支队全部更新；11 支原先没有名单的队伍补齐；GEN/HLE/T1/DK 等原本的首发保持不变（Kiin/Canyon/Chovy/Ruler/Duro 等）。
- 覆盖变化：`/api/lol-scope/coverage` 首发缺口 16 → **0**（lineup ok 8/8）；缺口总数 24 → **8（只剩价格）**。
- 备份：`/home/ubuntu/lol_data/backups/rosters-20261025-152425.csv`（同步前 145 行）。
- Hermes 网关已重启（`hermes-gateway.service`），MCP 工具 37 → 最终 **35**（清掉 ScoreGG 合并后残留的两个工具），工具清单已在网关侧热载。
- 价格：探测了 oddsportal（可访问但 JS 渲染）、the-odds-api / odds-api.io（均需 API key）、pinnacle/bwin（拒绝）。没有免密可用的赔率接口，需要用户提供 key 或接受"不接价格"。

## 2026-10-25（第三轮）· 工具归并第二批 + 边界确定

- MCP 工具 39 → 37：判断目录与判断正文合并为 `xiaoxue_open_judgment`（不传 method_id 列目录）；讨论与续读合并为 `xiaoxue_discuss_judgment`（传 reply_id 读后续页）。
- 确定工具归并边界并写入 DECISIONS：只合并同对象、同参数形态、同副作用等级的工具；写入类异构参数不合并。
- 验证：MCP 单测 43 通过；后端 425 通过 / 5 项既有失败；前端 99 通过；合同校验通过；工作树干净。

## 2026-10-25（第二轮）· 收尾清理 + 工具归并第一批

- 清掉「沉淀候选」残留：页面卡片、CSS、页面路由、项目中心文案与节点标签、workflows 目标。
- MCP 工具 44 → 39：Gol.gg 6 个合成 `xiaoxue_get_gol_facts(kind=series|tournament|bp|entities|team|player)`；ScoreGG 3 个合成 `xiaoxue_get_score(kind=evidence|result|results)`。
- 修复三处历史遗留：MCP 写操作白名单里残留的已删路由、boolean 链断裂、被删模块的测试引用。
- 验证：后端 425 通过 / 5 项既有失败；前端 99 通过；MCP 单测 43 通过；合同校验通过；dist 已重建。

## 2026-10-25 · 模块归并到 7 个 + 两个概念退役（执行中）

- 后端实现模块 20 → 7：team / match / knowledge / methods / daily_content / platform / external。
- 删除：analyst、weread_bridge、legacy_trades、market_notes；空目录 business_updates/pre_match/pro_stats。
- 概念退役：「沉淀候选」「盘口记录」的页面、标签、入口、接口、MCP 工具、能力树节点全部移除；数据保留在 TK。
- 线上 dist 已重建并与源码对齐（上一版备份 /home/ubuntu/dist-backup-20261025-150810.tar.gz）。
- 文档：22 篇标记为历史冻结；新增 docs/archive/DECISIONS.md 作为决策正源（三份正源：PROJECT-MAP / progress / DECISIONS）。
- 验证：/api/health 7 模块 healthy；后端 425 通过 / 5 项为改动前既有失败（事件筛选 3、基本面单场 2）；前端 99 通过；合同校验通过；独立目录构建通过。
- 未完成（需要决定或另行排期）：MCP 工具 44 个尚未按对象归并；单场页五个动作（今天/读一场/记一句/找回/提事）未动，按钧钧"页面先不动"的要求暂停；首发与价格来源未接。

## 2026-10-22 Codex：足球观察台产品与工程规格（当前授权）

- Goal：在小雪工作台内形成可直接开发的足球观察台；页面给出半破与75分钟后两种独立赛前筛选结果，比赛开赛后仍可查，钧钧只按需写交易TK。
- Executor：钧钧在本次任务明确授权 Codex 直接施工；不改变项目长期角色分工。本段只记录当前任务，不代表足球功能已上线。
- Locked：不打分、不算概率、不跟踪变盘；滚球盘口、25/45/75/80分钟字段由钧钧自己看，不是系统依赖；缺资料不伪造保留/排除；后台提前准备并保留赛前版本；沿现有交易TK正源，不建平行应用或记录库。当前默认办法已补入PRD：半破初盘3球以上排除、去掉无法提供的五项四项；75分钟玩法按初盘/名单圈池、最近5场晚段支撑和已核实阵容筛选。
- Written：`docs/archive/designs/足球滚大球赛前筛选-PRD.md`、`docs/archive/designs/足球滚大球赛前筛选-SSD.md`；旧 `docs/archive/designs/足球滚大球赛前筛选-idea.md` 已标为历史并指向新文档；`docs/PROJECT-MAP.md` 已补导航。
- Current stage：足球后端模块、ESPN只读赛程/详情接口、公开摘要 `open` 初盘读取、文件缓存、工作台“足球”入口和内嵌详情页已落地；足球对象合同仍为 `planned`，尚未接生产排程。交易TK已能从足球卡跳到正式 `/api/trading-tk` 表单并带入比赛/玩法，尚未做独立比赛ID字段的结构化读回。
- Verified：足球模块注册/架构测试通过；足球单测3项通过；隔离Vite构建通过；Playwright实测桌面与390宽手机入口、候选卡、详情阅读、足球TK预填和无横向溢出通过；真实ESPN接口取到样例赛程和2.5初盘。
- Next：把文件缓存接入已有后台排程并补近5场晚段历史资料；再评估是否需要给交易TK增加结构化比赛ID字段。不把当前公开源覆盖当成全联赛生产能力。

## 2026-10-21 Codex：本次约定重构快速收尾已交付

- 修复登记名单误标本场首发，保留IG全部8名登记成员并说明不代表首发；不改人员数据。定向Node／Python、编译和diff共4项必需检查通过，隔离Vite构建通过。
- `xiaoxue-ssd-closeout-20261021` 的7个目标于23:40:23（北京时间）verified/activated，正式API已重启。1280／390正式网页进入GEN–IG看到新标签和材料，刷新后仍可读，窄屏无横向溢出。
- 产品MCP两页读完8场，并逐场按相同revision读回非空要点；另抽读GEN–IG共享正文、引用和出处。8场均partial，不冒称已整理完成。核对前后8场revision／更新时间一致，没有主动重开研究探针、写交易／长期知识、改排程或外发消息。
- 原10分钟自动准备及有限恢复保持；自然飞书新会话、未来连续供给、资料深度和模型质量仍有未验／缺口，但不再自动延长本次授权工程。唯一最终记录见[SSD第12节](../docs/archive/designs/小雪整体重构-SSD.md#12-快速收尾交付2026-10-21)。

## 前阶段：整体重构第3A批次覆盖发布（历史）

- 正式激活 `xiaoxue-ssd-batch-coverage-20261021`：27 个交付目标、5/5 验收通过；不覆盖本批以外的工作区改动。
- 工作台 API 重启后正式 8880 页面、近期看板、逐场覆盖 API 均 200；S16 当前窗口 8 场：部分整理 8、已准备 0、未开始 0，每页4场并给逐场限制、修订和正文读取入口。
- 小雪 Hermes 网关重载后新 MCP 注册近期准备工具；MCP协议发现和只读调用成功，返回同窗口和分页。飞书 WebSocket 恢复连接；未代发消息、未重启小白或结衣。
- 启动时恢复的3个既有任务读回均 partial、attempts=3；不是完整准备。现有 `LOL自动化排程器` 每10分钟运行且 last_status=ok，其包装脚本调用 `scheduler-tick`；没有新建重复定时任务。只证明这3个任务达到恢复上限，不能推导全部8场均已达到上限。
- 整体目标仍未完成：补查质量、自然飞书对话实际使用新工具、未来多个周期的持续产出未完整验收。正式证据与限制见[整体重构 SSD 第11节](../docs/archive/designs/小雪整体重构-SSD.md#11-本轮实施进度2026-10-21)。

## 任务入口与历史边界

最终收尾见[整体重构 SSD](../docs/archive/designs/小雪整体重构-SSD.md)第12节；第3A节保留能力合同，第11／10节为历史批次与资料卡交付。后续仅按真实使用的具体问题沿原链处理，不另建采集系统，也不因下方历史“整体未完成”字样重复施工。

## 前期运行证据：S16准备与判断入口（03:52 摘要，历史）

本段保留原记录。更晚的赛事总览可读与未完成窗口等证据见 `docs/archive/designs/当前赛事信息收集能力重构-SSD.md` 第 8.2 节；不要将以下“总览尚无 digest”当作本轮最新事实。

钧钧明确“全部完成”后，已接正式工作台/小雪及原后台准备链。正式8880与网关已重载，原排程器每10分钟检查，原日报07:00不改，仅消费同截止成果。默认先看粗筛与系统推导，已有理解视角可进入；长背景收起、真正阅读后记本机位置、实质变化逐条提示。19/19 S16队伍现均可读筛选观点和条件解释；其中11/19有可核发表日期，另8队日期未知但并非无成果。赛事总览仍因一次模型返回空内容未产出digest，页面诚实保持准备中，禁止误报无相关信息；未拿团队内容冒充赛事综述。正式知识、画像认可、个人判断、预案、模型/Provider均未覆盖。

| 用户开发模块 | 本轮状态及边界 |
|---|---|
| current-event-prep | 正式入口已启用；依赖失效/同正文复用、19队筛选和条件解释、原目录/MCP、阅读变化已实现；赛事总览digest仍待原模型有限恢复 |
| daily-and-automation | 原wrapper已发布，原排程每10分钟检查；日报冻结消费者接通，未额外发布；未来真实赛前连续交付待观察 |
| knowledge-and-data | 仅按public读正式版本/画像/TK和实际来源；未写正式知识/索引，不把旧26.16或未核画像当S16事实 |
| 交易记录/独立阵容/项目中心 | 保留原职责和入口；不加项目中心日报阅读，不自动交易或确认采用，不调用纯阵容流程 |

接线套件5/5通过（Python124、JS85、MCP44、wrapper5、日报57），独立子进程/共享两锁验证通过，不代表事件级摘要通过。正式8880已读回T1媒体首发限定、LYON反证和TLAW观点；390窄屏无溢出。小雪全新会话从自然问题一步读取BLG结果，未搜索、采集、保存。后台排程器实际自动运行成功。六份误入的单测来源缓存已精确移入可恢复隔离目录，真实来源/业务数据未删除；测试强制临时目录和无网/无模型。运行边界和读回证据统一记原SSD第8.2节。总目标仍未完成：赛事总览digest需要模型恢复，且连续三场真实赛前送达只能等未来赛程证据，不能提前宣称完成。

## 上一阶段：赛事两线分析重构（历史）

2026-10-19 用户明确授权“写对应的ssd然后执行”，并要求子代理并行。当前规范为原PRD及原SSD第1—9节；旧32节点只作影响清单。三主责已分别落盘：原知识提炼runtime故障修复与正文验证；单场公开粗筛+正式方法执行/条件身份+原页面/MCP精炼读回；跨日24小时准备与原日报冻结消费（默认未启用）。不新建日报、知识库或MCP，项目中心日报阅读动作已撤回。

最终复验：完整后端/MCP308、前端61、lol_data导入/两线日报/原日报/冻结75项通过。隔离原入口真实KC–MVK得到4条报道背景及有引用的中立条件推导；修订981670ee03c47352fe12，partial/ready=false，没有作者实质分析或比较，不能宣称赛前信息优势。B站真实字幕提炼通过但未正式导入，公众号仍受验证页限制。正式8880/dist、生产排程/日报开关、真实业务/知识/索引和外部发布均未操作；生产接线启用需明确确认，连续三场赛前与正式机器人新会话未验收。备份 /tmp/xiaoxue-two-lines.jFj0Rz/before.tar，具体实现、证据和交接点统一在原SSD第9节。总目标未完成；下文仅为旧版历史。

## 前版局部实施（历史）

用户目标是自动准备完整成果，不再承担搜索、抄录和拼接；仍按原 8 类 32 节点验收，不以单场采集代替全目标。已编写 `docs/archive/designs/当前赛事信息收集能力重构-SSD.md`，第 10 节为本次执行证据和逐节点状态唯一记录。

已启用切片：原单场页面自动收集、可恢复任务与证据快照、带原句出处的中文要点、唯一产品 MCP 两个命名工具与分页、日报真实发布回执和原项目中心成品链接。正式 `8880 → 当前赛事 → KC–MVK → 比赛资料` 实测取得 7 条中文要点和 4 篇原文，刷新读回修订 `9758257313d8e4ab4ca5`；390 窄屏无横向溢出、页面异常 0，真实业务数据库字节不变。完整后端 285、前端 57、日报 40 项通过，旧正式路由全部保留。两个 verified 交付包已激活，既有 API 服务重启后 PID 955108；仅按需工作台已启用，不能推导全目标完成。

基线阻塞已解除：保留用户改动将现网分支能力整合进原工作树，没有切分支/reset/提交/推送；交易预案、Gol.gg、scope、business-mutations、全局版本与三阶段单场均保留，退役入口未复活。修复 GET 建表/保存预案/暂停单场的副作用、跨场晚到响应及赛前回放泄漏事后资料；日报昨日冻结按精确比赛 ID 取原时点两队上下文，40 项回归及独立复审通过，原数据缺失不伪造。未写真实业务库、未改生产 cron/模型/网关、未发布日报或发消息。仍未完成：完整双方研究、可靠首发/逐局 BP/带时点报价、赛后与知识闭环、新材料进入日报生产、提前准备排程及正式机器人新会话。不能承诺用户已经不必网上搜索。备份、交付包和真实入口证据统一记在 SSD 第 10.5 节；沿同一 SSD 继续，不另建平行系统。下文旧进度仅为历史，不覆盖本区事实。

## 合并恢复的既有进度（历史）

## 2026-10-17 小白：受管自动化被 Hermes 静默删任务的事故修复（排程器 + 失败告警）

- Goal：处理「LOL 自动化失败告警」——`LOL赛前简报`/`LOL赛后刷新` 报"暂停/停用，赛前赛后不会自动跑"。查证后确认不是误报本身，而是真事故：任务已经被删掉了。
- 根因（已用 Hermes 自身代码复现）：受管任务是对**同一个 Hermes once job 反复改期复用**，而 once job 创建时自带 `repeat.times=1`。`LOL赛后刷新` 10-17 06:31 跑过一次（`completed=1`），09:00 排程器把它改期到 11:30；11:30 到期扫描命中 `Job 'LOL赛后刷新': one-shot dispatch limit reached (1/1) — removing stale due entry` 直接把任务从 `jobs.json` 删掉，脚本再没执行 → 当天 07:00 C9 vs FUR 赛果未刷新、结果消息未发、10-18 赛程仍是 TBD。失败告警本身还有第二层缺陷：把"任务停用"当故障，而受管任务跑完自然停在 `completed`、本阶段无比赛会被排程器主动暂停，于是每天固定时点误报。
- 修复（lol_data + `~/.hermes/scripts`）：①`lol_auto_planner.py` 武装顺序固定 `--repeat 0`（清消耗上限）→ `--schedule` → 按需 `resume`，任务缺失时按定义重建；受管任务定义收敛到 `config/system_config.json` 的 `automation.managed_tasks`。②`xiaoxue_automation_watchdog.py` 判据改为以排程回执为意图正源，只报"回执排了时刻却没武装/到点没跑/被暂停/回执过期"。③排程器 wrapper 的告警标记同步新文案。
- 验证：沙箱 `hermes cron tick` 真对照——旧序列（只 `--schedule`）任务被删且零输出，新序列（`arm_steps`）跑出 `PROBE OK` 且任务保留；到期扫描对照（`times=1/completed=1` 删、`times=null` 保留）固化为 `tests/test_lol_auto_planner.py::DueScanGuaranteeTests`，告警判据 12 项；lol_data 全量 185 passed。生产现状：`LOL赛前简报` 已武装 2026-10-18 00:30（repeat ∞）、`LOL赛后刷新` 已重建并武装 2026-10-18 06:30（repeat ∞）；当日缺失数据已补（C9 vs FUR → FUR 1:3）；告警实跑静默。
- 文档与边界：SSD `docs/archive/designs/LOL信息与自动化整合-工程实现.md` 5.1/5.4 补记形态约束与回归口径；`/home/ubuntu/.agents/skills/devops/cron-inspection-debugging` 新增根因 9/10。未改数据库结构、模型、Provider、权限、网关或 cron 配置；未发外部消息（只在项目既有推送目标内补跑被漏掉的那次刷新）。

## 2026-10-16 小雪：比赛面收拢 S16 世界赛（口径 + 自动化）

- Goal：钧钧要求「LOL 项目比赛只关注世界赛，修改不一致的口径和自动化任务」（清单确认后执行）。
- 口径：`competition_registry.json` 世界赛置 `exclusive`（唯一研究范围；德杯保留在册、数据照常入库，仅不进日报/研究；版本 2026-10-16）；`team_priority.json` 核心=世界赛 LPL/LCK 出征队（AL/BLG/TES/IG/GEN/HLE/T1/DK）、常规=外赛区世界赛队（C9/FUR/G2/KC/MVKE，随名单补全）；工作台当前赛事事件名/检索词/知识图链接收拢为「S16 世界赛 / q=世界赛」。
- 工作台显示：`current_event/config.json` 新增 `leagues: ["S16全球总决赛"]`；看板与今日内容比赛列表按当前赛事范围过滤（新增 `get_current_event_scope_leagues` / `match_in_current_event_scope`，经 current_event.public 暴露、daily_content 走 public 调用）；10-17 起德杯决赛不再出现。
- 自动化：日报研究范围随注册表收拢；每日巡检「今日赛程」从 LPL/LCK 扩到含国际（不再误报「今日无赛程」）；数据刷新/知识导入/概念图/梗库/月度清理保持全量不动。
- 两处阻塞补丁（lol_data）：`collect_daily_context.py` 选择器 tri-state——已登记但不在研究范围记 `excluded`（不阻断），未登记 `league_id` 仍报错；未决对阵（TBD）拆分为 `pending_today`，只进「今日赛程」（标待定）不入逐场/舆论，`build_daily_report.py` 同步渲染；协议 §7 更新。
- 验证：lol_data 144 passed + check_config_facts 0 违规；10-16/10-17 上下文实测（active=[WORLDS]、德杯行 excluded、待定 2 行）；10-17 全流水线 dry-run `audit_ok=true`（runs/2026-10-17 已清理，不污染正式冻结包）；xiaoxue-web 208 pytest / 44 node / build 全过；8880 重启后 current-event、dashboard(10-17)、daily-content 读回正确；巡检脚本实跑显示世界赛赛程。
- 备份：`lol_data/backups/worlds-scope-20261016/`、`.xiaobai-backups/worlds-scope-20261016/`、`~/.hermes/scripts/xiaoxue_daily_inspection.py.bak-20261016`。未提交 git（工作树含小白既有未提交改动，避免混入）；未改模型/网关/cron 配置；未发外部消息。

## 2026-10-16 小白：小雪"会什么"菜单与项目中心内容合并为一份正源

- Goal：项目中心内容更新后，小雪在飞书里给的"我会什么"菜单自动跟上，不再两边手工同步。
- 做法（让不一致在结构上不可能）：`config/project-center-content.json` 的 `manual` 是小雪菜单的唯一正源。根 Skill「引导与菜单」不另抄功能清单，只指向正源 + 新增的 `scripts/xiaoxue_menu.py`（读正源输出菜单，`--scenario <id>` 取单场景完整口径）。原先手写在 Skill 里的 5 条常用说法（周期扫描 / 盘口判断 / 分析师 / 其他电竞 / 研究底稿）移入正源 `manual.extras`。
- 可见结果：项目中心「使用说明书」页尾新增"说明书之外的常用说法"区块，逐条可一键复制发给小雪；与小雪菜单同源，改一处两边一起变。用真实 8880 接口数据走前端模板渲染核验：区块正常渲染、10 个可复制按钮、无空 prompt。
- 验证：pytest 211 passed（新增 `tests/test_project_center_menu_source.py` 9 项：菜单覆盖全部场景与 extras、输出不含路径/接口/内部字段、单场景含边界、未知场景列出可用 id、Skill 菜单节不保留副本、extras 覆盖常用说法、模块一览与单模块口径来自同一正源、使用说明不再抄模块表）；`node --test tests/*.mjs` 44 passed（新增 extras 渲染断言）；`npm run build` 通过；8880 健康、`/api/project-center/manual` 已返回 extras、实际服务的页面与分块已带新区块。
- 备份与边界：Skill 备份 `/home/ubuntu/.agents/skills/小雪/SKILL.md.bak-project-center-sync-20261016`。未改数据库、模型、Provider、权限、网关或 cron；未发外部消息。
- 收尾（同一原则）：`docs/小雪项目总使用说明.md` 的 8 行模块表已删除，改为指向正源（运行 `scripts/xiaoxue_menu.py --modules` / `--module <id>` 或直接读 `module_tree`）；该文档其余产品口径不变，`config/module-contract.json` 仍是模块 ID/正源/入口/字段映射的唯一事实源。

## 2026-10-16 小白：虚拟数据衔接调查 + 当前赛事看板 TBD 缺陷修复

- Goal：用生成的虚拟数据测小雪项目各层互相衔接，为后续修改做基本调查；调查中发现并修复真实断点。
- 隔离环境：`/home/ubuntu/xx-linkage/`（生产库副本 + 隔离 Wiki + 隔离 config；后端 8899、前端 5273 指向 8899）。虚拟实体：ZZA/ZZB、VTC测试赛 2026、赛程/赛果/TS 快照与展示/三维/画像/版本理解行/两份虚拟 TK。生产库与生产 Wiki 零写入（已核对）。运行器：`fake_env.py`（造数据）、`probe_linkage.py`（后端链路）、`frontend_contract.py`（前端实际调用的接口）、`mcp_probe.py`（Agent 工具）、`run_survey.sh`（一键重跑）。
- 调查结论：读链/写链/跨模块/Agent 工具共 40 项通过、0 失败。写入链（单场建立→依据 10 条→环节记录→阶段推进→判断→长期候选、TK 写入与读回、画像写回）全部落到隔离库；前端模块实际调用的 30 个读接口全部 200 且拿到虚拟数据；Agent 层（`xiaoxue-product` MCP，`XIAOXUE_API_BASE_URL` 指向隔离后端）8/8 通过。
- 修复的真实缺陷：`GET /api/current-event/dashboard` 遇到 `team_a == team_b` 的 TBD 占位赛程时整页 400（“两边队伍不能相同”），生产 2026-10-17 起 S16 世界赛 TBD 行日期全部不可读。现由 `current_event.service.is_unresolved_matchup` 统一识别未定对阵，`_match_summary` 返回 `pending=True/pending_reason` 且不再进入严格对阵校验；`normalize_match_identity` 报错文案改为“对阵未定：双方队伍尚未产生”。生产 8880 已重启：2026-10-17/18/19/24、11-04 由 400 变 200，TBD 显示为待定卡片，真实对阵照常可进入。
- 前端：`src/modules/current-event/view.js` 待定行渲染为不可点击卡片（新增 `.event-match-button.is-pending` 样式）。
- 盘口页死链清理：前端 market-notes 的写动作全部改接唯一正源交易 TK——保存→`POST /api/trading-tk`、复盘写回与标记失效→`PATCH /api/trading-tk/{filename}`、复盘预览改本地生成、记到队伍→`POST /api/trading-tk`（scope=team）；“删除”改“标记失效”，页面对齐只读投影说明。
- 新增/更新测试：`tests/test_current_event_dashboard_pending.py`（5 项，占位行不崩且真实对阵照常）；`tests/workflow_ui.test.mjs` 期望同步为 `trading_tk`。
- 验证：pytest 201 passed；`node --test tests/*.mjs` 43 passed；`npm run build` 通过；隔离环境复跑衔接调查 40 PASS / 0 FAIL（唯一 GAP 是“虚拟新队伍没有 Wiki 实体页”，属预期前置条件）。
- 已知边界（未改，留给后续）：版本理解按固定对象（id=229）读取，往 `shared_version_analysis` 加新行不会自动成为当前版本；TK 语义检索在 MemPalace 8770（独立进程），写入后需 reindex 才可检索；`config/system_config.json` 由 DB 路径父目录推导，隔离或搬迁 DB 会静默回落到内置阶段 token。当前环境浏览器工具不可用，前端只做接口级验证，未做像素级渲染验证。
- 未修改：数据库内容、Skill、模型、Provider、权限、网关配置；未发布日报、未发外部消息。

## 2026-10-16 Codex：阵容分析文字改为具体判断（已激活）

- 用户反馈四阶段和兜底报告充满“实际看情况、需要现场验证”等安全套话，路线差异没有信息量。本批同步修改 Skill 输出合同、模型提示和 analyze_lineup.py 兜底生成器。
- 四阶段现在按“哪几条路线先动 → 资源落点 → 反转事件”生成；10–20 与 20–32:30 即使曲线相同，也分别落到先锋/小龙先手和二轮资源团站位/清线，不再写空泛占位。风险只保留会推翻主链的两条条件。
- 交付包 /home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-wording-final-20261016/manifest.json 已 verified/activated；25 项回归、真实快照、语法检查全通过。
- 同一真实十英雄输入 /tmp/lineup-analysis-darjuhog/：取数 6.698 秒，最高档位模型 76.035 秒后截止，总 82.735 秒；ultra、max 保持不变。正文禁用套话检查全为 0，四阶段均出现具体路线或转折信息，targeted real-use gate 通过。
- 未改模型、Provider、思考档位、网关、密钥、权限或业务数据，未重启或主动发飞书。

> 当前发布版本：`2.2.0`｜项目中心系统结构图与交易对象目录已完成并通过真实页面验收。

## 2026-10-16 项目中心内容对齐真实现状

- Goal：保留现有格式，修正开发模块与对象目录对当前可用范围的描述；本次用户明确授权 Codex 实施。
- 已观察：整体部分可用；日报当天内容未齐，日报与知识自动化检查因当天数据就绪信息缺失而需要处理；不能据此推断所有定时任务失败或主动暂停。
- 修正项目中心状态聚合：后端正常响应不再覆盖模块合同的 partial；展开项列出受影响能力及原因，异常项的下一步先说明局部处理与可继续使用的入口。
- 内容版本 `2026-10-16.1`：更新方法/阵容/关注范围、日报、知识导入、单场与阶段复盘等说明及相关下一步；清除旧盘口可写、默认日报稳定产出、缺内容等于主动暂停等误导。
- 四个对象在原对象合同内补齐现在能做、不能保证、使用入口、下一步和缺口；LOL 的 active 表达为主业务已接入，不宣称全部稳定或无缺口；未新增业务能力或第二套事实源。
- 验证：定向 Python 10 项、Node 10 项、模块合同检查、py_compile、build 和 diff 检查通过。从 `http://127.0.0.1:8880/#project-center/objects` 实际进入对象目录、开发模块、使用说明和开发书；1440×1000 / 390×844 均显示正确，刷新后结果保留、无页面脚本错误及横向溢出。截图 `/tmp/project-center-objects-{1440,390}.png`、`/tmp/project-center-modules-{1440,390}.png`。
- 运行入口：本机 10075 未监听，使用工作台稳定入口 8880 核验；原临时后端进程在检查期间退出，已启动现有 `xiaoxue-workbench-api.service` 加载本批代码，未修改服务配置或启用状态。
- 范围边界：未修改业务数据、Skill、模型、权限、网关或 cron，未发布日报或发外部消息；日报与自动化故障仍待单独处理，本次不宣称其恢复可用。

## 2026-10-15 项目中心结构图与对象目录

- 项目中心新增“系统结构图”和“交易对象目录”两个视图；结构图说明人—小雪—信息—普通 TK—交易 TK—当前判断—结果/复盘，目录直接读取对象合同及缺口。
- 使用说明、PRD/SSD 已补充新增足球对象、给 CS 增加信息源的操作路径；TK 概念关系图保持独立，不作为项目结构图正源。
- 真实页面 `#project-center/architecture`、`#project-center/objects` 已打开并截图确认；对象目录读到 LOL、无畏契约、CS、足球四个对象及状态/缺口。
- 定向 Python 15 项、前端 Node 18 项通过，`npm run build` 通过；旧 8880 进程已重启以加载新代码。

## 2026-10-15 Codex：统一骨架重构文档定稿（仅文档）

- 用户明确本次目标：梳理整合现有内容进入“人—小雪—信息—普通 TK/交易 TK—结果”的统一骨架；缺信息或缺方法以后直接补内容，新增 CS、足球等交易对象不应重写公共结构。
- 已更新：`AGENTS.md`、`docs/archive/designs/交易信息系统-总体设计.md`（PRD）、`docs/archive/designs/交易信息系统-工程实现.md`（SSD/一次性重构方案）、`docs/PROJECT-MAP.md`、`docs/小雪项目总使用说明.md`。
- 已固定：普通 TK 与交易 TK 的语义和写入边界；现有内容归位表；交易对象包合同；内容缺口与系统缺口区分；一次性重构目标；无 README 新增计划。
- 已降级为历史证据：无畏契约首个 MVP、F-000 至 F-006 施工分组、旧局部验收记录。它们可供迁移和回归参考，不再定义整体产品范围或要求用户逐片批准。
- 本轮没有修改代码、配置、数据库、Skill、运行服务或外部消息；文档完成不代表运行态完成。等待钧钧明确喊施工后再执行代码重构。
- 2026-10-15 施工已开始：未清理工作树既有改动；收口 `tk` 合同，使普通 TK 与交易 TK 共用资料库但拥有不同类型、交易 TK 状态/复查和独立写入入口；旧 `交易` 标签仅作兼容读取。新增 `/api/trading-tk` POST 与 PATCH，MCP `xiaoxue_remember(trading=true)` 改走正式交易 TK 写入。
- 新增 `config/project-contract.json.object_catalog`（shared-object-package-v1），登记 LOL、无畏契约、CS、足球的对象状态和内容缺口；补充交易 TK、对象目录和兼容投影回归。定向测试 50 项通过，模块合同验证通过，py_compile 通过，`npm run build` 已通过。
- 验证：`scripts/acceptance_check.py --base http://127.0.0.1:8880` 通过（模块合同、health、盘口只读、TS、画像、TK、版本理解）；全量 pytest 为 192 passed / 1 failed，唯一失败是外部 `lol-lineup-analysis/SKILL.md` 当前文案缺少既有测试期望的“用户给出蓝红方十英雄”，与本次变更无关；`git diff --check` 另报告既有 `src/modules/current-event/api.js` EOF 空行，未覆盖。
- 最终收口：对象目录已接入 `product_modules`、公共模块目录和项目中心 overview/modules；TK 浏览记录明确返回 `knowledge_tk`、`trading_tk` 或 `legacy_trade_label`。补齐外部阵容 Skill 的十英雄输入边界后，全量 `pytest` 通过（193 passed），`npm run build`、相关 `py_compile`、`verify_module_contract.py` 和 `acceptance_check.py --base http://127.0.0.1:8880` 全部通过。

## 2026-10-15 Codex：清理阵容分析用户可见正文（已激活）

- 用户反馈阵容分析正文混入运行模式、模型说明、来源状态、原始统计和输入确认等杂项。本批保留完整结论栏目，但移除这些工程与资料底稿；只有明确传入比赛版本时才显示版本行。
- 正式交付包 `/home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-display-clean-20261015/manifest.json` 已 verified/activated；接收端第二次回归 24 项全过，首次失败是既有进程清理测试竞态，重跑通过。随后同步 Skill 输出合同的 `/home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-display-contract-20261015/manifest.json` 也已 verified/activated。
- 同一真实十英雄输入 `/tmp/lineup-analysis-33t1jtx3/`：取数 8.840 秒，最高档位模型 76.521 秒后截止，总 85.363 秒；配置 `ultra`、请求 `max`；正文保留四阶段、核心链、控制/替代、三路线、24 场景、画像、32:30 与观赛验证，且不含运行模式、模型说明、来源状态、原始统计、文件名或输入确认。
- 真实使用验收 targeted gate 通过；未改模型、Provider、思考档位、网关、密钥、权限或业务数据，未主动发飞书。

## 2026-10-14 Codex：最高档位下保留全部栏目（已激活）

- 用户明确要求所有栏目都保留。本批把超时快照从“未完成占位”改为基于本轮曲线/来源证据的完整保守判断：结论卡、四阶段、核心链、控制/反制、三路线与野区、版本契合、24场景、比赛画像、32:30、风险、来源确认全部输出；不编精确技能数值，统一降低置信度并标注快速模式。
- 最新交付包 `/home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-fast-full-20261014/manifest.json` 已 verified/activated，3项接收端测试全过；上一版截止包与回退证据保留。
- 同一真实十英雄输入 `/tmp/lineup-analysis-nsonbki5/`：取数9.388秒，最高档位模型76.659秒后截止，总86.048秒；配置 `ultra`、请求 `max`；报告四阶段、三路线、24场景主类/候选和32:30均有内容。
- 当前真实边界：这是“全部栏目保留的快速证据判断”，不是模型完整技能链长推理；完整模型若在75秒内完成则仍优先使用完整判断。未主动发飞书，本批没有扩大为外部投递验收。

## 2026-10-14 Codex：最高思考档位下的截止交付已激活

- 用户选择保持最高思考档位。本批没有改模型、Provider、reasoning_effort、max_tokens、网关或全局配置。
- 正式 `lol-lineup-analysis/scripts/analyze_lineup.py` 增加75秒模型流截止：最高档位模型仍未结束时主动关闭流，程序基于本轮已采集证据生成完整但保守的“快速证据模式”；明确标注未完成技能链、24场景和32:30推演，不发布截断模型正文、不自动续写。
- 正式 Skill 已同步说明该兜底边界。交付包 `/home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-speed-deadline-20261014/manifest.json` 已 verified/activated，接收端3项测试通过；上一版回退包仍保留。
- 同一真实十英雄输入实测 `/tmp/lineup-analysis-evpu2o4x/`：取数9.001秒，模型流76.545秒后截止，完整快照报告总耗时85.547秒；配置 `ultra`、请求 `max`，无模型正文，报告含快速模式标记，四阶段/三路线/证据附录齐全。
- 结论口径：这是“最高档位不降级、两分钟内必交付保守快照”的性能完成；不是完整技能链模型分析在两分钟内完成。真实飞书群聊新会话尚未由本批主动发送验证，不能把本地脚本证据扩大成飞书投递证据。

## 2026-10-14 Codex：连续优化实测与思考档位授权边界（目标未完成）

- 用户最新要求“一直做到完成”，取代此前每批一次测试的限制。本轮连续执行三次同原模型/Provider/ultra实测，候选仍未发布。
- 十英雄局部技能资料和逐路分组输入：`/tmp/lineup-analysis-ct08n9_7/`，完整175.352秒，取数10.917、模型约161秒；并未提速。五段并发：`/tmp/lineup-analysis-awljmjc7/`，185.279秒，战略判断用尽16384推理token、无正文，失败。进一步拆分场景和版本：`/tmp/lineup-analysis-gl0vho1o/`，完整148.257秒，取数12.584、战略124.536、场景134.316；仍超120秒且尚不含小雪回复耗时。
- 无效并发方案已从候选撤除，正式版本保持第一批脚本入口。候选仍为单次统一判断与完整JSON模板，新增显式`--analysis-effort low/medium`提案参数；未向真实Provider执行任何降档请求。25项回归通过，包括默认沿用配置、显式参数仅在模拟传输中测试、不修改配置的回归；这不证明提案的实际速度或业务质量。
- 刚核对`devops/hermes-model-config/SKILL.md`的用户硬约束：model/reasoning_effort/context_window/provider不可自动触碰，改档位须用户明确点名授权。仅在阵容脚本请求内降档也不能绕过。后续必须先获这项明确授权，再执行同题完整实测、新会话回复及质量验收；不把不断调整提示词当成已经解决。
- 边界：无遗留分析进程；未改正式Skill、思考/模型配置、网关、密钥、权限或业务数据，未重启、主动发飞书或提交。候选和证据位于现有`lineup-speed-template-20261014/`及`lineup-batch4-report.md`。

## 2026-10-14 Codex：阵容提速第二批（候选未激活）

- 本批只改候选analyze_lineup.py的输出模板：程序展开完整四阶段与三路等级窗口，替换原伪JSON占位；比赛版本限制直接引用definitions。保留判断字段、三源、24场景及原模型/Provider/思考设置，未改正式文件或运行配置。
- 22项回归通过；本批唯一一次实时完整脚本复测 `/tmp/lineup-analysis-_ejb02ee/`：取数10.049秒，模型112.785秒，完整报告124.847秒，stop，reasoning_tokens=8045、completion_tokens=10705。四阶段与三路线权均齐全，但尚未全面验证判断质量。
- 与此前完整候选138.587秒相比本次快13.740秒，仅为两次样本观察，不能证明稳定提速。仍超120秒，且不含小雪加载Skill与回传全文的耗时；端到端目标未通过。
- 候选包 `/home/ubuntu/.hermes/team/deliveries/verified-changes/lineup-speed-template-20261014/` 留在暂存区，没有覆盖正式版本。本批不再追加模型实测；待办仍是推理提速与正式完整回复验收，不表示后台持续执行。

## 2026-10-14 Codex：阵容提速分批收口（两分钟目标未完成）

- 用户要求：继续优化，实际小雪测试约十分钟；随后要求分批进行。本批停止新增长时间复测，无残留计时或分析进程。
- 已观察根因：default会话 `20261014_180639_8a06655f` 取数约8秒，随后两次生成耗尽输出额度并续写，记录约605秒；上一轮压缩只进入本地计时器，正式聊天仍收到大证据包。
- 第一批已实施：正式Skill改为调用 `analyze_lineup.py`，并发取数、当前模型一次统一判断、程序生成完整报告；证据包保留版本正文和全部24场景，删除曲线平均分/胜率均值选场景；修复烈娜塔别名，保持十英雄识别与五路统计完整。测试22+8项通过，接收端验证后已激活，回退在 `lineup-speed-script-20261014/backups/`。
- 实测限制：候选脚本完整运行138.587秒，仍超过120秒；最新正式文件的新会话复测走到脚本，十位识别和三源均ready，取数9.053秒、模型149.933秒（reasoning_tokens=11553），报告与判断文件已落盘。因外层中断导致BrokenPipeError，脚本总计161.076秒，外层未形成最终回复，不能算端到端通过。
- 分批安排：下一批只处理模型统一判断的耗时，每批最多一次完整真实复测；之后单独验收新会话完整回复。功能测试通过不代表质量或两分钟目标完成。正式飞书投递未测；不重启、不主动发消息、不改模型/思考配置、密钥、权限或业务数据。
- 当前证据：现有 `lineup-batch4-report.md`；原始运行 `/tmp/lineup-analysis-hryhffvz/` 和 `/home/ubuntu/.hermes/team/lineup-test/script-route-20261014.*`。项目其他未提交改动保留。

## 2026-10-14 Codex：阵容分析输入去重窄切片

- 仅修改共享正式 `lol-lineup-analysis/scripts/measure_lineup.py` 的执行期模型工作包：固定定义与 24 场景全文不再重复拼入模型动态证据，完整附录仍原样追加到本地结果；新增定向测试，7项通过。
- 显式 `HERMES_HOME=/home/ubuntu/.hermes`、`HERMES_PROFILE=default` 独立复测：154.056秒、2次API、`stop`、无截断；输入 `47694`、输出 `15042`、推理 `10723`、缓存读 `54144`，首轮工具调用后第二轮生成96.855秒；质量字段保留，但仍不达120秒，且首次仍触发 `skill_view`。
- 本批低风险基线：`/tmp/lineup-batch4-baseline`。本地结果：`/home/ubuntu/.hermes/team/lineup-test/batch4-default.*`；独立本地验收，不代表群聊激活。
- 未改模型/思考配置、密钥、权限、网关、数据或人格；未重启、发飞书或提交。工作树原有无关脏改动保持不动。

> 最后更新：2026-10-29 02:01:00.213495 | 更新人：小雪

## 2026-10-14 Codex：阵容分析结构化决策包

- 目标：保留完整证据附录、结论卡、十步正文和 24 场景合同，同时减少模型重复读取与重算。
- 改动：新增 `lol-lineup-analysis/scripts/derive_lineup_features.py`；`prepare_lineup.py` 生成 `decision_packet`；`measure_lineup.py` 的模型工作包改为消费紧凑决策包，完整来源和 24 场景矩阵仍由程序附录原样保留；Skill 正文补充一次统一判断合同。
- 证据：阵容测试 `19 passed`；三个脚本 `py_compile` 通过；健康扫描无 YAML/换行/前置元数据错误。指定阵容模型工作包约 `15547 -> 6173` 字符，减少 `60.3%`；决策包约 `2942` 字符。
- 边界：未改模型、思考档位、Provider、权限、密钥、网关、飞书发送或业务数据；输入缩减不等于端到端已稳定低于 120 秒，线上 `skill_view`/预加载行为仍需单独真实复测。

## 2026-10-13 Codex：阵容分析窄切片（本次明确授权）

- 仅修共享正式阵容Skill及prepare输入语义，增加本地执行器请求/返回观测；6项定向测试通过，程序化附录逐字段无损。
- 明确default真实HERMES_HOME复测167.417秒，单次生成stop，无截断；120秒未达标，正文仍有等级窗口/替代链/风险一致性问题，不能声称质量通过。
- 首轮143.884秒对应会话保存推理24254字、正文5198字；缺原始请求及首轮provider usage，确切耗尽原因未知，不仅凭length归因。
- 无网关重启、飞书发送、模型/思考/权限/密钥修改、数据删除或提交。详见现有sync当前阵容任务段和deliveries/lineup-batch3-report.md；回退基线/tmp/lineup-batch3-baseline。

> 最后更新：2026-10-13 02:00:44.786346 | 更新人：小雪

## 2026-10-11 小白：无畏契约问题到有依据回答 MVP 施工与真实验收

- Goal：让小雪面对无畏契约问题时，优先复用已有 TK/交易 TK/方法，只补必要缺口，分清已有认识与当前交易判断，并能在追问时回指原文。
- Locked decisions：只保留 TK、交易 TK 两类，其余是标签；不修改已有 TK，不自动保存聊天，不扩全库整理、历史留存或新分析系统；无可靠价格不硬给交易价值。
- Current stage：最小施工和测试完成，真实入口部分通过，整体尚未通过验收。已修改专项路由、方法边界与只读候选脚本，未改后端或 TK。
- Verified：共 13 项相关测试通过；2601 条 TK 哈希不变；新话题核心选材、观察项限制、缺价格不硬判及依据追问通过。仍观察到多余会话检索、重复关键词搜索和底稿扩读，不能声称稳定完成。
- Next：修正工具顺序与停止条件，重跑新会话；不扩大范围。
- Blockers：实时赛程/赔率补缺、跨轮持久快照/后台跟踪、观察项量化升级仍未完成；均不属于本次已确认范围。

## 2026-10-11 小白：确认交易 TK 产品骨架与首版 MVP

- Goal：把跨游戏产品最终实体统一为交易 TK，并为首个真实验收切片锁定语义边界。
- Locked decisions：交易 TK 是可复用、可验证的交易认识；资料/事实是依据，比赛是应用上下文，单场记录是当前应用；不自动写入、不以一次输赢改写长期 TK；游戏专属规律不强行跨游戏复用。
- Current stage：已将核心对象、支撑材料/当前应用/正式 TK 三层、首版无畏契约样本和用户可见验收标准写入产品正源。
- Verified：产品文档已完成定向写回；未修改代码、数据库、配置或现有 TK。
- Next：读取工程正源，核对现有无畏契约 TK 的真实入口和读写链路，然后做一次只读真实主路径验收。
- Blockers：当前工作树已有其他改动，尚未清理；飞书连续追问和正式写入边界仍需真实入口验证。

## 2026-10-10 小白续做：跨游戏单场持久化首个代码切片

- Goal：补齐跨游戏单场持久上下文合同并为小雪飞书真实接续验收准备可复验能力。
- Locked decisions：交易 TK 唯一正源；不自动写业务观点；其他游戏不混用 LOL 数据，不承诺实时价格或后台监测。
- Current stage：`match_runs` 现支持 `lol`、`valorant`、`cs2` 的创建、暂停、恢复；非 LOL 生成明确资料缺口，不调用 LOL 赛程适配。
- Verified：本轮重新执行四组合同测试（match_run、match_desk、product_mcp、public_route），66 项通过；新增三游戏同队同时间记录隔离、review 保存、暂停及恢复测试通过（隔离数据库，资料收集使用 mock，不代表外部资料接入）。`npm run build` 成功；运行入口 `127.0.0.1:8880/openapi.json` 返回 HTTP 200、93 条路径。`py_compile` 通过。前端没有 npm test 脚本；全树 diff 检查发现 current-event/api.js 末尾空行，尚未处理。生产写回与真实飞书连续追问未验收。
- Next：从小雪飞书入口做真实连续追问验收，记录模型实际响应。
- Blockers：飞书真实模型行为尚未验收；其他游戏自动赛程、首发、价格、赛果适配仍缺失。工作树已有他人改动，未清理。

## 前端工作台（xiaoxue-web）

### 当前跨模块改造：BO5 阶段适配（按 PROJECT-MAP 用户模块）

| 用户模块 | 状态 | 本轮实际结论 / 证据 |
|---|---|---|
| teams-ts-profile | 已适配 | 常规赛 TS 基线已保留并由 `/api/fundamentals/teams` 提供基线上下文；BO5 仍按系列赛连续更新。 |
| current-event-prep | 已适配 | 真实 8/28 EDG–NIP、TT–IG 已读回 BO5；底稿与近期状态按当前赛事、赛段、赛制读取。 |
| tk-library-and-search | 已适配 | 单场交易 TK 调用现把统一版本理解 `26.16` 传入既有 `version_context` 筛选；未限定版本的长期资料仍可用，旧版本限定资料不会静默混入。资料库阅读/检索本身保持日期可见与原正源。 |
| project-center-and-feedback | 不受影响 | 项目中心不消费比赛赛制或赛前资料，不因 BO5 改造其结构。 |
| stage-review-candidates | 已适配 | 既有阶段/主体档案通过 current-event 读取完整 `match_format`；真实 BO5 research brief 读回 BO5 身份，不另建 BO5 复盘。 |
| market-and-live-records | 已适配 | 盘口记录是交易 TK 的只读兼容投影，不被当作当前赛制事实；当前 BO5 单场调用走版本筛选后的交易 TK。 |
| pure-ten-lineup | 已适配 | 纯十英雄交接不消费系列赛赛果或 BO3/BO5 资料；真实 API 保持只返回既有单局输入合同，版本正源已与当前赛事统一。 |
| version-understanding | 已适配 | 当前赛事与阵容分析已实测读取数据库统一版本理解对象 `shared_version_analysis#229`。 |

| 日期 | 内容 | 状态 | 备注 |
|------|------|------|------|
| 2026-10-12 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力（ts_strength/team_profile/tk/current_match/version_lineup/daily_knowledge/knowledge_automation/attention_config）、后端 18 个 manifest 模块（活跃 14：business_mutations/champion_static/current_event/daily_content/fundamentals/gol_gg/lineup/market_notes/platform/profiles/project_center/team_data/tk_knowledge/version_understanding；disabled 兼容 4：analyst/legacy_trades/research_subjects/weread_bridge 不上树；business_updates/pro_stats 仍为空目录残留）、前端 9 目录 6 活动 loader（teams/current-event/stage-review/tk-library/market-notes/project-center）与 module_tree 37 节点（8 顶级）：8 个 ability_ids 全部被树引用、无无效能力引用、无真实存在却树缺失的用户模块；10-05 后无新增模块目录（current_event 10-10、tk_knowledge 10-04 均为既有模块内部改动），module-contract 无结构变化；entry.page 仍限 teams/event/stage/tk、manual 与 book 链接完整、无重复节点 id。未新增节点、未改任何节点语义；仅升级 content_version 2026-10-05.2 → 2026-10-12.1；备份 .xiaobai-backups/project-center-cron/project-center-content-2026-10-12.json，语义 diff 仅版本行；后端 `_validate_content` 通过、pytest 191 过、mjs 41 过、`/api/project-center/overview` 与 `/modules` 真实读回 content_version=2026-10-12.1、stale=False。 |
| 2026-10-05 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力（ts_strength/team_profile/tk/current_match/version_lineup/daily_knowledge/knowledge_automation/attention_config）、后端 20 目录（18 个 manifest 模块：15 个活跃 business_mutations/champion_static/current_event/daily_content/fundamentals/gol_gg/lineup/market_notes/platform/profiles/project_center/research_subjects/team_data/tk_knowledge/version_understanding；analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录（current-event/daily/lineup-handoff/market-notes/project-center/research-subjects/stage-review/teams/tk-library）/7 loader 与 module_tree 38 节点（8 顶级）：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-19 后无新增模块目录，唯一可观察改动为 tk_knowledge/service.py 未提交内部逻辑（隐式搜索仅匹配 LOL 条目，显式 /api/tk/search 全量，不构成新能力节点）与 Valrorant 规律导入脚本（TK 内容入库，不影响模块结构），module-contract 无结构变化；entry.page 全合法、无内部路径泄漏、无重复节点 id。仅升级 content_version 为 2026-10-05.1，未改任何节点语义；备份至 .xiaobai-backups/project-center-cron/project-center-content-2026-10-05.json，git diff 确认仅版本行变化，JSON 合法（8 顶级/38 节点不变）、tests/test_project_center_content_coverage.py 4 项全过、/api/project-center/overview 真实读回 content_version=2026-10-05.1、stale=False。 |
| 2026-09-19 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 20 目录（15 个活跃模块：business_mutations/champion_static/current_event/daily_content/fundamentals/gol_gg/lineup/market_notes/platform/profiles/project_center/research_subjects/team_data/tk_knowledge/version_understanding；analyst/legacy_trades/weread_bridge 为 disabled 兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录（current-event/daily/lineup-handoff/market-notes/project-center/research-subjects/stage-review/teams/tk-library）与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-18 后无新增模块文件（xaioxue_api/modules 与 src/modules 无 09-18 后 mtime，manifest 最新 mtime 08-26，git 最新提交 08-30）；entry.page 全合法（web 页仅 event/research/stage/teams/tk）、无内部路径泄漏、无重复节点 id。仅升级 content_version 为 2026-09-19.1，未改任何节点语义；写回前已备份至 .xiaobai-backups/project-center-cron/project-center-content-20260919-pre-incr.json，diff 确认仅版本行变化，JSON 合法（8 顶级/38 节点不变）、tests/test_project_center_content_coverage.py 4 项全过、/api/project-center/overview 真实读回 content_version=2026-09-19.1、stale=False。 |
| 2026-09-18 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 活跃模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-17 后无新增模块（唯一 09-17 后变动文件为上次巡检自身写入的 project-center-content.json，git 最新提交 08-30）；entry.page 全合法（web 页仅 event/research/stage/teams/tk）、无内部路径泄漏、无重复节点 id。仅升级 content_version 为 2026-09-18.1，未改任何节点语义；备份至 .xiaobai-backups/project-center-cron/project-center-content-2026-09-18.json，JSON 合法、后端 _validate_content 通过、tests/test_project_center_content_coverage.py 4 项全过、/api/project-center/overview 与 /modules 真实读回 content_version=2026-09-18.1、stale=False。 |
| 2026-09-17 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 活跃模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-16 后无新增模块文件（manifest 与模块目录无新 mtime）；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-09-17.1，未改任何节点语义；tests/test_project_center_content_coverage.py 4 项全过，/api/project-center/overview 真实读回 content_version=2026-09-17.1、stale=False，写回前已备份至 .xiaobai-backups/project-center-cron/。 |
| 2026-09-16 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 活跃模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-15 后无新增模块文件（find 无新 mtime）；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-09-16.1，未改任何节点语义；tests/test_project_center_content_coverage.py 4 项全过，/api/project-center/modules 真实读回 content_version=2026-09-16.1、stale=False。 |
| 2026-09-15 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 活跃模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-12 后无新增模块（最新 manifest mtime 08-26，git 最新提交 08-30，本轮仅 09-12 巡检自身写入的 project-center-content.json 在工作区有变动，module-contract 无结构变化）；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-09-15.1，未改任何节点语义；后端 _validate_content 通过，tests/test_project_center_content_coverage.py 4 项全过，/api/project-center/overview 与 /modules 真实读回 content_version=2026-09-15.1、stale=False、38 节点。 |
| 2026-09-12 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 活跃模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-11 后无新增模块（git 最新提交 08-30，仅有既有业务改动未提交），业务变更（business-mutations）节点已于 09-10 补入并在树中确认存在；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-09-12.1，未改任何节点语义；JSON 校验通过，/api/project-center/overview 与 /modules 真实读回 content_version=2026-09-12.1、stale=False、38 节点。附带发现：tests/test_project_module_contract.py 的 test_formal_docs_and_root_skill_point_to_the_same_model_guide 失败（小雪 .agents/skills/小雪/SKILL.md 自 09-06 起缺少「小雪项目总使用说明.md」引用），与模块树无关、非本次改动引入，待单独处理。 |
| 2026-09-11 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 18 个 manifest 模块（analyst/legacy_trades/weread_bridge 为兼容不上树，business_updates/pro_stats 仍为空目录残留）、前端 9 目录/7 loader 与 module_tree 38 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-10 后无新增模块（后端 manifest 最新 mtime 08-26，git 最新提交 08-30，module-contract 仅 TK 措辞/工具口径更新无结构变化）；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-09-11.1，未改任何节点语义；7 个项目中心测试全过，/api/project-center/overview 真实读回 content_version=2026-09-11.1、stale=False。 |
| 2026-09-10 | 项目中心模块树增量核对（cron） | ✅ 已修正 1 处 | 对照合同 8 能力、后端活跃模块、前端 9 目录/7 loader 与 module_tree 38 节点：发现 09-04 新增的 business_mutations（业务变更，写正源统一合同，/api/health healthy，MCP 工具 xiaoxue_apply_business_mutation）此前未被树覆盖；在 knowledge-and-data 下新增「业务变更与正源更新」节点（ability_ids=team_profile/ts_strength，current_capability 标待完善），不动已有节点语义与分组；content_version → 2026-09-10.1；后端 _validate_content 通过，/api/project-center/modules 真实读回 38 节点含新节点，JSON 合法。 |
| 2026-09-05 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 20 目录（仅 15 个 manifest 活跃模块；business_updates/pro_stats 仍为空目录残留，analyst/legacy_trades/weread_bridge 为兼容 disabled 不上树）、前端 9 目录/7 loader、module-catalog 与 src/main.js 页面（teams/event/stage/research/tk/project + market 隐藏）对照 module_tree 37 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-04 后唯一源码改动为 business_mutations/service.py（2026-09-04 15:24 废弃 Wiki 队伍画像写入、DB team_profiles 为唯一正源，属既有模块内部收敛，不改树）；entry.page 全合法、无内部路径泄漏；JSON 校验通过（37 节点/8 顶级不变）。仅升级 content_version 为 2026-09-05.1，未改任何节点语义。 |
| 2026-09-03 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 20 目录（18 个 manifest 可加载模块；business_updates/pro_stats 仍为空目录残留，analyst/legacy_trades/weread_bridge 为兼容 disabled 不上树）、前端 9 目录/7 loader、module-catalog 与 module_tree 37 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；08-31 后无新增模块目录（唯一未跟踪文件为 scripts/migrate_tk_to_tag_model.py，module-contract 仅 TK 措辞/工具口径更新无结构变化）；entry.page 全合法、无内部路径泄漏；`/api/project-center/overview` 真实入口 200 读回正常。仅升级 content_version 为 2026-09-03.1，未改任何节点语义，JSON 校验通过（37 节点/8 顶级不变）。 |
| 2026-09-04 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 20 目录（18 个 manifest 可加载模块；business_updates/pro_stats 仍为空目录残留，analyst/legacy_trades/weread_bridge 为兼容 disabled 不上树）、前端 9 目录/7 loader、module-catalog 与 module_tree 37 节点：8 个 ability_ids 全部被树引用、无无效能力、无真实存在却树缺失的用户模块；09-03 后工作区无任何源码或配置改动（唯一 09-03 后改动的两个文件为上次巡检自身写入的 progress.md 与 project-center-content.json），current_event 为既有模块内部迭代，module-contract 仅 TK 措辞/工具口径更新无结构变化；entry.page 全合法、无内部路径泄漏；`/api/project-center/overview`/`modules` 真实入口读回 ok（37 节点、stale=False）。无真实漂移，未改任何节点语义，仅升级 content_version 为 2026-09-04.1，JSON 校验通过。 |
| 2026-08-31 | 项目中心模块树增量核对（cron） | ✅ 无漂移 | 逐项对照合同 8 能力、后端 20 目录（18 个 manifest 可加载模块；business_updates/pro_stats 仍为空目录残留，analyst/legacy_trades/weread_bridge 为兼容 disabled 不上树）、前端 9 目录/7 loader、module-catalog 与 module_tree 37 节点：8 个 ability_ids 全部被树引用、无无效能力、无缺失用户模块；08-30 后无新增模块目录，current_event 为既有模块内部迭代；entry.page 全合法、无内部路径泄漏。仅升级 content_version 为 2026-08-31.1，未改任何节点语义，JSON 校验通过。 |
| 2026-08-30 | 项目中心模块树增量核对（cron） | ✅ 已验证 | 逐项对照后端 18 个 manifest 可加载模块、前端 9 目录/7 loader、合同 8 能力与 module_tree 37 节点；无真实存在但树缺失的用户模块，analyst/legacy_trades/weread_bridge 仍为兼容/支撑不补节点，pro_stats/business_updates 为空目录非真实模块。仅升级 `project-center-content.json` content_version 为 2026-08-30.1，未改任何节点语义；`/api/project-center/overview` 真实入口读回正常。 |
| 2026-08-25 | BO5 阶段数据与赛前底稿适配 | ✅ 已验证 | ScoreGG 按每场 `game_count` 写入 BO3/BO5；8/26 起 LPL/LCK 淘汰赛赛程已读回 BO5。TS 保留 22 队常规赛基线，BO5 仍按一个系列赛更新并区分 3:0/3:1/3:2；当前赛事底稿显示 BO5 资料语义。近期状态现按赛事、赛段、赛制一致读取：BO3 只读当前赛段 BO3，BO5 只读当前赛段 BO5；无样本明确为 0，不混入旧赛段。 |
| 2026-06 v6 | 对话驱动布局重构：指令栏为主角，画像从SKILL.md全量展开 | ✅ 完成 | 访问 42.193.177.127:5173 |
| 2026-06 v5 | 三维面板：三列dim卡片+战术笔记，inline编辑Ctrl+S写回DB | ✅ 完成 | 队伍旧版本字段后续迁移至队伍 TK |
| 2026-06 v5 | TK面板：内嵌搜索+展开全文+编辑器overlay+删除，过滤80字空壳 | ✅ 完成 | |
| 2026-06 v5 | 横向对比弹窗：双栏画像+三维对比 | ✅ 完成 | 钧钧说用处不大 |
| 2026-06 v5 | 画像栏可折叠（◀/▶按钮，44px），TK展开/收起动画 | ✅ 完成 | |
| 2026-06 v5 | 24支LPL+LCK队伍数据接入 | ✅ 完成 | |
| 2026-06 v6 | 📊概念关系图：新标签页打开120节点力导向图 | ✅ 完成 | |
| 2026-06 v6 | 分析师面板：DeepSeek API并行跑双skill框架 | ✅ 完成 | 仅飞书chat内调用，web不接入 |
| 2026-07-03 | 运维增强：新增 `/api/health`，`vibe-status` 接入工作台/API/Vite/knowledge-rag 检查，并建立 git 稳定基线 | ✅ 完成 | 本地 Codex 代小白执行；后续改动可用 git diff/commit 管理 |
| 2026-07-06 | 盘口页收敛为手写判断工作区，P0/P1 收口验证完成 | ✅ 完成 | `/api/market-notes` 为主链路；不自动交易、不自动生成方向 |
| 2026-07-07 | 运维与项目收口：磁盘降到 85% 以下，`vibe-status` 增加磁盘分级提示，`/api/health` 纳入盘口表、memory-bank、磁盘检查 | ✅ 完成 | 当前边界：健康检查只读；盘口记录仍只走 `/api/market-notes` |
| 2026-07-07 | 队伍画像扩展为 Wiki/SKILL/数据库三层降级 | ✅ 完成 | 无手工画像时，用 teams/rosters/team_3d_data/msi_ts_seed 生成只读兜底画像；不伪造人工判断 |
| 2026-07-07 | 版本理解与队伍资料边界收口 | ✅ 完成 | 全局只保留版本理解；旧队伍版本字段不再作为栏目 |
| 2026-07-08 | 赛前交易判断日报第一阶段：接入交易 TK 标签链路 | ✅ 完成 | 交易 TK 归队伍 TK；新增 `/api/team-trading-notes`、`/api/team-trading-notes/from-text`、`/api/pre-match-trading-report`、今日内容 `trading_report` 入口和 `scripts/build_pre_match_trading_report.py`；不恢复 `tk_library`，不接旧 `/api/trades` |
| 2026-07-08 | 赛前交易判断层嵌入 LOL 日报生成流水线 | ✅ 完成 | 根治为后加工架构：`build_daily_report.py` 只生成基础日报并禁止输出交易 marker；cron 完成基础日报和赛后复盘后，运行 `postprocess_daily_report.py`/`inject_pre_match_trading_layer.py` 只插入“赛前交易判断层”，用幂等与交易层外 hash 验证保护其它内容 |
| 2026-07-09 | 前端模块小分层：队伍资料=长期依据，今日内容=交易前入口，盘口记录=交易时手写记录，阵容八步法=问小雪 | ✅ 完成 | 不重做 UI；盘口记录保存到 `market_notes`，BP 阵容只复制模板触发 `lol-lineup-analysis`，复盘回溯后续从原始记录扩展 |
| 2026-07-09 | 盘口记录第二阶段：结果字段与轻量回溯筛选，单场入口弱化为 BP 后问小雪 | ✅ 完成 | 结果写入 `review` 固定行 `结果：...`，不改数据库结构；列表本地筛选最近 7 天 / 30 天 / 全部最近记录、关键词和结果；前端只整理 BP 文本，不承载八步法本体 |
| 2026-07-09 | TK 搜索链路修复：当月 bilibili TK 不再被旧 wechat 文件压住 | ✅ 完成 | `/api/tk/search` 从 RAG 原文 frontmatter 解析日期，本地 TK fallback 全量候选后按 `created`/mtime 排序；修复单行 `【结论】` 文件导致 500 的问题 |
| 2026-07-10 | 历史：旧 Codex 主控口径曾接入小雪 memory-bank | ✅ 已被替代 | 这是历史过程记录，不是当前规则；当前以 `TEAM_OPERATING_GUIDE.md` 为准：小雪、小白均具备能力，小白因模型与开发类 Skill 配置通常优先承担开发维护，Codex 仅为小白后台施工工具 |
| 2026-07-10 | 历史：Codex 直接主控口径曾替代旧小白主控口径 | ✅ 已被替代 | 这是历史过程记录，不是当前规则；当前以小白优先开发维护、业务能力回到小雪正式入口的口径为准 |
| 2026-07-11 | Agent Reach 接入小雪搜索路由 | ✅ 完成 | 内部 DB/Wiki/TK 优先；最新公告、网页和视频发现走 Agent Reach；正式日报舆情继续走冻结豆包链路；未改前端、数据库或 cron |
| 2026-07-12 | Fixed/Hardcoded Workflow 收口 | ✅ 完成 | 配置注册表、BP 八步法输入契约、market_notes 复盘预览/确认写回、数据就绪 manifest、日报发布门禁、知识导入 manifest 和 no-agent 巡检已落地；7 月 8 日后处理链仅保留历史，7 月 10 日 v2 已替代 |
| 2026-07-18 | 小雪工作台 2.0.0 模块化版本 | ✅ 完成 | 前后端按模块拆分，表现层/业务层/数据层分离，模块通过公开接口通信；日报按钧钧决定保持手动暂停 |
| 2026-07-13 | 无比赛日真实空态与前后台边界修正 | ✅ 已验证 | 今日赛程为空时只显示“今日无比赛”，不再保留旧 MSI 示例或放前端复盘入口；前端负责赛前内容和原始记录，赛后复盘回到小雪对话 |
| 2026-07-14 | 前端收口为“今日赛前 / 当前赛事 / 队伍资料 / TK资料库”四个主页面 | ✅ 已验证 | TK 独立按时间阅读，正文优先、日期可见、全文不截断；赛程退出前端，盘口记录仍为辅助入口，赛后复盘回小雪对话 |
| 2026-07-18 | 工作台模块隔离第一阶段：保留现有入口，盘口记录与阵容交接后端独立，前端按模块目录装载 | ✅ 已验证 | 单个模块配置损坏不会阻断其他模块；健康状态分为可用/待修/暂未启用；当前每日准备因当天 readiness 缺失标为待修，其余主模块继续使用 |
| 2026-07-18 | 工作台完成真实模块化与三层隔离 | ✅ 已验证 | 后端入口只负责创建应用，各功能按表现/业务/数据三层拆分并只通过公开接口协作；前端六个功能模块各自拥有界面/业务/数据/公开接口，旧内联处理和主入口功能实现已移除；单模块故障页面验证通过 |
| 2026-07-18 | 工作台按最终产品边界收缩为长期 LOL 资料本 | ✅ 已验证 | 主导航只保留队伍资料、当前赛事、TK资料库；默认先看全部队伍；今日赛前和 BP 入口已移出；盘口记录保留为隐藏辅助；当前赛事读取唯一正式预案，不存在时明确显示尚未制定 |
| 2026-07-19 | 真实词表统一与旧队伍版本字段迁移 | ✅ 已验证 | 30 条有效旧字段迁入队伍 TK，测试字段跳过；队伍页只保留画像/三维/队伍 TK；交易 TK 在队内和日报按比赛优先显示；盘口记录、TS 表、日报等名称统一 |
| 2026-07-18 | 每日日报运行状态按钧钧决定标为主动暂停 | ⏸️ 用户暂停 | 不再把 readiness 缺失显示成日报故障；待剩余日报模块修好并验收后，再由钧钧决定是否恢复自动运行 |
| 2026-07-19 | TK 检索入口迁移到 MemPalace | ✅ 已验证 | 714 份 Wiki TK 已进入 `xiaoxue-tk` 分区；新增本机 `8770` 适配入口；工作台 `/api/tk/search` 已切换；旧 8768 服务、索引、日志和专属环境已删除；真实 BLG/纪律性搜索返回 200 |
| 2026-07-31 | 单场交易工作流第一段 | ✅ 已验证 | 当前赛事可从真实赛程点进单场底稿，统一呈现 TS、首发、三维和交易 TK；小雪四行回复可留存为当前判断，首发/BP/盘口等具体变化独立追加并刷新读回；新增 `match_workspaces`/`match_observations`，数据库先备份，旧 `market_notes` 保持不变 |
| 2026-07-31 | 快速沟通 / 深度整理双流程 | ✅ 运行态已启用并回归 | 时间少时直接在 HarmonyOS/飞书让小雪逐步引导单场判断；时间多时用工作台横向对比队伍、TS、定性画像、定量字段和 TK，再把确认内容留存；前端不替代对话入口。Hermes default 已放行 19 个小雪产品工具；新飞书来源会话用 HLE–DK 真实 ScoreGG 导入记录验证：首轮只给四行依据账本，封存赛果，指出首发/过时资料的具体改法；不调用网页、文件或终端。 |
| 2026-07-31 | 单场虚拟推演与赛后解封 | ✅ 已验证 | 新增 `match_runs`、`match_run_facts`、`match_run_revisions`。同一队伍/日期/时间即使赛事名称写法不同也只归一条流程；ScoreGG 证据按赛前/赛后分视图，`pre` 不返回赢家或比分，只有明确解封后才能读赛果。工作台已显示依据状态和“开始赛前模拟”入口；数据库和 Hermes 配置已各自留备份。 |
| 2026-08-01 | 统一交易 TK 与单场调用链 | ✅ 已验证并启用 | 所有长期定性规律共用原 TK/Wiki 正源，按全局、赛区、队伍、选手归类；原队伍 `type=trading_note` 保留且以只读兼容项进入统一列表和单场调用，不复制。已整理写入 4 条钧钧原有阵容/赛区规律，均为待验证；HLE“虐菜大人头”旧备注保持已确认。打开具体比赛默认停在单场底稿，也可直接停在钧钧点名模块；需要时才带回相关 TK，待验证只提醒，采用和确认仍由钧钧决定。前端阶段整理和小雪新会话均已读回 5 条内容。 |
| 2026-08-01 | 可组合工作流与状态化引导 | ✅ 已验证并启用 | 总纲明确日报默认入口不等于强制链；单场线程保存比赛、模式、当前位置和明确留存内容，可随时进入、暂停、换场、恢复或切换模块。切换不写判断，不再返回“下一步”指令；虚拟回放仅用于调试。 |

| 2026-08-19 | 项目 AI 可读性优化（根因：不是文档归并不够，是缺"全貌导航"） | ✅ 已完成 | ① 新增 `docs/PROJECT-MAP.md`（项目全貌地图：分块/正源/改动影响面/文档权威等级）；② AGENTS.md 顶部加"改前必读强制协议"，指向 PROJECT-MAP；③ 历史文档（SPEC、1.0、2.0、README、交易方法重组执行）移入 `docs/archive/`，清空默认阅读面。核心思想：薄入口看全貌 + 按需钻取 + 契约管影响面 + 语义按需取(MemPalace)，不是把文档合并成一个长文件 |
| 2026-08-19 | 版本理解正源 → 前端展示链路 | ✅ 已验证 | 当前赛事页顶部从 `shared_version_analysis#229` 经 `/api/version-understanding/global/current` 读取统一正文；项目中心只保留开发状态。真实页面已显示 8-19 精简版及更新时间，正文按标题、列表和段落阅读，不暴露 Markdown 符号；以后小雪写回同一版本正源，刷新当前赛事页即可同步显示。 |
| 2026-08-19 | 小雪英雄知识独立化与阵容输入容错 | ✅ 已验证 | 新建独立 `lol-hero-knowledge`：全英雄中文名册与常用别名成为小雪日常英雄常识，单英雄/对位/技能/机制不再依赖阵容场景；阵容分析先加载英雄知识再做十人推演。英雄工具只用于错字、歧义和机制核对；补齐滑板鞋、小火龙、龙女、大树、瑞尔、沙弥拉、女枪、猴子等别名，`16.16` 可命中 Data Dragon 的 `16.16.1` 快照，区分名称不存在、版本快照缺失和快照不完整。52 个相关测试通过，小雪 default profile 已发现并启用新 Skill。 |
| 2026-08-20 | 飞书阵容分析路由恢复 | ✅ 已验证 | 小雪飞书新会话自动加载日常根 Skill；十英雄请求先进入 `lol-lineup-analysis`。队名只作蓝红方标签，不再自动扩成赛程、赛果、队伍画像、TS、TK、盘口或外部新闻调研。真实同输入复验只加载根 Skill、阵容 Skill、英雄知识、版本正源和歧义英雄本地快照，无队伍/赛程/外部搜索调用。 |
| 2026-08-20 | 小雪 Skill 分层重做 | ✅ 已验证 | 固定底座只保留两层：默认自动加载 `xiaoxue`，飞书默认知识入口增加 `lol-hero-knowledge`。`lol-lineup-analysis` 属于分析方法，`junjun-trading-system` 属于交易方法，`agent-reach` 属于资料工具，`cs2-betting-analysis` 属于其他项目；它们及版本、队伍、日报、导入、复盘、自动化均保持可用但按需加载，不再混称“固定核心能力”。 |
| 2026-08-20 | 电竞博彩基础知识 Skill | ✅ 已验证 | 新增共享 `esports-betting-basics`，覆盖独赢、系列赛/单图让分、大小分统计单位、赔率与隐含概率、庄家利润、盘口变化、走盘/半赢半输、串关和电竞特有误区；与交易系统、LOL阵容、CS2专项分层。真实新会话问“BO3让1.5”时首个工具动作正确加载本 Skill，仅 1 次 Skill 调用，无比赛资料或外部搜索。 |
|| 2026-08-21 | 阵容英雄曲线正源补全 | ✅ 已验证 | `hero-power-curve.md` 定为完整稳定机制常识正源：当前静态库 173/173 英雄全覆盖（177 条位置行，含跨位置），每行有前/中/后期与机制理由；“后期强 / 后期核 / 功能后期”口径固定。`lol-lineup-analysis` 已强制先读英雄知识与完整曲线表，再读版本理解做版本修正；不得临场凭记忆补曲线，也不建立外部时长胜率管道。覆盖校验和瑞兹/凯尔/金克丝/李青回归通过。 |
|| 2026-08-22 | TS 综合实力/发挥稳定性展示层重做 | ✅ 已验证 | 保留底表 TS 计算；稳定性改为赛前预期兑现度 65% + 被爆冷抵抗力 35%，样本向 50 收缩；展示层对综合实力和稳定性做单调拉差，60 分强弱分界与 50 分稳定性中性线保持；数据库已备份至 `/tmp/lol_data_ts_backups/英雄联盟数据库.before-display-contrast-20260822_091354.db`，19 个 TS/赛事测试通过，dry-run 与数据库读回/API 已验证。
|| 2026-08-22 | TS 走势阶段合同与有向指标 | ✅ 已验证 | `trend`/`momentum` 改为 -100～+100 有向信号：趋势=当前斜率，势头=斜率变化；正负组合解释上涨加速、上涨钝化、下跌加速、下跌钝化和反转观察。分组折扣先进入赛前预期；数据库已备份至 `/tmp/lol_data_ts_backups/英雄联盟数据库.before-signed-trend-momentum-20260822_100807.db`，dry-run、19 个测试、字段核对、数据库/API 读回通过；TS 治理与周期 Skill 已同步指标目的性合同。
|| 2026-08-22 | TS 势头阶段标签上线 | ✅ 已验证 | 趋势前台保留 `+/-` 数字；势头从孤立的 `+/-` 数值改为“上涨加速/上涨钝化/下跌加速/下跌钝化/启动/延续观察”标签和箭头，底层数值仍供周期判断。真实工作台队伍资料页已读到 BLG“上涨加速”、NIP“上涨加速”、LNG“下跌钝化”、JDG“下跌启动”；日报同步输出阶段标签。周期 Skill 的方法论扩展待钧钧后续讨论后再改。
|| 2026-08-22 | 周期 Skill 收口为总控入口 | ✅ 已验证 | `lol-tournament-cycle-analysis` 现在是“周期 Skill / 今天全部比赛”的唯一日常入口；当天赛程先筛参赛队，再按需消费赛区重点池和单队复核，命中才在对应场次补“周期提示”。`lol-region-cycle-scan` 与 `lol-team-cycle-review` 明确为内部助手，不再提供平级中文入口；TS 字段核对、API 读回、后端编译和前端构建通过。 |
|| 2026-08-23 | 项目中心模块树同步巡检（cron） | ✅ 无漂移 | 用 module-contract（8 能力模块）、xiaoxue_api/modules（17 后端模块）、src/modules（9 前端目录）、module-catalog.js（7 个活动 loader）与 module_tree 逐一核对：8 个 ability_ids 全部被树引用、无无效能力 ID、树 entry.page 全部对应真实页面（teams/event/stage/research/tk/project）；analyst 为 disabled 旧分析兼容接口，已由「旧入口归档与兼容边界」节点覆盖，不补新节点。未改 project-center-content.json，content_version 维持 2026-08-22.1。 |
58||| 2026-08-23 | 队伍 TK 与资料库一致性、删除回读修复 | ✅ 已验证 | 队伍资料页选队后不再走最多 15 条的语义搜索，改为分页读取同一 `/api/tk/library?team=` 正源的完整队伍 TK；删除后同时刷新队伍快捷视图与已打开的资料库，并展示具体失败原因。真实 BLG 页面验收：128 条（含临时项）完整加载；点删除后浏览器 DELETE 成功，后端读回 404、页面即时消失。 |
59||| 2026-08-23 | TK 技术残渣清理与写入治理 | ✅ 已验证 | 56 个内容仅为 `@/tmp/...` 的无正文临时指针已移到可恢复技术归档，不再进入 TK 正源或索引。资料读取、搜索和新建/编辑/口述写入统一剔除代码块、内部路径和日志残留；交易 TK 保留业务正文但不再显示 YAML。真实 API 与页面全文验收：旧交易/压缩资料无代码和本机路径；三类技术关键词搜索为 0；新写入含代码和路径时仅保留可读判断并读回。 |
| 2026-08-23 | TK资料库笔记式管理界面 | ✅ 已验证 | 资料库改为检索工具栏、时间分组列表和同页阅读面；桌面同时保留列表与正文，手机切为“返回资料列表”的单栏阅读。新建、编辑和删除只在资料库管理面提供，编辑已带入全文，删除仍先确认；队伍页保留快捷阅读。稳定入口以 BLG 实例检索并读到 366 字正文，1440px/390px 无横向溢出，截图留存 `/tmp/tk-library-{desktop,mobile}.png`。 |
| 2026-08-23 | 队伍资料速览收紧 | ✅ 已验证 | 选中队伍后默认只显示最新两条可读资料与总数；可在卡内展开完整列表（独立滚动）或跳转 TK资料库。BLG 真实页面读到 126 条，TS 卡与速览卡同屏；全文仍在卡内，可返回且不遮住 TS 表。截图：`/tmp/xiaoxue-team-tk-after.png`。 |
| 2026-08-24 | 项目中心模块树同步巡检（cron） | ✅ 已修正 1 处 | 用 module-contract（8 能力模块）、xiaoxue_api/modules（17 带 manifest 后端模块；business_updates/pro_stats 为空目录残留不算模块）、src/modules（9 前端目录）与 module_tree 逐一核对：8 个 ability_ids 全部被树引用、无无效能力 ID、树 entry.page 全部对应真实页面（teams/event/stage/research/tk/project）、无缺失模块；8-23 以来的未提交改动均为既有模块内部迭代（TK 内容清洗、英雄别名补充、TK 资料库 UI），不产生新用户模块，不补新节点。发现并修复 1 处不一致：research-subjects 节点 engineering_details.source 泄漏内部路径 `/api/research`，违反前台卫生测试（test_default_content_does_not_leak_implementation_paths_or_retired_primary_routes），已改为「主体档案后端模块与前端主体档案页」；content_version 2026-08-22.1 → 2026-08-24.1。4 个覆盖测试全过，真实 API `/api/project-center/modules` 读回 34 节点、status ok、无 /api/ 泄漏。 |

## 日报管道（daily-report cron）

| 日期 | 内容 | 状态 | 备注 |
|------|------|------|------|
| 2026-06 v17 | anysearch搜索+中文NLP修复+焦点战100+评论+BP分析框架 | ✅ 完成 | 每日08:00自动执行 |
| v14 | 源码重构：1901行→511行，从14层try/fallback→1道闸门 | ✅ 完成 | |

## 数据库与自动化

| 日期 | 内容 | 状态 | 备注 |
|------|------|------|------|
| 持续 | ScoreGG数据导入管道 | ✅ 运行中 | cron自动执行 |
| 持续 | B站/公众号知识导入 | ✅ 运行中 | 订阅UP主自动拉取 |
| 2026-07-12 | 数据库刷新与 TS 合并为数据就绪任务 | ✅ 已切换 | `9b8cd8f43d39` 05:30 运行 `xiaoxue_data_readiness.py`；独立 TS 任务 `7e6e1cf65059` 已暂停；日报发布前必须读取当天 readiness manifest |
| 2026-07-12 | 每日巡检 no-agent 路径修复 | ✅ 已切换 | `355886f0ca6b` 改为允许目录内 `xiaoxue_daily_inspection.py`；不再被脚本目录安全策略拦截 |
| 2026-06 | 8个cron job全量收紧：工具懒加载，token省40-60% | ✅ 完成 | 下次新会话生效 |
| 2026-06 | 三维数据手动维护 | ⏸️ 暂停 | 钧钧说"现在先不弄" |
| 2026-08-25 | 项目中心模块树增量对齐：补「关注范围与赛事配置」节点（attention_config 能力此前只有引用无节点），content_version → 2026-08-25.1 | ✅ 完成 | 只增不改：不动已有节点语义/分组；`/api/project-center/modules` 真实读回 35 节点、新增节点可见；schema 校验通过 |
| 2026-08-26 | 项目中心模块树增量对齐（cron）：补「Gol.gg 逐局事实核对」节点（gol_gg 后端模块真实存在、effect=live_search，此前树上无对应节点），content_version → 2026-08-26.1 | ✅ 完成 | 用 module-contract（8 能力）、xiaoxue_api/modules（20 目录，business_updates/pro_stats 为空残留不算）、src/modules（9 前端目录）逐一核对：8 个 ability_ids 全部被树引用、前端 9 目录全部有对应节点、champion_static/platform/business_mutations/weread_bridge/legacy_trades/market_notes/analyst 均已被现有节点语义覆盖（版本/阵容底座、健康后台、写正源机制、导入登录、兼容归档、盘口只读投影、disabled）；只增不改不动已有节点；git diff 仅 +29/-1；前端 view.js 动态渲染 children 无兼容风险 |
| 2026-08-27 | 项目中心模块树增量对齐（cron）：补「英雄静态资料查询」节点（champion_static 后端模块真实存在且 /api/health 为 healthy，经 MCP 工具 xiaoxue_get_champion_context 供用户查英雄技能/属性/版本资料，此前树上无对应节点；8/22–8/26 历次巡检曾将其归为支撑层，本次按“真实存在但树上缺失”补入并标为待完善），content_version → 2026-08-27.1 | ✅ 完成 | 用 module-contract（8 能力）、xiaoxue_api/modules（15 活跃；analyst/legacy_trades/weread_bridge 为 disabled；pro_stats/business_updates 为空目录残留）、src/modules（9 目录，daily/lineup-handoff 未注册为页面）、module-catalog.js（7 个活动 loader）逐一核对：8 个 ability_ids 全部被树引用、无无效能力 ID、7 个前端 loader 全部有对应节点、其余 14 个活跃后端模块已有节点覆盖；只增不改，未动已有节点语义/分组；4 个覆盖测试全过、无 /api/ 泄漏；/api/project-center/modules 真实读回 37 节点、content_version 2026-08-27.1、新节点 runtime healthy |
| 2026-08-28 | 项目中心模块树同步巡检（cron） | ✅ 无漂移 | 用 module-contract（8 能力）、xiaoxue_api/modules（20 目录，business_updates/pro_stats 为空残留不算模块；analyst/legacy_trades/weread_bridge 为 disabled 兼容，已由「旧入口归档与兼容边界」等节点语义覆盖）、src/modules（9 前端目录）、module-catalog.js（7 个活动 loader）与 module_tree 逐项脚本核对：37 节点无重复 ID；8 个 ability_ids 全部被树引用、无无效能力 ID、无缺失引用；树 entry.page 全部对应真实页面（teams/event/stage/research/tk/project）；无 /api/ 实现路径泄漏；9 个前端目录与 7 个 loader 全部有对应节点；15 个活跃后端模块全部已有节点覆盖；8/27 巡检后无新增模块文件。未改 project-center-content.json，content_version 维持 2026-08-27.1 |
| 2026-08-29 | 项目中心模块树同步巡检（cron） | ✅ 无漂移 | 用 module-contract（8 能力模块）、xiaoxue_api/modules（20 目录，business_updates/pro_stats 为空残留不算模块；analyst/legacy_trades/weread_bridge 为 disabled 兼容，已由「旧入口归档与兼容边界」等节点语义覆盖）、src/modules（9 个目录）、module-catalog.js（7 个活动 loader）与 module_tree 逐项脚本核对：37 节点无重复 ID；8 个 ability_ids 全部被树引用、无无效能力 ID、无缺失引用；树 entry.page 全部对应真实页面（teams/event/stage/research/tk/project）；无 /api/ 实现路径泄漏；9 个前端目录与 7 个 loader 全部有对应节点；15 个活跃后端模块全部已有节点覆盖；8-28 核对后无新增模块文件（模块目录无 08-27 后源码改动，git 最后 commit 为 2026-08-26）。未改 project-center-content.json，content_version 维持 2026-08-27.1 |
|| 2026-08-30 | LOL 赛事常识底座与 TK 写入边界 | ✅ 已验证 | 新增 `lol-competition-basics` 并配置为小雪飞书默认加载；小雪入口对所有 LOL 对话先进入赛事常识，再叠加英雄/BP/盘口/赛前等专项。TK 仅接受明确“TK”指令，“记住/记一下/帮我记着”不写入。MCP 工具标题/说明、项目合同和项目中心示例同步修正；45 项 MCP 回归、Python/JSON 校验、前端构建、项目中心 API、Feishu Skill guard 均通过，默认网关已重启并加载新 MCP 子进程。 |
|| 2026-08-29 | 项目地图与前端项目中心更新 | ✅ 已验证 | 程序化核对 8 个能力、37 个模块树节点、9 个前端目录、7 个活动 loader、6 个主页面无漂移；`PROJECT-MAP.md` 增加当前事实快照，项目中心内容版本更新为 `2026-08-29.1`；首屏增加“从这里开始”三条入口，真实 API、7 项内容/API 测试、前端构建、桌面/移动渲染和 `#teams` 跳转通过。截图：`/tmp/xiaoxue-project-center-desktop.png`、`/tmp/xiaoxue-project-center-mobile.png`。 |

## 2026-08-30｜每日赛前交易方案第一切片

- 状态：已验证（代码/API/前端构建）；真实飞书入口仍待常驻服务重载后验收。
- 结果：当前赛事每日列表读取比赛时自动生成每场方案；方案从现有交易 TK 动态合成，无赔率依赖；新增本场交易方案存储，保留自动层、人工补充层和开赛冻结层。
- 前端：当前赛事单场显示队伍做多/做空、人头做大/做小、时间做大/做小；赛前可补充“人头大/时间大/队伍做多”等本场判断。
- 边界：本场补充不回写长期交易 TK；开赛后方案自动锁定；赛中不要求记录。
- 验证：`python3 -m py_compile` 通过；`npm run build` 通过；相关 current-event/MCP 回归 71 项通过；当天 2 场自动建立方案记录并读回。公共路由合同仍有 2 项既有 `/api/trading-tk` 写入口冲突，非本次新增链路造成。
- 风险：当前“本场补充”以自然文本追加，尚未提供逐条删除/编辑；完整赛后自动归因仍需下一切片接入。

## 2026-08-30｜当前赛事页面信息层级与可读性

- 状态：✅ 已验证（真实稳定入口桌面与移动端）。
- 结果：当天赛程成为页面主视图；此前打开过的单场记录收为默认折叠的「最近查看」，明确标注为历史内容，不再与当天赛事混在一起。
- 改动：`index.html` 重做当前赛事区的层级、赛事卡、详情排版、字号、对比度与移动端布局；`src/modules/current-event/view.js` 调整赛事/历史卡和详情的用户可读文案，不改任何后端、数据或写入动作。
- 验证：`npm run build` 通过；稳定入口 `http://127.0.0.1:8880/#event` 的 headless 实测读到 2 场当天赛事。1440×900 / 390×844 均验证详情标题 27px / 23px、元数据 15px、正文 15px，无横向溢出、无全屏遮罩，赛前方案控件仍存在。截图：`/tmp/xiaobai-current-event-desktop.png`、`/tmp/xiaobai-current-event-mobile.png`。
- 边界：历史单场数据没有删除或过滤；它们是既有临时记录，仅被降为次级、可展开的查看区。

## 2026-09-30｜德杯+世界赛适配（运行模式切换）

- 状态：✅ 已验证（lol_data 全链路 + xiaoxue-web 构建/API/测试）。
- 结果：小雪项目从「LPL/LCK 第三赛段」切到「德杯 + S16 世界赛」：队伍关注只保留两赛事参赛队（LPL/LCK 14 队核心、外赛区 12 队常规、LNG/WBG 退回基础）；德杯与 S16 世界赛完成赛事登记；赛制链路支持 BO1（ScoreGG game_count=1→BO1）；德杯 13 条赛程已导入；当前赛事卡与前端硬编码全部切新；旧「第三赛段」文案清零。
- 改动：`lol_data/config/competition_registry.json`（+DEMACIA-2026、WORLDS-2026）、`config/team_priority.json`（v2026-09-30）、`scripts/scoregg_refresh.py`（BO1）、`config/team_aliases.json`（+11 队别名）；`xiaoxue-web/xiaoxue_api/modules/current_event/config.json`、`index.html`、`tests/workflow_ui.test.mjs`。
- 验证：日报上下文实测 2026-10-03（active 两赛事、选中 6 场、0 错误、分级正确）；DB 13 条德杯赛程校验通过；lol_data 测试 66 项通过 + config 哨兵 0 违规；xiaoxue-web build 通过、`/api/current-event` 返回新赛事、pytest 12 通过、node 43/44（1 处既有 tabs 预存失败，非本次引入）。
- 边界：世界赛 ScoreGG 词条未发布（source 名待核对）；外赛区队伍基础档案待名单确定后补齐；大周期交易预案仍为第三赛段版（内容层，待钧钧与小雪更新）。
- 适配面核对（按 PROJECT-MAP 用户模块）：

  | 用户模块 | 状态 | 结论 |
  |---|---|---|
  | teams-ts-profile | 已适配 | 关注名单/别名按两赛事更新（14 核心 + 12 常规）；外赛区 12 队档案与花名册列为待补 |
  | current-event-prep | 已适配 | 赛事卡/赛程/赛制全链路切新（BO1 支持、德杯 13 场入库、10/3 实测 0 错误） |
  | tk-library-and-search | 已适配 | 事件相关 TK 搜索词随配置切换（德杯 世界赛）；检索本体不变 |
  | project-center-and-feedback | 不受影响 | 内容不点名赛事；接口/测试/运行状态实测正常；周一 tree-sync 最近一次 09-28 ok |
  | stage-review-candidates | 不受影响 | 不依赖赛事范围；新阶段沉淀随真实使用接入 |
  | market-and-live-records | 不受影响 | 盘口记录与赛事范围无关 |
  | pure-ten-lineup | 不受影响 | 纯阵容不消费赛事范围 |
  | version-understanding | 待处理 | 正文仍为第三赛段版（内容层，等新周期更新） |

- 审计复查（09-30）：① 外赛区数据链路缺口——LEC/LCS/CBLOL/LCP 按旧规则整体拒绝、12 队无档案/花名册 → 待定接入方式（参考层接入或随名单补档）；② MSI 时代遗留无引用（msi_ts_daily_context / _check_data / 日报 msi 分支），post_import_cleanup 已加过期警示（防误删德杯 TBD 与国际数据）；③ WSCI 国际邀请赛=青训/学院队赛事、名古屋亚运会=国家队（LPL 未参加），维持拒绝；④ 队伍资料页 scope 补「国际」筛选按钮（后端 intl scope 既有支持，实测返回 7 队）。
- 收口（09-30 钧钧定调「按赛事为准、对象=两赛事队伍、打完即年度收尾」）：外赛区联赛不接入（12 队随名单确定一次性补档案/花名册）；MSI 残留清收——msi_ts_daily_context 归档 `scripts/archive/`、_check_data 修复为含国际赛事、.bak 移入 `.xiaobai-backups/project-center-cron/`、post_import_cleanup 维持禁运行警示；旧 MSI 三队（KC/DCG/FURIA）保留不收起；skill 参考（msi-era-leftovers / expected-rejects-triage）已同步终态。
- 虚拟赛果测试（09-30）：模拟德杯 10-03 两场完赛（LGD 1:0 FLY、KT 1:0 SR）走真实导入路径 → 单场赛果/批量赛果/单场依据/复盘入口/10-04 日报 dry-run「昨日比赛回顾」全部正确；TS 副本对照确认德杯不进 TS；测后已还原（matches 498 条、赛程行恢复、runs 产物清理），真实库无残留。
- 说明书收口（09-30）：①能力地图（CURRENT-CAPABILITY-MAP）刷新 4 行过期状态（赛程赛果→德杯周期、TS→快照正源、版本理解→#229 正源、日报→每日 07:00 自动发布）+ 核对日期；②CRON-ORCHESTRATION 对齐实际调度（日报 07:00、知识导入每日、旧 TS 任务已移除、no-agent 包装说明）；③小雪刷新回执/工具文案改赛段中性（「赛果和 TS 已刷新」）；④使用说明/项目地图/总体设计/工程实现核对无周期状态、无需改动；⑤pytest 195 全过，workbench 已重启生效。
- TS 面向赛事（09-30）：新增「国际赛」阶段——德杯/S16 世界赛计入 TS（跨赛区单池 + 国内终值结转 + σ 抬升）；run_ts_update 双阶段重算；活动阶段解析器（有国际数据自动接管）接入日报/前端/单场；lol_data 141 + xiaoxue-web 197 测试全过；副本模拟（跨赛区/结转/切换/国内零污染）通过。

## 2026-10-01｜小雪内容宏观收敛（技能 74→36，四批执行）

- 背景：钧钧要求按交易系统视角（事实→归因→规律→决策+保障）宏观优化小雪全部内容；方案批准后执行到全部完成。
- 批1：队伍画像 22→1（esports/teams/team-profiles，22 references）；产品侧 profiles/analyst 读取更新。
- 批2：知识维护/导入/复盘 3 族合并（esports/knowledge/ 下 knowledge-maintenance / knowledge-import / retrospective）；11 个旧目录退役；B站 cookie 迁移。
- 批3：周期/盘口/其他电竞/分析师/舆论 5 族合并（lol-cycle / lol-markets / other-esports-markets / analyst-lenses / opinion-sources）；scoregg+integrity 并入 lol-tournament-data-governance；17 个旧目录退役；analyst 后端 read_skill 改相对路径（修复别名化后框架丢失）。
- 批4：目录收敛（esports/knowledge、engineering、trading、devops 归类；workflow+toolkit+capability-landing 合并为 engineering/xiaoxue-dev-index）；12 份历史报告移入 archive；全系统引用 258+27 文件更新；退役 pre-match-plan / dianjing / 小雪看板。
- 验证：治理校验（team-profiles、3 知识技能、5 市场技能、dev-index）全 ok；测试——loop 90、xiaoxue-web 197、lol_data 相关 8+、合并技能 37、批1 契约 59 全过；inventory 306→285→收敛后 36 个域技能（esports 26 + 专属工程 8 + 交易 1 + 运维 1）；每批 receipt + 备份于 state/skill-governance。
- 说明：知识库（Wiki/TK）与自动化保持不动；剩余内容层（版本理解/交易预案新周期）仍需钧钧与小雪定内容。

## 2026-10-01｜防幻觉 1+2（事实核查扩面 + 动态事实带时间）

- 事实核查（fact_check.py）扩面：原只覆盖比分/胜者/TS 三类 → 新增稳定性、赛程日期两类；带日期的比分/赛果声明改为按日期核对（不再与最近一场混比，消除旧日期误报）；盘口类做成行为规则（没记录必须明说，写进 lol-markets 共同规则）；队名宽松过滤 + 「的/是」句式兼容；测试 9→27 项（新增临时库确定性用例）。
- 动态事实带时间：TS/赛程读取原已带 updated_at；画像三条读取路径补齐（canonical 加更新时间行 + updated_at 字段、skill 路径按文件时间加更新时间、fallback 补字段，五区块合同保持）；根入口加「动态事实带时间」规则（引用带「截至 X 月 X 日」）。
- 验证：小雪技能测试 60 全过；xiaoxue-web 198 全过（含新增画像时间用例）；治理校验 xiaoxue / lol-markets ok；workbench 已重启，`/api/profile-full/GEN` 实测返回更新时间。
- 备份：state/skill-governance/backups/20261001-anti-hallucination-1-2；receipt：20261001T155614Z-anti-hallucination-1-2。

## 2026-10-02｜完整度自检与 MCP 重载（小雪）

- 背景：大更新后钧钧要求完整度自检；小雪对全部核心链路做实测。
- 结果：核心全通——后端 18 模块健康、德杯赛程/赛果链路、TK 检索、画像+TS、版本理解、日报 07:01 已发、14 个自动化任务最近运行全 ok。
- 修复①：xiaoxue-product MCP 子进程停留在 09-30 02:49 加载版本，09-30 17:01「说明书收口」的赛段中性文案未生效 → 终止旧子进程 + 工具调用触发自动重连；新进程 10-02 15:58:42 启动，调用实测正常，零中断。
- 修复②：数据就绪任务（9b8cd8f43d39）移除失效技能引用 xiaoxue-esports-toolkit（no_agent 行为不变，读回确认）。
- 待定：大周期交易预案与版本理解新周期内容仍为第三赛段版（内容层）；磁盘剩 4.1G（85%~90%）建议清理；外赛区队伍档案随名单确定补齐。

## 2026-10-03｜按游戏类型整理（瓦先行）：规律库入库交易 TK + 游戏标签 + CS2 引用修复

- 背景：钧钧确认"以交易 TK 为中心"的整理方向，按游戏类型分步做（瓦/CS2 先、LOL 最后）；TK 默认 LOL，瓦/CS 按明确提及或上下文区分。
- 瓦：规律库 26 条（阶段 3 / 赛区 4 / 大小分 1 / 盘中 2 / 队伍速查 16）入库交易 TK，标签「游戏:无畏契约」；一次性脚本 `scripts/import_valorant_rules_to_tk.py`（hash 幂等）；skill 侧 valorant.md 标注"已入库、正式调用优先走 TK"（保留为工作镜像）。
- 标签机制：`tk_knowledge/service.py` 支持「游戏:」前缀（_TAG_PREFIXES + remember 过滤 regex 两处），供瓦/CS2 条目结构化区分。
- CS2：`ewc2026-cs2-team-snapshot.md`、`ewc2026-cs2-round16-session.md` 自 10-01 技能合并备份恢复（此前引用失效）；cs2.md 补「结构定位」小节。
- 影响面修复（游戏维度贯通，防 LOL 侧误拉）：xiaoxue-web `service.py` 加 `_document_game` 识别 + 5 处 LOL 语境聚合过滤（队伍交易 TK 列表 / 严格匹配 / 计数 / 单场相关 TK）；lol_data `daily_knowledge_manifest.py` 加 `game` 字段 + 团队/窗口匹配过滤——瓦条目不再进入 LOL 队伍列表、画像统计、单场 TK 和日报（T1/JDG 等撞名队伍已实测隔离）。
- 验证：py_compile + tk 相关测试 62 过、lol_data 测试 41 过；API 读回——按游戏 26/26 命中、T1 队伍交易 TK 2 条纯 LOL、瓦条目被排除；manifest 2379 条中 26 条瓦被正确隔离；引用完整性 5/5。
- 验收与瘦身（2026-10-03）：钧钧实测验收通过（"过了"）；valorant.md 规律库正文撤除（9045→4691 字符），改为「规律库索引」段（26 条清单 + 调用方式 + 更新路径）；两处校准补录 TK（中段条、大小分条各补 26 上海对照）；SKILL.md 说明同步；技能测试 10 过、引用完整性 5/5、reindex OK。
- 已完成：LOL 侧系统设计收拢（一个 `match_runs` 活跃比赛容器、一条 `xiaoxue-prematch-guide` 赛前入口、一个交易 TK 终点）；后续只做闭环验收、文档口径和兼容层退役观察。

## 2026-10-05｜LOL 容器收拢完成（切片 A+B+C：旧容器 / 研究档案 / 入口三合一）

- 背景：钧钧确认「系统设计性收拢」——一个容器（单场工作区）+ 一条赛前入口 + 一个终点（交易 TK）；「一步到位，睡醒验收」。口径：结构收拢、飞书/前端正常、数据不删。
- 切片 A（旧容器残留）：MCP 移除 3 个旧工具（52→49）；前端 current-event 收掉旧容器链（view 原有单场记录块/事件、public saveJudgment/saveChange、api 3 函数、service 3 函数）；module-contract.json current_match 合同更新（tools→match-run、state→match_runs/facts/entries、读写入口→match-run）；测试同步。旧容器端点与 2 张空表保留兼容。
- 切片 B（研究档案）：MCP 移除 9 个 research 工具（49→40；保留 prepare_match 首轮依赖的 match-brief 只读聚合）；research_subjects 模块置 disabled（「已归并进单场体系；接口保留兼容」，health 读回确认）；前端移除主体档案 tab/卡片/loader/页面注册；project-center-content.json 移除节点并升版 2026-10-05.2；daily_knowledge 合同移除 research_subjects；测试同步（9 个 research 测试、路由断言、tab 断言）。
- 切片 C（入口三合一）：`lol-research-dossier` 并入 `xiaoxue-prematch-guide`（升级 v1.3 赛前统一入口：研究/收集模式 + 引导模式，收集完成后主动衔接判断；收集方法全文存 references/research-collection.md）；原 skill 归档至 `.agents/archive/skills-retired-20261005/`；detect_task.py 与根 skill 入口表同步（research→统一入口）；赛前日报历史产出（3 个 md）归档至 `.agents/archive/scripts-retired-20261005/`（脚本本体此前已不存在，仅剩 pyc 缓存）。
- 服务：xiaoxue-workbench-api 重启（manifest 生效，research_subjects=disabled 读回）；hermes-gateway 重启（MCP 新版 40 工具 + skill 生效，新 PID 3012591）；前端 dist 重建（8880 tab=队伍资料/当前赛事/沉淀候选/TK资料库/项目中心）。
- 验证：全量 pytest 186 过；mjs 41 全过（含修复的 tab 断言）；小雪技能测试 60 过；health 读回 disabled；端点兼容读回正常；MCP 工具 40；detect_task 实测（研究/收集→统一入口）。
- 备份：`.xiaobai-backups/container-consolidation-20261005/`；归档：`.agents/archive/skills-retired-20261005/`、`.agents/archive/scripts-retired-20261005/`。
- 数据：一个字没删没改；旧表/旧端点/旧代码全部保留（兼容层）。
- 引导机制升级（v1.3，德杯要求补全 + 收集完成主动衔接）：铁律加「先加载再开口」（原话「你先去把对应的 skill 全部加载完」）；杯赛模板补「复刻/特例」「发挥=心理×实力」「什么时候进场」「BO1 特殊性」；收尾加沉淀去向（判断落单场、规律进候选→交易 TK）；收集底稿完成后直接抛第一步判断锚点。
- 文档全链路跟进（大改标准）：PROJECT-MAP（快照 2026-10-07 / loader 6 个 / 主页面 5 个 / stage-review 行）、工程实现（前端节 + 结构问题注 + 待验证 + F-006a 注）、modules.md（导航与单场主链）、能力地图（6 处）、dev-index（更新记录）、index.html 死 CSS 清理（11 处）、prematch-guide v1.3。
- 复验：pytest 186、mjs 41、技能 60、治理 verify ok 全过；dist 重建；gateway 重启生效。

## 2026-10-18 小白：小雪自动化自检——排程器终态再武装 + B站导入 TMPDIR 错位

- Goal：钧钧「自检一下，随便看看小雪自动化的问题」。只读排查全部 cron 任务/回执/日志，修掉两处真实故障。
- 故障一（排程器武装失败，影响次日赛前简报）：10-18 09:00 `LOL自动化排程器` 报 `cron edit 失败：Cannot activate terminal cron job 'LOL赛前简报' ... use cron resume --run-now or --at`。根因：受管一次性任务跑完后 `state=completed` 是 Hermes 终态，`update_job`（含 `cron edit --schedule`）拒绝激活它——10-17 的 `--repeat 0 → --schedule` 序列只在任务"还没跑过"时有效，跑完一次就再次失效。修复：`lol_auto_planner.py::arm_steps` 对 once 型任务改用 `cron resume <id> --at <时刻>`（Hermes 给的唯一正源入口，内部走 `rearm_oneshot`，重排消耗上限）。回归：`tests/test_lol_auto_planner.py` 新增终态再武装用例，45 passed。
- 故障二（B站知识导入误报失败）：10-18 06:04 知识导入 `partial / B站 DISCOVERY_FAILED`（发现 0、失败 0），当天巡检同时告警。根因：Hermes cron 给脚本设 `TMPDIR=<profile>/cache/scratch`，子脚本 `batch_discover.py` 用 `tempfile.gettempdir()` 把 manifest 写到 `<TMPDIR>/bilibili_batch`，父脚本 `xiaoxue_knowledge_import.py` 却硬编码读 `/tmp/bilibili_batch` → 读不到 manifest 判失败。实证：当天 45 个视频/32 条字幕的 manifest 实际落在 `~/.hermes/cache/scratch/bilibili_batch/`。修复：父脚本 `BATCH_DIR` 改为 `Path(tempfile.gettempdir())/"bilibili_batch"`，父子同源。E2E 实测（带 TMPDIR 真跑 discovery）：`status=complete`、B站 ready、11 个候选、文件路径可读回。
- 处置与边界：只改这两个确定性脚本 + 一个测试文件；备份在 `lol_data/.xiaobai-backups/automation-20261018/`、`xiaoxue-web/.xiaobai-backups/memory-bank/progress.md.bak-20261018-automation`。未改数据库、模型、Provider、权限、网关或 cron 定义；未发外部消息。
- 读回：跑一次排程器 → `LOL赛前简报` 已武装 2026-10-19 00:30、`LOL赛后刷新` 已武装 2026-10-19 06:30，均 `enabled=true / state=scheduled / repeat.times=null`；失败告警实跑静默。
- 未决（只报告不动手）：①`瓦赔率台账-赛果结算/盘口快照` 的 `origin` 投递偶发被飞书拒（`[99992402] field validation failed`，9-25~9-28 与 10-17 出现过，任务本身跑成功只是消息没送达）；②`/` 磁盘 90%（08:00 巡检 85.3%），大头是 `~/.hermes/backups` 540M、`~/.npm` 612M、`~/.ollama` 610M、`/var/log` 454M，等钧钧点头再清；③`加密盘前筛选`/`加密市场盯盘` 仍处停用（10-10 起），按现状不动。
- 为什么 10-17 那次没修好（钧钧追问后补查）：上次只修了"跑完的任务被到期扫描删掉"这一层（补 `--repeat 0`），但写时刻仍走 `cron edit --schedule`；而 Hermes 对一次性任务有第二个终态——正常跑完一次后 `state=completed`，`update_job` 会直接拒绝激活它，只有 `cron resume --at` 能重新武装。10-17 的验证正好落在"任务还没跑过"的形状（当时 job 还是 `state=scheduled`），单测也把 `--schedule` 这个错误步骤断言成了正确行为（只在自己代码里断言步骤序列＝假通过）。补强：新增 `tests/test_lol_auto_planner.py::TerminalRearmGuaranteeTests`，用子进程真调 Hermes 的 `update_job`/`rearm_oneshot`，钉死"终态拒绝 edit、resume --at 生效"。

## 2026-10-18 小雪：项目完整度自检（自动化重点）——投递取证与文案修复

- 背景：钧钧要求「自检一下项目，特别是自动化任务并且给出建议」。8 项清单逐项实测取证；白天两个修复批次（排程器终态再武装、B站导入 TMPDIR）在本次自检中复验通过。
- 全链实测：健康接口全模块正常；数据层（赛程/赛果/TS 快照/画像）正常；业务链路 8 项真实调用全通（TK 检索、队伍读取、版本理解、单场准备、阶段候选、待修改篮子、英雄静态资料、日报就绪）；部署一致性通过（无新于服务启动的代码、前端产物最新、MCP 子进程无滞后）；watchdog 实跑静默。
- 自动化核对：受管任务回执-现实一致——`LOL赛前简报` 10-18 00:30 实跑 ok、已武装 10-19 00:30；`LOL赛后刷新` 10-18 07:02 实跑 ok、已武装 10-19 07:00；知识导入 10-18 06:04 error 为修复前旧运行（修复已在位、相关测试全过），待 10-19 06:00 自然验证；其余任务无异常。
- 瓦台账投递取证（本批新证据）：直接拉取投递目标话题 `omt_19d647b89acf9ce7` 消息逐条核对——10 月台账消息绝大多数实际送达；确认丢失 10 条：9-25~9-28 连续 4 天 8 条全丢 + 10-17 23:49 结算 + 10-18 16:32 快照；失败均发生在任务跑成功、消息被飞书拒收（99992402）之后，无自动补发。
- 修复（本批直接做）：运营状态文案「按每日 10:30 调度执行」与实际调度（07:00）不符——`daily_content/config.json` 改为「日报生成与投递自动化运行中；按每日 07:00 调度执行。」，health 读回生效；全库无其他「10:30」引用、无测试引用。
- 待定（只报告与建议）：①S16 新队资料缺口现状——覆盖检查实测报「MVK 不在库」「FUR 不在库」（FUR 为赛程名未映射到库内 FURIA；MVK 等新队无身份/首发/画像），影响 KC vs MVK 等场资料完备度；与「等钧钧给来源」的既有缺口一致，补录前不自动抓取。②瓦台账投递：现有 10 个失败样本，建议专项根因或继续观察。③阶段整理候选积压 6 条（8-30、9-17）。④`/` 磁盘 89%（可用 4.3G），候选大项与白日记录一致（backups 540M、.npm 612M、.ollama 610M 等），等钧钧点头再清。
- 会后执行（钧钧当日指示）：①无畏契约内容全面暂停——`瓦赔率台账-盘口快照`/`赛果结算` 两条任务已暂停（enabled=false / state=paused），数据与配置保留、可随时恢复。②磁盘清理——删除 8-23 旧备份快照 539M（内容清单归档）+ codex-acp npx 缓存 445M + uv 缓存 264M，实际释放约 1.25G（可用 4.3G → 5.5G）；ollama 610M 查实为 ClawBench 活跃依赖未动；清理记录见 `~/.hermes/backups/cleanup-20261018/`。
- 边界：未改数据库、模型、Provider、权限、网关或 cron 定义；本批写入为文案修复、本记录与「最后更新」更新人字段；未发外部消息。

## 2026-10-26｜全链路自检

- 服务健康：7 个模块（日报 / 队伍 / 认识 / 应用外壳 / 外部事实 / 方法 / 比赛）全部 healthy；整体 ok=false 的唯一原因是磁盘 93%。
- 数据层：teams 34、schedules 580、matches 551、team_profiles 30、shared_version_analysis 134；今日 4 场赛果已入库（09:50 更新）。
- 业务链路实测：TK 搜索与全文读取、BLG 队伍读取、版本理解目录、BLG vs KC（10-27）单场准备、待修改篮子、阿卡丽静态资料、10-26 日报（09:48 发布，verified）全部正常。
- 部署一致性：后端无晚于进程启动的代码、前端产物最新、产品 MCP 子进程晚于脚本文件。
- 自动化：19 个任务；10-26 09:46 知识导入 partial（B 站 6 篇中 1 篇 TK 提炼瞬时不可用、字幕已留底）已手动重跑写入并重建索引；公众号 25 篇发现中 2 篇新写入、23 篇重复（前一日已导入）。
- 待处理：磁盘 93%（剩余约 1.0G），需清理；候选为 snapd 旧版本、npm 缓存、uv 缓存。

## 待做

| 优先级 | 内容 | 备注 |
|--------|------|------|
| P2 | 飞书附件能力文档化到小雪工作流 | 已有 Hermes `send_message + MEDIA:` 兜底可发图片/文件；不要优先补 lark-cli 用户 OAuth scope |

## 当前验收口径

| 模块 | 验收 |
|------|------|
| 运维 | `vibe-status` 服务全 active，proxy residue 为 none，根分区低于 85% 优先；85%-92% 警告，92% 以上必须清理 |
| 盘口记录 | 前端新建、读取、删除只走 `/api/market-notes`；单条记录可先预览、明确确认后写回复盘，且只改原记录；不自动交易、不自动写 TK/画像 |
| 赛前交易判断能力 | 交易 TK、当前交易预案和盘口记录分别走各自正式入口；不生成第二份日报、不注入交易判断层、不作为 LOL 日报发布门禁；缺数据时明确“暂不推荐” |
| LOL 日报 v2 | 生产只走 `daily_pipeline.py --publish`；唯一 daily artifact 是 `LOL电竞日报_{date}.md`；发布前 readiness manifest 必须是当天完整刷新、`mode=full / ok=true` 且两个阶段成功 |
| BP 八步法 | `/api/lineup-workflow/prepare` 校验蓝红方和双方五位置，返回固定八步与 `保留/降权/取消/等待`；前端只整理输入，小雪对话执行动态判断 |
| 画像页 | 优先 Wiki，其次 SKILL.md，再用数据库只读兜底；兜底画像必须标明来源和“不替代人工画像” |
| 版本理解 | 全局版本读取 `shared_version_analysis`；旧 `/api/version-understanding/{team}` 仅作兼容，前端不再展示队伍版本栏目 |
| TK 搜索 | `/api/tk/search` 读 MemPalace `xiaoxue-tk` 分区，再用 Wiki 文件补齐；旧 8768 服务和自动回退代码已删除；日期从 frontmatter/mtime 提取，结果按日期降序，不能按文件名字母序提前截断 |
| TK资料库 | 默认最新优先；今天/7天/30天/月/全部可切换；队伍与关键词可筛选；每次加载 30 条；点开读取完整正文且不显示来源/文件名等后台字段 |
| memory-bank | 新对话先读 `README.md`、改模块读 `modules.md`、汇报进度读本文件 |
| 模块隔离 | 默认运行 `scripts/acceptance_check.py` 做只读逐模块验收；某一模块失败后继续检查其余模块；架构门禁要求后端严格三层、跨模块只走 `public.py`，前端跨模块只走 `public.js`/语义事件；只有显式传入写入开关才允许做临场记录写入验收 |

## 2026-10-13 Codex：LOL完整阵容分析性能窄切片

- 已完成真实日志拆解与指定阵容复测；新增只读计时执行器，未修改正式技能正文、模型、配置或业务数据。
- 基线：313.139秒、3次模型调用、81893输入tokens；取数消息间隔5.844秒；最终回复消息间隔215.153秒（非独立API日志）；字段完整性人工对照通过。
- 仪器化实测245.9秒（完整生成API208.4秒）；官方预加载试验249.574秒、2次调用（完整生成216.3秒）。字段人工对照齐全，但32:30取舍波动，质量等价未获证明。未达120秒；不宣称根因修复或飞书入口提速，证据见lineup-test/batch1-review.md。

## 2026-10-16 小白：LOL 信息与自动化整合（S1/S2 已交付）

- 文档：新增 `docs/archive/designs/LOL信息与自动化整合-PRD.md` 与 `docs/archive/designs/LOL信息与自动化整合-工程实现.md`，并在 `docs/PROJECT-MAP.md` 文档权威等级登记（骨架仍以总体设计为准）。
- S1：新增只读能力 `xiaoxue_api/modules/lol_scope/`（范围派生 + 每场"谁上场/价格/结果"覆盖状态与洞清单），真实入口 8880 已读回；`tests/test_lol_scope_service.py` 10 项通过。
- S2：新增唯一排程器 `lol_data/scripts/lol_auto_planner.py`（执行时刻由赛程算出，写入 Hermes cron 并写回执），新增 4 个受管任务到小雪 Profile：LOL自动化排程器 / LOL赛前简报 / LOL赛后刷新 / LOL自动化失败告警。
- 验证：改期跟随（副本改期后执行时刻自动变化）、无比赛不排、幂等不重写、失败出声均已实测；排程器与告警脚本测试 16 项通过。
- 未做：S3 gol.gg 落库、S4 接价格、S5 日报退成归档。

## 2026-10-17 小白：LOL 整合 S3/S4/S5 交付（日报按钧钧决定保留）

- S3：teams 表补来源留痕字段（幂等迁移 + 改前备份）；新增外部事实入库入口 `team_intake`（库外队伍身份+首发，无来源拒绝、不覆盖已有、写入后盖来源章）；覆盖面入库后自动关闭缺口（临时库验证）。
- S4：新增外部价格留存入口 `lol_price` → `lol_price_facts`；覆盖面价格三态接通（有报价/这场没报价/未接入），带来源与时间。
- S5：新增 `xiaoxue_change_watch.py` 小时级"谁上场变了 / 价格到了"推送；日报保留 07:00 不退役。
- 来源现状：gol.gg（JS 渲染、现拉不动）、ScoreGG（无公开首发接口）、lol.fandom（本机不通）→ C9/FUR/MVKE 真实首发与 LOL 价格仍需钧钧给来源。
- 测试：xiaoxue-web 44 项（含 team_intake/price 10 项）、lol_data 28 项（排程器 10、告警 6、失败说明 5、变化推送 7）。

## 2026-10-25 小白：本机零 Key 中文搜索接入全项目

- 背景：Hermes 内置 `web.search_backend=tavily` 不稳定，项目采集/资讯/预测链路缺少可复用的免费中文搜索入口。
- 服务：安装 `daidaiJ/websearch-mcpserver` v3.10.2，systemd 常驻 `127.0.0.1:8338`；`mode=mcphub`，Bing/360 作回退，无付费 Key。
- Hermes：`web.search_backend=searxng`，`SEARXNG_URL=http://127.0.0.1:8338/searxng`；另接入 `agent-search-mcp`（搜狗/Bing 中文补充）与 `websearch-http`（smartsearch/cleanfetch）。
- 项目：新增 `xiaoxue_api/core/web_search.py` 与 `scripts/search_web.py`；`collection_repository.search()`、产品 MCP 外部资讯/预测、`prediction_hunt.py`、`agent-reach` 路由均改为优先走本机搜索；`system_config.json` 新增 `services.web_search_url/health`。
- 边界：不改数据库、不刷新比赛资料、不跑真实采集、不碰线上 `dist`；赔率仍只算网页线索，不冒充可核验价格。
- 验证：`test_web_search.py` 5 项通过；`test_xiaoxue_product_mcp.py` 43 项 + 新增本地回退用例通过；`test_current_event_collection.py`/`test_supply_design.py` 共 44 项通过；真实只读搜索 `TES G2 赛前预测` 返回 8 条线索，产品 MCP 本地搜索返回 5 条结果；全量前端 99 通过、产品 MCP 64 通过。
- 已知全量后端仍有 5 项基线失败（`test_event_screening_batches.py` 3 项、`test_match_desk_contract.py` 2 项）；在未改动的 HEAD worktree 复跑同样失败，确认与本次搜索改动无关。
- 运行态：`websearch-mcpserver.service` active；Hermes 已自动发现 `websearch-http` 与 `agent-search`，现有会话需新会话或 `/reload-mcp` 才能看到新工具。
