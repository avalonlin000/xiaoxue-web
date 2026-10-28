# 足球来源有界核验（解耦验收 A01 承接）

- 任务：kanban t_69df7d67（解耦验收A01：卡塔尔足球来源有界只读核验）
- 调查人：小白
- 调查时间：2026-10-28 17:54–17:59 +08:00（UTC 09:54–09:59，多哈 UTC+3 12:54–12:59）
- 范围声明：只读调查 + 少量上游 GET。本卡未改代码、配置、数据，未安装依赖，未触发任务、未重启服务、未发外部消息、未删除 qat.1 配置、未提交推送。
- 结论一句话：**找到可用的官方候选入口（卡塔尔足协 QSL 赛程页，服务器渲染，HTTP 200，含完整轮次赛程），但“可替换数据”还不成立**——官方页未声明时区，第三方同轮数据与官方冲突。ESPN `qat.1` 上游确实 400，且当前实现下 400 不是唯一缺口（24 小时窗口）。所以本卡只关闭“替代来源是否已找到”的调查，**不关闭 A01 覆盖缺口**。

## 1. 正式入口复现（从 service.py 核实路由与参数）

`xiaoxue_api/modules/external/football/service.py`：

- `ESPN_BASE = https://site.api.espn.com/apis/site/v2/sports/soccer`（第 14 行）
- `DEFAULT_LEAGUES = ("eng.1","esp.1","ita.1","ger.1","aus.1","swe.1","qat.1","chn.1")`（第 15 行）
- 列表取数：`_matches_for()` → `GET {ESPN_BASE}/{league}/scoreboard?dates=YYYYMMDD`（第 138–145 行），异常只汇入 `errors`，不抛出。
- 窗口：`_dates()` 取 **UTC 今天 + UTC 明天**（第 77–79 行），即 24 小时窗口。
- 正式列表路由：`/api/football/matches`（PROJECT-MAP.md 第 44 行），readiness 由 `errors` 是否为空决定（第 187 行）。
- 配置正源 `config/football.json` 的 leagues 与 `DEFAULT_LEAGUES` 一致，含 `qat.1`；`whitelist` 含 `Al Sadd`。

### 复现的真实响应

```
$ curl -s -o /tmp/fb.json -w "HTTP %{http_code} time %{time_total}s size %{size_download}\n" \
    "http://127.0.0.1:8880/api/football/matches"
HTTP 200 time 14.109763s size 15982
```

响应摘要（2026-10-28 17:54 +08:00）：

```
ok False   readiness partial
coverage: leagues=[eng.1, esp.1, ita.1, ger.1, aus.1, swe.1, qat.1, chn.1] window_hours=24 source=ESPN
errors:
  - qat.1: HTTP Error 400: Bad Request
  - qat.1: HTTP Error 400: Bad Request   ← 两个 UTC 日期各一次
matches: 18 场，全部来自 esp.1 / ita.1 / swe.1 等，qat.1 为 0 场
```

即：页面级表现就是 `readiness=partial` + 两条 `qat.1: HTTP Error 400: Bad Request`，与已知证据一致（不重复同一请求当进展，此处仅作为正式入口取证）。

## 2. 上游核对：ESPN 侧（精确 URL / 状态 / 短响应）

| 请求 URL | 时间(+08:00) | HTTP | 短响应 |
| --- | --- | --- | --- |
| `https://site.api.espn.com/apis/site/v2/sports/soccer/qat.1/scoreboard?dates=20261028` | 17:57 | **400** | `{"code":400,"message":"Failed to get events endpoint."}`（gzip 解压后） |
| `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=20261028` | 17:57 | 200 | 正常 events |

结论：`qat.1` 在该 ESPN 前端接口上不存在/不服务，不是本项目的参数或编码错误（同参数 `eng.1` 正常）。与已知证据“qat.1 带/不带日期均 400、qatar.1 亦 400、核心联赛目录前 220 项无匹配”一致，未发现新的 ESPN 可用路径，因此不再重复探测 ESPN。

## 3. 候选替代来源试探（全部真实 GET）

| 来源 | URL | HTTP | 判断 |
| --- | --- | --- | --- |
| ESPN 站点搜索 | `https://site.web.api.espn.com/apis/common/v3/search?query=qatar&limit=8` | 503 | `Search Guru Meditation`，不可用 |
| TheSportsDB（旧免费 key 3） | `.../api/v1/json/3/search_all_leagues.php?c=Qatar&s=Soccer` | 403 | 提示 key 永久停用 |
| TheSportsDB（新测试 key 123） | 同上，key 改为 `123` | **200** | 可用，见第 4 节（数据有日期漂移） |
| SofaScore | `https://api.sofascore.com/api/v1/search/all?q=Qatar%20Stars%20League`（含 Referer/UA） | 403 | Cloudflare 拦截，不可用 |
| QSL 官方页 | `https://www.qsl.qa/en/doha-bank-stars-league-fixtures-results` | **200** | 服务器渲染，见第 4 节（首选） |
| QSL 官方 JSON:API 探测 | `https://www.qsl.qa/jsonapi`、`/jsonapi/node/fixture` | 404 | 无 JSON:API；但 HTML 已可解析，不影响 |

（顺带否证：`qsl.qa` 的 `en/fixtures`、`en/matches`、`en/match-center` 均 404，本站真实路径是 `en/doha-bank-stars-league-fixtures-results`，来自首页导航链接，非猜测。）

## 4. 候选来源与赛事身份核对

### 4.1 首选：卡塔尔足协官方 QSL 赛程页

- URL：`https://www.qsl.qa/en/doha-bank-stars-league-fixtures-results`
- 2026-10-28 17:57 实测：`HTTP 200`，127129 字节；未执行 JS 即含赛程行（服务端渲染）。
- 赛事身份：页面标题 `Doha Bank Stars League - Fixtures / Results | QSL`，赛季 `2026-2027`。“Doha Bank Stars League” 即卡塔尔顶级联赛 Qatar Stars League 的冠名名称（同站另有 `Jetour League`、`Qatar Cup`、`QSL Cup`、`QSL2`，彼此独立，未混用）。
- 页面实际文本节选（去标签后原样）：

```
FIXTURES / RESULTS   Fixtures  Results   Filter Match by : Week  All  Week 8  Week 9  Week 10  Week 11
Week 8
43  30/10/26 17:15  Al Shahania VS Al Ahli      Al Khor Stadium
44  30/10/26 19:30  Al Sadd VS Al Shamal        Jassim Bin Hamad
45  30/10/26 19:30  Al Gharafa VS Qatar SC      Thani Bin Jassim
46  31/10/26 17:15  Al Sailiya VS Lusail        Suhaim Bin Hamad
47  31/10/26 19:30  Al Arabi VS Al Rayyan       Al Thumama
48  31/10/26 19:30  Al Duhail VS Al Wakrah      Abdullah Bin Khalifa
Week 9
49  06/11/26 17:15  Al Arabi ...
```

- 时间口径：页面只显示 `dd/mm/yy HH:MM`，**未显式声明时区**。可确认的只是：赛事在卡塔尔、场地为卡塔尔境内球场，卡塔尔民用时区为 AST/UTC+3 且无夏令时（本机 `TZ=Asia/Qatar date` 实测 12:58+03 对 UTC 09:58，仅证明该时区偏移，不证明页面用的就是它）。因此 **kickoff 时区应记为“未确认”**，实施阶段不得凭 UTC+3 假定换算后直接写库，需先取得官方时区/比赛日依据（或用两条独立来源同场核对）。
- 可解析结构（最小适配依据，非改动）：`<tr class="fixture-result">`；`<td class="table__date"><div class="table__date__round"><span>43</span><p>30/10/26<br>17:15</p>`；`<td class="order-team score-block">` 内 `a.linked-club.table__result__team > span` 为主客队名；场地在结果块后续 td 文本。

### 4.2 次选（仅交叉核对，不作主源）：TheSportsDB

- 联赛身份：`search_all_leagues.php?c=Qatar&s=Soccer` → `idLeague=4663`，`strLeague=Qatar Stars League`，`strSeason=2026-2027`，`idCup=0`（联赛，非杯赛）。同名杯赛（4971 Emir of Qatar Cup、5192 QSL Cup）未混用。
- `https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id=4663&r=8&s=2026-2027` → **HTTP 200**，6 场，`strTimestamp` 为 UTC：

```
2026-10-30T14:15:00 Al-Shahaniya vs Al-Ahli Doha   R8
2026-10-30T16:30:00 Al-Sadd vs Al-Shamal            R8
2026-10-30T16:30:00 Al-Gharafa vs Qatar SC          R8
2026-11-06T16:00:00 Al-Sailiya vs Lusail            R8
2026-11-06T16:00:00 Al-Duhail vs Al-Wakrah          R8
2026-11-06T16:00:00 Al-Arabi vs Al-Rayyan           R8
```

- 与官方页对照（官方本地时间 → UTC）：30/10 17:15 → 14:15 UTC ✔；30/10 19:30 → 16:30 UTC ✔；**31/10 17:15/19:30 → 应为 14:15/16:30 UTC，TheSportsDB 却给 2026-11-06 16:00，3/6 场日期漂移**。
- 另外 `eventsnextleague.php?id=4663` 只返回 1 条、`eventspastleague.php?id=4663` 也只 1 条（免费 key 大幅限量），且 key `123` 是公共测试 key，配额与稳定性都不能作为生产依赖。
- 结论：TheSportsDB 只能当交叉校验或兜底，**不能当卡塔尔主源**；日期必须另有权威比对。

#### 4.2.1 明确的来源冲突（不得视为可替换数据）

同轮 R8，两源给出**不同的日期和不同的时刻**，不是格式差异：

| 比赛 | 官方 QSL 页（本地时刻，时区未显式声明） | TheSportsDB（strTimestamp，UTC） |
| --- | --- | --- |
| Al Sailiya vs Lusail | 31/10/26 17:15 | 2026-11-06T16:00:00 |
| Al Arabi vs Al Rayyan | 31/10/26 19:30 | 2026-11-06T16:00:00 |
| Al Duhail vs Al Wakrah | 31/10/26 19:30 | 2026-11-06T16:00:00 |

即使忽略时区，日期本身就差 6 天，且两场 19:30 被第三方压成同一时刻 16:00。**因此第三方 HTTP 200 不能当作“已找到可替换数据源”的证据**；它只证明该接口可访问，不证明数据正确。可用的只有“官方页作为赛事身份与赛程候选源”，其时间字段仍需在实施阶段逐场核对（官方公告/比赛日确认）后才可写入。

## 5. 契约映射（若未来实施，最小适配方案）

现有匹配对象契约（`_normalize_event`）字段与 QSL 官方页映射：

| 契约字段 | 现有 ESPN 口径 | QSL 官方页映射 |
| --- | --- | --- |
| `id` | `espn:{league}:{event_id}` | `qsl:{league}:{match_no}`（match_no = 行内 `<span>43</span>`） |
| `source` | `ESPN` | `QSL`（官方） |
| `league` / `league_name` | `qat.1` / season displayName | `qat.1` / `Qatar Stars League`（页面冠名 Doha Bank Stars League 需固定映射） |
| `home` / `away` | 队名+id | 队名取自 `a.linked-club span`；官方页无稳定队 ID，`id` 留空或按队名哈希 |
| `kickoff` | 事件 `date`（UTC ISO） | 页面 `dd/mm/yy HH:MM`，**时区未声明 → 记为未确认**；取得官方时区依据前不得按 UTC+3 假定并转 UTC |
| `status` | `status.type.state` | 有比分/结果显示 `post`，无则 `pre`；过滤标签 “Fixtures/Results” 决定 |
| `source_url` | `.../{league}/summary?event=` | 官方 fixtures 页 URL（可带 `?week=N` 锚点） |
| `opening_total` / `plays` | summary 的 `odds` 派生 | 官方页无初盘，保持 `None` + `missing_opening_total`（与现状同口径，不伪造） |

实施建议（留给项目工程流程，不在本卡执行）：
1. 在 `external/football/` 内新增一个 Qatar 适配函数/模块，按 league 分流（`qat.1` 走 QSL，其余继续 ESPN），不改 `DEFAULT_LEAGUES`、不删 `qat.1`。
2. 只解析服务端渲染 HTML 的 `tr.fixture-result` 行；对 HTML 结构变化要显式产出 `errors`（例如 `qat.1: qsl structure changed`），保持 partial 可见，不静默空白。
3. 时间处理：页面时刻先按“时区未确认”原样保留并显式标注；取得官方时区依据（官方声明/两源同场核对）后才统一转 UTC。测试至少覆盖：时区未确认时的显式降级、轮次过滤、结构变化报错、无比赛日空态。
4. 上线后从真实页面 `/football` 读回卡塔尔比赛与开赛时间，再谈关闭 A01。

## 6. 剩余动作与责任人

| 动作 | 责任人 | 说明 |
| --- | --- | --- |
| 决定是否接入 QSL 官方页作为 `qat.1` 源（结构级取舍，需钧钧/产品确认） | 钧钧 | 涉及新增外部来源与解析维护成本 |
| 实施第 5 节最小适配 + 单测 + 真实页面读回 | 小白（项目工程流程另开卡） | 本卡不改代码，未开工 |
| A01 覆盖验收 | 小白 | 只有适配上线且原页面读回正确比赛与时间后才能关闭；当前维持 partial + 可见错误 |

## 7. 附带观察与本次写入副作用（如实记录）

0. **本次复现触发了服务自身缓存写入（不是我改数据）**：`GET /api/football/matches` 会让 `list_matches()` 调 `_write_cache()`，因此 `xiaoxue_api/data/football/matches.json` 被服务刷新（31625 字节，`saved_at 2026-10-28T09:55:16Z`，34 行，league 仅 aus/eng/esp/ger/ita/swe，无卡塔尔）。该路径本就存在（未跟踪目录），内容由本次正式入口请求产生，未做手工编辑。除此之外，工作树唯一新增是 `Delivery/evidence/football-source-followup-20261028.md`；`data/football/matches.json`（根目录那份）mtime 仍为 10-22 02:05，未被本次改动。
1. **24 小时窗口是独立缺口**：`_dates()` 只取 UTC 今天/明天，而 QSL 第 8 轮在 10-30/10-31。即使来源修好，今天（10-28）卡塔尔仍会是 0 场。要覆盖卡塔尔必须同时确认窗口策略，否则 A01 仍会“空但正常”，与来源故障不可区分。
2. 根目录 `data/football/matches.json` 缓存里存在非真实行（`eng.1` 的 `A vs B`、`Home vs Away`，`saved_at 2026-10-21T18:05:02Z`），并被合入列表（本次 18 场中含 2026-10-25/26 的旧行）。属历史测试残留，未清理，建议单独立项。
3. 本次未验证“上游正常时列表能读到卡塔尔比赛”的端到端结果——因未实施，符合本卡范围；**不得据此宣称 A01 通过**。

## 8. 结论

- 替代来源：**找到候选源，但“可替换数据”未成立**。QSL 官方赛程页（`https://www.qsl.qa/en/doha-bank-stars-league-fixtures-results`，HTTP 200，服务端渲染）赛事身份与赛季（2026-2027，卡塔尔顶级联赛冠名 Doha Bank Stars League）核对通过，可作为适配候选；但页面**未声明时区**，且第三方 TheSportsDB 同轮 R8 的日期/时刻与官方冲突（3/6 场差 6 天，见 4.2.1），第三方 HTTP 200 不能当作可替换数据。
- source-blocked：**否**（存在可访问的官方候选入口，阻碍转为“时区与逐场时间需权威确认”）。
- A01 覆盖：**仍未通过**，维持 `partial` 与可见错误；关闭条件见第 6 节。
- 本卡未修改任何代码/配置/数据，未安装依赖，未触发任务或重启服务，未提交、未推送；仅新增一份 Delivery 证据文件，并因复现请求由服务自身刷新了其缓存文件（见 7.0）。
