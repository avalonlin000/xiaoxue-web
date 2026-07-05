"""小雪工作台 FastAPI 后端 v2 — 对话驱动布局"""
import sqlite3, os, re, hashlib, json, asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

app = FastAPI(title="小雪工作台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = "/home/ubuntu/lol_data/英雄联盟数据库.db"
WIKI_DIR = "/home/ubuntu/workspace/knowledge/wiki"
TK_DIR = os.path.join(WIKI_DIR, "小雪电竞", "原始资料", "tk")
SKILL_DIR_XIAOBAI = "/home/ubuntu/.hermes/profiles/xiaobai/skills"
SKILL_DIR_MAIN = "/home/ubuntu/.hermes/skills"
RAG_API = "http://localhost:8768/api/search"
REINDEX_API = "http://localhost:8768/api/reindex"

DAILY_CONTENT_ROOT = "/home/ubuntu/lol_data/scripts"
DAILY_ANALYST_ENTRY_COPY = "/home/ubuntu/life-os-frontend-v2/docs/products/xiaoxue-esports-life/ANALYST-ENTRY-COPY.md"
DAILY_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _resolve_daily_content_date(value: str | None) -> str:
    raw = (value or "today").strip().lower()
    if raw == "today":
        return datetime.now().strftime("%Y-%m-%d")
    if not DAILY_DATE_RE.fullmatch(raw):
        raise HTTPException(400, "非法 date 参数；只支持 today 或 YYYY-MM-DD")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "非法 date 参数；只支持 today 或 YYYY-MM-DD")
    return raw


def _daily_content_files_for(date_str: str) -> dict:
    """Generate the fixed daily-content whitelist for one safe date only."""
    return {
        "daily_report": {
            "title": f"LOL电竞日报 {date_str}",
            "kind": "daily_report",
            "path": os.path.join(DAILY_CONTENT_ROOT, f"LOL电竞日报_{date_str}.md"),
        },
        "pre_match_card": {
            "title": f"MSI赛前内容卡 {date_str}",
            "kind": "pre_match_card",
            "path": os.path.join(DAILY_CONTENT_ROOT, f"MSI赛前内容卡_{date_str}.md"),
        },
        "analyst_entry_copy": {
            "title": "分析师入口说明",
            "kind": "analyst_entry_copy",
            "path": DAILY_ANALYST_ENTRY_COPY,
        },
    }

# DeepSeek API config — read from hermes config.yaml when available.
# In Hermes profile shells, HOME may point at ~/.hermes/profiles/<profile>/home,
# so expanduser('~/.hermes/config.yaml') is not always the real shared config path.
import yaml as _yaml

def _load_hermes_config():
    candidates = [
        os.path.expanduser("~/.hermes/config.yaml"),
        "/home/ubuntu/.hermes/config.yaml",
        "/home/ubuntu/.hermes/profiles/xiaobai/config.yaml",
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as _f:
                return _yaml.safe_load(_f) or {}
    return {}

_cfg = _load_hermes_config()
LLM_URL = "https://api.deepseek.com/v1/chat/completions"
LLM_KEY = _cfg.get("providers", {}).get("deepseek", {}).get("api_key", "")
LLM_MODEL = _cfg.get("model", {}).get("default", "deepseek-v4-pro")

# ─── Lifespan (load skills at startup) ──────────────────
SKILL_ZHONGNIAN = ""
SKILL_XINYU = ""

def _load_skill(name):
    # 先查小白项目主责 profile，查不到回主目录
    for base in (SKILL_DIR_XIAOBAI, SKILL_DIR_MAIN):
        path = os.path.join(base, name, "SKILL.md")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read()
    return ""

@app.on_event("startup")
def _load_skills():
    global SKILL_ZHONGNIAN, SKILL_XINYU
    SKILL_ZHONGNIAN = _load_skill("zhongnian-esports-coach")
    SKILL_XINYU = _load_skill("xinyu-tactical-analyst")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── Teams ──────────────────────────────────────────────

@app.get("/api/teams")
def list_teams():
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT t.short_name, t.name, t.team_id, t.region
        FROM teams t
        WHERE EXISTS (SELECT 1 FROM rosters r WHERE r.team_id = t.team_id AND r.status = 'active')
           OR t.region = 'INTL'
           OR t.league_id LIKE 'MSI%'
           OR EXISTS (
               SELECT 1 FROM team_3d_data d WHERE d.team_name = t.short_name
           )
        ORDER BY CASE WHEN t.region='LPL' THEN 0 WHEN t.region='LCK' THEN 1 WHEN t.region='INTL' THEN 2 ELSE 3 END, t.short_name
    """).fetchall()
    conn.close()
    return [{"short_name": r["short_name"], "name": r["name"], "team_id": r["team_id"], "region": r["region"]} for r in rows]


@app.get("/api/schedules")
def list_schedules(
    event: str = Query(None),
    region: str = Query(None),
    team: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    limit: int = Query(50),
    upcoming: bool = Query(False),
):
    """赛程查询 — 支持 event/region/team/日期筛选"""
    conn = get_db()
    wheres = []
    params = []

    if event:
        event_like = f"%{event}%"
        if event.upper() == "MSI" or "季中赛" in event:
            wheres.append("(stage LIKE ? OR region = ? OR source LIKE ?)")
            params.extend([event_like, "国际", event_like])
        else:
            wheres.append("stage LIKE ?")
            params.append(event_like)
    if region:
        wheres.append("region = ?")
        params.append(region)
    if team:
        wheres.append("(team_a = ? OR team_b = ?)")
        params.extend([team, team])
    if date_from:
        wheres.append("date >= ?")
        params.append(date_from)
    if date_to:
        wheres.append("date <= ?")
        params.append(date_to)
    if upcoming:
        from datetime import date as dt_date
        today = dt_date.today().isoformat()
        wheres.append("date >= ?")
        params.append(today)

    where_clause = " AND ".join(wheres) if wheres else "1=1"
    rows = conn.execute(f"""
        SELECT date, time_bjt, team_a, team_b, region, format, stage, updated_at
        FROM schedules
        WHERE {where_clause}
        ORDER BY date ASC, time_bjt ASC
        LIMIT ?
    """, params + [limit]).fetchall()

    conn.close()
    return [{
        "date": r["date"],
        "time": r["time_bjt"],
        "team_a": r["team_a"],
        "team_b": r["team_b"],
        "region": r["region"],
        "format": r["format"],
        "stage": r["stage"],
        "updated_at": r["updated_at"],
    } for r in rows]


@app.get("/api/players")
def list_players(team: str = Query(...)):
    conn = get_db()
    team_row = conn.execute("SELECT team_id FROM teams WHERE short_name = ?", (team,)).fetchone()
    if not team_row:
        conn.close()
        raise HTTPException(404, "队伍未找到")
    rows = conn.execute("""
        SELECT player_name, role FROM rosters
        WHERE team_id = ? AND status = 'active' AND is_starter = 1
        ORDER BY CASE role WHEN '上单' THEN 1 WHEN '打野' THEN 2 WHEN '中单' THEN 3 WHEN 'ADC' THEN 4 WHEN '辅助' THEN 5 END
    """, (team_row["team_id"],)).fetchall()
    conn.close()
    return [{"name": r["player_name"], "role": r["role"]} for r in rows]


# ─── 3D Data ────────────────────────────────────────────

@app.get("/api/team-3d/{team}")
def get_team_3d(team: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM team_3d_data WHERE team_name = ? ORDER BY updated_at DESC LIMIT 1", (team.upper(),)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"队伍 {team} 无三维数据")
    return {
        "team_name": row["team_name"],
        "dim_1_name": row["dim_1_name"], "dim_1_value": row["dim_1_value"],
        "dim_2_name": row["dim_2_name"], "dim_2_value": row["dim_2_value"],
        "dim_3_name": row["dim_3_name"], "dim_3_value": row["dim_3_value"],
        "notes": row["notes"] or "", "version_understanding": row["version_understanding"] or "",
        "updated_at": row["updated_at"],
    }


class Team3DUpdate(BaseModel):
    dim_1_value: str = ""; dim_2_value: str = ""; dim_3_value: str = ""
    notes: str = ""; version_understanding: str = ""

@app.put("/api/team-3d/{team}")
def update_team_3d(team: str, data: Team3DUpdate):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute("SELECT id FROM team_3d_data WHERE team_name = ? ORDER BY updated_at DESC LIMIT 1", (team.upper(),)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "队伍未找到")
    conn.execute("""UPDATE team_3d_data
        SET dim_1_value=?, dim_2_value=?, dim_3_value=?, notes=?, version_understanding=?, updated_at=?
        WHERE id=?""",
        (data.dim_1_value, data.dim_2_value, data.dim_3_value, data.notes, data.version_understanding, now, row["id"]))
    conn.commit(); conn.close()
    return {"ok": True, "updated_at": now}


# ─── TK ─────────────────────────────────────────────────

MIN_CONTENT_LEN = 80
_DATE_PAT = re.compile(r'(\d{4}-\d{2}-\d{2})')
_DATE_PAT2 = re.compile(r'(\d{4})(\d{2})(\d{2})')

def _extract_date(text: str) -> str:
    """从文本中提取并正规化日期为 YYYY-MM-DD"""
    m = _DATE_PAT.search(text or '')
    if m: return m.group(1)
    m = _DATE_PAT2.search(text or '')
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ''


def _clean_tk_content(body: str) -> str:
    """清理 TK 正文：去掉 frontmatter/导入元信息，过滤导入失败留下的 @/tmp 指针。"""
    text = (body or "").strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2].strip()
    lines = text.split("\n")
    meta_prefixes = ("📰", "👤", "📅", "🔗")
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(meta_prefixes):
            start = i + 1
            continue
        break
    text = "\n".join(lines[start:]).strip()
    if text.startswith("@/tmp/") or text.startswith("/tmp/"):
        return ""
    return text

@app.get("/api/tk/search")
def search_tk(q: str = Query(...), team: str = Query(None), limit: int = Query(20)):
    import requests
    query = q
    if team: query = f"{team} {q}"
    raws = []
    try:
        resp = requests.post(RAG_API, json={"query": query, "top_k": limit * 2}, timeout=10)
        resp.raise_for_status()
        raws = resp.json().get("results", [])
    except Exception: pass

    seen = set()
    merged = []
    for r in raws:
        key = r.get("title", "")
        text = _clean_tk_content(r.get("text", "") or "")
        if key in seen: continue
        if len(text.strip()) < MIN_CONTENT_LEN: continue
        seen.add(key)
        date = _extract_date(r.get("date", "") + " " + text)
        merged.append({
            "id": key, "concept": key[:80], "content": text[:800],
            "date": date, "source": r.get("author", ""),
            "source_type": r.get("source_type", "rag"), "strength": 0, "tags": [],
        })

    for r in _search_tk_files(q, team, limit):
        if r["id"] not in seen:
            seen.add(r["id"])
            merged.append(r)

    # 按日期降序（最新在前），无日期排最后
    merged.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)
    return {"results": merged[:limit]}


def _strip_meta_header(body: str) -> str:
    lines = body.split("\n")
    meta_emojis = {"📰", "👤", "📅", "🔗"}
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(em) for em in meta_emojis):
            start = i + 1
            continue
        break
    while start < len(lines) and not lines[start].strip():
        start += 1
    return "\n".join(lines[start:]).strip()


def _search_tk_files(q: str, team: str, limit: int):
    results = []
    if not os.path.exists(TK_DIR): return results
    ql = q.lower(); kws = ql.split(); tu = team.upper() if team else None
    for fname in sorted(os.listdir(TK_DIR), reverse=True):
        if not fname.endswith(".md"): continue
        fpath = os.path.join(TK_DIR, fname)
        try:
            with open(fpath) as f: content = f.read()
        except: continue
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content.strip()
        clean_body = _clean_tk_content(body)
        if len(clean_body) < MIN_CONTENT_LEN: continue
        if tu and tu not in fname.upper() and tu not in content[:500].upper(): continue
        cl = content.lower(); score = sum(1 for kw in kws if kw in cl)
        if score == 0 and q.strip(): continue
        source = ""; date = ""; tags = []
        for line in content[:1000].split("\n"):
            line = line.strip()
            if line.startswith("source:"): source = line.replace("source:", "").strip()
            elif line.startswith("created:"): date = _extract_date(line.replace("created:", "").strip())
            elif line.startswith("tags:"): tags = [t.strip() for t in line.replace("tags:", "").strip().strip("[]").split(",")[:5]]
        concept = fname
        if "【结论】" in content:
            concept = content[content.index("【结论】"):content.index("\n", content.index("【结论】"))][:80]
        results.append({"id": hashlib.md5(fpath.encode()).hexdigest()[:12],
                         "concept": concept.replace(".md", ""), "content": clean_body[:800],
                         "date": date, "source": source, "source_type": "file",
                         "strength": score * 20, "tags": tags, "filename": fname})
        if len(results) >= limit * 2: break
    return results[:limit]


def _safe_tk_filename(filename: str) -> str:
    """Return a basename-only TK filename under TK_DIR, or reject path traversal."""
    safe = os.path.basename(filename or "")
    if not safe or safe != filename or not safe.endswith(".md"):
        raise HTTPException(400, "非法 TK 文件名")
    return safe


def _tk_markdown(data: dict, *, source: str = "手动录入", created: str | None = None) -> str:
    content = data.get("content", "")
    tags = data.get("tags", "")
    team = data.get("team", "")
    player = data.get("player", "")
    tag_list = []
    if team:
        tag_list.append(f"队伍:{team}")
    if player:
        tag_list.append(f"选手:{player}")
    if isinstance(tags, str) and tags:
        tag_list.extend(t.strip() for t in tags.split(",") if t.strip())
    if not tag_list:
        tag_list.append("通用")
    date_str = created or datetime.now().strftime("%Y-%m-%d")
    return f"---\nsource: {source}\nsource_type: manual\ntags: [{', '.join(tag_list)}]\ncreated: {date_str}\n---\n\n{content}\n"


@app.post("/api/tk")
def create_tk(data: dict):
    content = data.get("content", ""); source = data.get("source", "手动录入")
    if not content or len(content.strip()) < 10: raise HTTPException(400, "内容太短")
    os.makedirs(TK_DIR, exist_ok=True)
    title = content.strip().split("\n")[0][:60]
    fname = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', title)[:50].strip("_") or "untitled"
    fname = f"manual_{hash(content) % 10000}_{fname}.md"
    md = _tk_markdown(data, source=source)
    fpath = os.path.join(TK_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f: f.write(md)
    try:
        import requests; requests.post(REINDEX_API, json={"force": False}, timeout=3)
    except: pass
    return {"ok": True, "filename": fname, "path": fpath}


@app.put("/api/tk/{filename}")
def update_tk(filename: str, data: dict):
    safe = _safe_tk_filename(filename)
    fpath = os.path.join(TK_DIR, safe)
    if not os.path.exists(fpath):
        raise HTTPException(404, "TK 条目未找到")
    content = data.get("content", "")
    source = data.get("source", "手动录入")
    if not content or len(content.strip()) < 10:
        raise HTTPException(400, "内容太短")
    created = None
    try:
        with open(fpath, encoding="utf-8") as f:
            old = f.read(1000)
        for line in old.split("\n"):
            if line.strip().startswith("created:"):
                created = _extract_date(line.replace("created:", "").strip()) or None
                break
    except Exception:
        created = None
    md = _tk_markdown(data, source=source, created=created)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md)
    try:
        import requests; requests.post(REINDEX_API, json={"force": False}, timeout=3)
    except: pass
    return {"ok": True, "filename": safe, "path": fpath}


@app.delete("/api/tk/{filename}")
def delete_tk(filename: str):
    safe = _safe_tk_filename(filename)
    fpath = os.path.join(TK_DIR, safe)
    if not os.path.exists(fpath): raise HTTPException(404, "TK 条目未找到")
    os.remove(fpath)
    try:
        import requests; requests.post(REINDEX_API, json={"force": False}, timeout=3)
    except: pass
    return {"ok": True}


def _strip_wiki_frontmatter(md: str) -> str:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return md.strip()


def _wiki_path(kind: str, name: str) -> str:
    safe = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "-", name.strip().lower()).strip("-")
    return os.path.join(WIKI_DIR, kind, f"{safe}.md")


def _wiki_team_path(team: str) -> str:
    safe = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "-", team.strip().lower()).strip("-")
    return os.path.join(WIKI_DIR, "小雪电竞", "实体画像", "队伍", f"{safe}.md")


def _wiki_concept_path(concept: str) -> str:
    safe = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "-", concept.strip().lower()).strip("-")
    return os.path.join(WIKI_DIR, "小雪电竞", "战术概念", f"{safe}.md")


@app.get("/api/wiki/team/{team}")
def get_wiki_team(team: str):
    team_code = team.upper()
    path = _wiki_team_path(team)
    if not os.path.exists(path):
        return {"found": False, "team": team_code, "path": path, "html": f"<p>暂无 {team_code} 的 Wiki 页面</p>"}
    with open(path, encoding="utf-8") as f:
        md = _strip_wiki_frontmatter(f.read())
    return {"found": True, "team": team_code, "path": path, "markdown": md, "html": _md_to_profile_html(md, team_code)}


@app.get("/api/wiki/concept/{concept}")
def get_wiki_concept(concept: str):
    path = _wiki_concept_path(concept)
    if not os.path.exists(path):
        return {"found": False, "concept": concept, "path": path, "html": f"<p>暂无 {concept} 的 Wiki 概念页</p>"}
    with open(path, encoding="utf-8") as f:
        md = _strip_wiki_frontmatter(f.read())
    return {"found": True, "concept": concept, "path": path, "markdown": md, "html": _md_to_profile_html(md, concept)}


# ─── Profile Full (Wiki first, SKILL.md fallback) ─────────

@app.get("/api/profile-full/{team}")
def get_profile_full(team: str):
    wiki = get_wiki_team(team)
    if wiki.get("found"):
        return {**wiki, "source": "wiki"}

    team_lower = team.lower()
    skill_path = os.path.join(SKILL_DIR_MAIN, f"{team_lower}-team-profile", "SKILL.md")
    if not os.path.exists(skill_path):
        alt_path = os.path.expanduser(f"~/.hermes/hermes-agent/skills/{team_lower}-team-profile/SKILL.md")
        if not os.path.exists(alt_path):
            return {"found": False, "team": team.upper(), "html": f"<p>暂无 {team} 的完整画像（SKILL.md 不存在）</p>"}
        skill_path = alt_path

    with open(skill_path, encoding="utf-8") as f:
        raw = f.read()

    parts = raw.split("---", 2)
    md = parts[2].strip() if len(parts) >= 3 else raw

    html = _md_to_profile_html(md, team.upper())
    return {"found": True, "team": team.upper(), "html": html}


# ─── Fundamentals aggregation ─────────────────────────────

def _text_summary(text: str, limit: int = 96) -> str:
    text = re.sub(r"[#>*`\[\]_|-]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _team_profile_markdown(team: str) -> str:
    path = _wiki_team_path(team)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return _strip_wiki_frontmatter(f.read())
        except Exception:
            return ""
    return ""


def _team_tk_count(team: str) -> int:
    if not os.path.isdir(TK_DIR):
        return 0
    tu = (team or "").upper()
    count = 0
    for fname in os.listdir(TK_DIR):
        if not fname.endswith(".md"):
            continue
        if tu and tu in fname.upper():
            count += 1
            continue
        try:
            with open(os.path.join(TK_DIR, fname), encoding="utf-8") as f:
                head = f.read(800).upper()
            if tu in head:
                count += 1
        except Exception:
            continue
    return count


def _team_starter_cards(conn, team_id: str) -> list[dict]:
    """Lightweight player cards from roster source only; never infer missing facts."""
    if not team_id:
        return []
    rows = conn.execute("""
        SELECT player_name, role, position, is_starter, status
        FROM rosters
        WHERE team_id = ? AND status = 'active'
        ORDER BY is_starter DESC,
                 CASE COALESCE(role, position)
                   WHEN '上单' THEN 1 WHEN 'TOP' THEN 1
                   WHEN '打野' THEN 2 WHEN 'JUNGLE' THEN 2
                   WHEN '中单' THEN 3 WHEN 'MID' THEN 3
                   WHEN 'ADC' THEN 4 WHEN 'BOT' THEN 4
                   WHEN '辅助' THEN 5 WHEN 'SUPPORT' THEN 5
                   ELSE 9 END,
                 player_name
        LIMIT 8
    """, (team_id,)).fetchall()
    cards = []
    for r in rows:
        role = r["role"] or r["position"] or "位置暂无数据"
        status = "首发" if r["is_starter"] else "轮换/替补"
        cards.append({
            "name": r["player_name"] or "暂无数据",
            "role": role,
            "status": status,
        })
    return cards


def _scope_where(scope: str):
    scope = (scope or "all").lower()
    if scope == "lpl":
        return "t.region = ?", ["LPL"]
    if scope == "lck":
        return "t.region = ?", ["LCK"]
    if scope == "intl":
        return "t.region = ?", ["INTL"]
    if scope == "msi":
        return "t.short_name IN (SELECT team FROM msi_ts_seed)", []
    return "1=1", []


@app.get("/api/fundamentals/teams")
def fundamentals_teams(scope: str = Query("all"), limit: int = Query(80)):
    """横向基本面队伍表 — 聚合 teams / 3D / wiki / TK 状态。"""
    conn = get_db()
    where, params = _scope_where(scope)
    order_by = "seed.final_seed_mu DESC" if (scope or "").lower() == "msi" else "CASE WHEN t.region='LPL' THEN 0 WHEN t.region='LCK' THEN 1 WHEN t.region='INTL' THEN 2 ELSE 3 END, t.short_name"
    rows = conn.execute(f"""
        SELECT t.short_name, t.name, t.team_id, t.region, t.league_id,
               t.mu, t.sigma,
               seed.final_seed_mu, seed.seed_sigma, seed.seed_ts, seed.outright_odds_decimal,
               d.dim_1_name, d.dim_1_value, d.dim_2_name, d.dim_2_value,
               d.dim_3_name, d.dim_3_value, d.notes, d.version_understanding, d.updated_at
        FROM teams t
        LEFT JOIN msi_ts_seed seed ON seed.team = t.short_name
        LEFT JOIN team_3d_data d ON d.id = (
            SELECT id FROM team_3d_data dd
            WHERE dd.team_name = t.short_name
            ORDER BY dd.updated_at DESC LIMIT 1
        )
        WHERE {where}
          AND (t.short_name IS NOT NULL AND t.short_name != '')
        ORDER BY {order_by}
        LIMIT ?
    """, params + [limit]).fetchall()

    teams = []
    for r in rows:
        code = r["short_name"]
        profile_md = _team_profile_markdown(code)
        has_profile = bool(profile_md)
        tk_count = _team_tk_count(code)
        has_3d = bool(r["dim_1_value"] or r["dim_2_value"] or r["dim_3_value"])
        players = _team_starter_cards(conn, r["team_id"])
        if has_profile and has_3d and tk_count:
            quality = "完整"
        elif has_profile or has_3d or tk_count:
            quality = "部分"
        else:
            quality = "资料不足"
        teams.append({
            "short_name": code,
            "name": r["name"] or code,
            "team_id": r["team_id"],
            "region": r["region"] or "",
            "league_id": r["league_id"] or "",
            "mu": r["mu"],
            "sigma": r["sigma"],
            "ts_score": round((r["mu"] or 25) - 3 * (r["sigma"] or 8.333), 3),
            "odds": r["outright_odds_decimal"],
            "seed_mu": r["final_seed_mu"],
            "seed_sigma": r["seed_sigma"],
            "seed_ts": r["seed_ts"],
            "has_profile": has_profile,
            "has_3d": has_3d,
            "has_tk": tk_count > 0,
            "tk_count": tk_count,
            "players": players,
            "players_note": "首发/关键选手来自 rosters；缺数据不推断" if players else "资料缺口/暂无数据",
            "dim_1_name": r["dim_1_name"] or "优势局",
            "dim_1_value": r["dim_1_value"] or "-",
            "dim_2_name": r["dim_2_name"] or "劣势局",
            "dim_2_value": r["dim_2_value"] or "-",
            "dim_3_name": r["dim_3_name"] or "胜负手",
            "dim_3_value": r["dim_3_value"] or "-",
            "notes_summary": _text_summary(r["notes"] or profile_md, 110),
            "version_summary": _text_summary(r["version_understanding"] or "", 90),
            "updated_at": r["updated_at"] or "",
            "data_quality": quality,
        })
    conn.close()
    return {"scope": scope, "teams": teams}


@app.get("/api/fundamentals/msi")
def fundamentals_msi():
    """MSI 国际赛环境 — 队伍池、赛区分布、资料缺口，不作为赛程表主入口。"""
    team_data = fundamentals_teams(scope="msi", limit=120)["teams"]
    region_counts = {}
    missing_profiles = []
    missing_3d = []
    for t in team_data:
        region_counts[t["region"] or "UNKNOWN"] = region_counts.get(t["region"] or "UNKNOWN", 0) + 1
        if not t["has_profile"]:
            missing_profiles.append(t["short_name"])
        if not t["has_3d"]:
            missing_3d.append(t["short_name"])
    key_topics = ["跨赛区强弱", "外卡未知量", "版本理解差", "BO 稳定性", "资料缺口"]
    return {
        "event": "MSI",
        "positioning": "国际赛环境研究，不是赛程表",
        "teams": team_data,
        "regions": region_counts,
        "missing_profiles": missing_profiles,
        "missing_3d": missing_3d,
        "key_topics": key_topics,
    }


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt_num(v, digits=1):
    return f"{_num(v):.{digits}f}"


def _ts_team_context(row):
    if not row:
        return None
    mu = _num(row["final_seed_mu"], _num(row["mu"], 25))
    sigma = _num(row["seed_sigma"], _num(row["sigma"], 8.333))
    ts = _num(row["seed_ts"], mu - 3 * sigma)
    risk_gap = round(mu - ts, 3)
    if sigma <= 1.2:
        volatility = "低波动"
    elif sigma <= 3.5:
        volatility = "中波动"
    elif sigma <= 5.2:
        volatility = "高波动"
    else:
        volatility = "极高波动"
    confidence = "高样本" if (row["region"] or "") in {"LPL", "LCK"} and sigma <= 1.5 else ("中样本" if sigma <= 5.0 else "低样本")
    return {
        "team": row["short_name"],
        "display_name": row["name"] or row["short_name"],
        "region": row["region"] or "",
        "odds": row["outright_odds_decimal"],
        "mu": round(mu, 3),
        "sigma": round(sigma, 3),
        "ts": round(ts, 3),
        "risk_gap": risk_gap,
        "volatility_tier": volatility,
        "sample_confidence": confidence,
        "note": row["note"] or "",
    }


def _load_ts_team(conn, team: str):
    code = (team or "").strip().upper()
    if not code:
        return None
    return conn.execute("""
        SELECT t.short_name, t.name, t.region, t.mu, t.sigma,
               seed.final_seed_mu, seed.seed_sigma, seed.seed_ts,
               seed.outright_odds_decimal, seed.note
        FROM teams t
        LEFT JOIN msi_ts_seed seed ON seed.team = t.short_name
        WHERE UPPER(t.short_name) = ? OR UPPER(t.name) = ? OR UPPER(seed.display_name) = ?
        LIMIT 1
    """, (code, code, code)).fetchone()


def _diff_line(label, value, strong_side, threshold=0.0):
    if abs(value) <= threshold:
        return f"{label}接近"
    return f"{strong_side} {label}领先 {_fmt_num(abs(value))}"


def _build_msi_match_context(team_a_ctx, team_b_ctx):
    mu_diff = round(team_a_ctx["mu"] - team_b_ctx["mu"], 3)
    sigma_diff = round(team_a_ctx["sigma"] - team_b_ctx["sigma"], 3)
    ts_diff = round(team_a_ctx["ts"] - team_b_ctx["ts"], 3)
    stronger = team_a_ctx["team"] if mu_diff >= 0 else team_b_ctx["team"]
    weaker = team_b_ctx["team"] if mu_diff >= 0 else team_a_ctx["team"]
    more_volatile = team_a_ctx["team"] if sigma_diff >= 0 else team_b_ctx["team"]
    less_volatile = team_b_ctx["team"] if sigma_diff >= 0 else team_a_ctx["team"]

    if abs(mu_diff) >= 4:
        power_note = f"{stronger} 绝对实力明显领先，{weaker} 需要靠版本/BP/临场波动制造空间。"
    elif abs(mu_diff) >= 2:
        power_note = f"{stronger} 实力有优势，但不是碾压档，盘口不能只按强弱简单处理。"
    else:
        power_note = "两队实力差不大，单场更看版本适配、BP 和当天状态。"

    if abs(sigma_diff) >= 2.5:
        volatility_note = f"{more_volatile} 波动明显更大，意味着上限/下限都更散；{less_volatile} 更偏稳定兑现。"
    elif max(team_a_ctx["sigma"], team_b_ctx["sigma"]) >= 4.5:
        volatility_note = "这场至少一边处于高波动区，日报里要提示爆冷/让盘风险，不要只看实力。"
    else:
        volatility_note = "两边波动都不高，TS 参考价值相对稳定。"

    market_note = "赔率只作市场位置参考：日报里重点对照实力差和波动差，判断市场有没有把强队热度或弱队爆冷空间打满。"
    daily_summary = f"TS参考：{team_a_ctx['team']} mu {_fmt_num(team_a_ctx['mu'])} / σ {_fmt_num(team_a_ctx['sigma'])} / TS {_fmt_num(team_a_ctx['ts'])}；{team_b_ctx['team']} mu {_fmt_num(team_b_ctx['mu'])} / σ {_fmt_num(team_b_ctx['sigma'])} / TS {_fmt_num(team_b_ctx['ts'])}。{power_note}{volatility_note}"
    risk_note = f"关注点：{_diff_line('实力', mu_diff, stronger, 0.8)}；{_diff_line('波动', sigma_diff, more_volatile, 0.4)}；保守下界差 {_fmt_num(abs(ts_diff))} 偏向 {team_a_ctx['team'] if ts_diff >= 0 else team_b_ctx['team']}。"

    return {
        "mu_diff": mu_diff,
        "sigma_diff": sigma_diff,
        "ts_diff": ts_diff,
        "stronger": stronger,
        "more_volatile": more_volatile,
        "power_note": power_note,
        "volatility_note": volatility_note,
        "market_note": market_note,
        "risk_note": risk_note,
        "daily_summary": daily_summary,
    }


@app.get("/api/fundamentals/msi-match-context")
def fundamentals_msi_match_context(team_a: str = Query(...), team_b: str = Query(...)):
    """MSI 日报用 TS 单场对比：只做参考底表，不自动给交易结论。"""
    conn = get_db()
    row_a = _load_ts_team(conn, team_a)
    row_b = _load_ts_team(conn, team_b)
    conn.close()
    if not row_a or not row_b:
        missing = [name for name, row in [(team_a, row_a), (team_b, row_b)] if not row]
        raise HTTPException(404, f"MSI TS 队伍未找到：{', '.join(missing)}")
    ctx_a = _ts_team_context(row_a)
    ctx_b = _ts_team_context(row_b)
    return {
        "event": "MSI",
        "team_a": ctx_a,
        "team_b": ctx_b,
        "compare": _build_msi_match_context(ctx_a, ctx_b),
    }


def _md_to_profile_html(md: str, team: str) -> str:
    lines = md.split("\n")
    out = []
    in_table = False; in_list = False; in_code = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            if in_code:
                out.append('<pre class="code-block">')
            else:
                out.append('</pre>')
            continue
        if in_code:
            out.append(f'{line}\n')
            continue

        if "|" in stripped and "---" in stripped.replace(" ", ""):
            continue

        if stripped.startswith("# "):
            out.append(f'<h1>{stripped[2:]}</h1>')
        elif stripped.startswith("## "):
            out.append(f'<h2>{stripped[3:]}</h2>')
        elif stripped.startswith("### "):
            out.append(f'<h3>{stripped[4:]}</h3>')
        elif stripped.startswith("#### "):
            out.append(f'<h4>{stripped[5:]}</h4>')
        elif stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            if not in_table:
                out.append(f'<table><thead><tr>{row}</tr></thead><tbody>')
                in_table = True
            else:
                out.append(f"<tr>{row}</tr>")
        elif in_table:
            out.append("</tbody></table>")
            in_table = False
            if stripped.startswith("- "):
                if not in_list: out.append("<ul>"); in_list = True
                out.append(f"<li>{stripped[2:]}</li>")
            elif stripped.startswith("> "):
                out.append(f'<blockquote>{stripped[2:]}</blockquote>')
            elif stripped:
                out.append(f"<p>{stripped}</p>")
            else:
                if in_list: out.append("</ul>"); in_list = False
        elif stripped.startswith("- "):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{stripped[2:]}</li>")
        elif stripped.startswith("> "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f'<blockquote>{stripped[2:]}</blockquote>')
        elif stripped == "---":
            if in_list: out.append("</ul>"); in_list = False
            if in_table: out.append("</tbody></table>"); in_table = False
            out.append("<hr>")
        elif stripped:
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p>{stripped}</p>")
        else:
            if in_list: out.append("</ul>"); in_list = False

    if in_table: out.append("</tbody></table>")
    if in_list: out.append("</ul>")
    if in_code: out.append("</pre>")

    return "\n".join(out)


# ─── Analyst (LLM-powered) ──────────────────────────────

def _gather_team_data(team: str) -> dict:
    """Assemble all available team data for analysis"""
    conn = get_db()
    # 3D data
    d3 = conn.execute(
        "SELECT * FROM team_3d_data WHERE team_name=? ORDER BY updated_at DESC LIMIT 1",
        (team,)
    ).fetchone()
    # Team info
    t = conn.execute("SELECT name, region FROM teams WHERE short_name=?", (team,)).fetchone()
    conn.close()

    data = {"team": team, "name": t["name"] if t else team, "region": t["region"] if t else ""}

    if d3:
        data["dim_1"] = f"{d3['dim_1_name']}: {d3['dim_1_value']}"
        data["dim_2"] = f"{d3['dim_2_name']}: {d3['dim_2_value']}"
        data["dim_3"] = f"{d3['dim_3_name']}: {d3['dim_3_value']}"
        data["notes"] = d3["notes"] or ""
        data["version_understanding"] = d3["version_understanding"] or ""

    # Profile (abbreviated)
    profile_path = os.path.join(SKILL_DIR_MAIN, f"{team.lower()}-team-profile", "SKILL.md")
    if os.path.exists(profile_path):
        raw = open(profile_path, encoding="utf-8").read()
        data["profile"] = raw[:3000]  # First 3000 chars for context

    # Recent TK items
    tk_files = []
    if os.path.isdir(TK_DIR):
        for f in sorted(os.listdir(TK_DIR), reverse=True):
            fp = os.path.join(TK_DIR, f)
            if not f.endswith(".md"): continue
            content = open(fp, encoding="utf-8").read()
            if team in content[:200]:
                tk_files.append(f"{f}: {content[:400]}")
            if len(tk_files) >= 5:
                break
    data["tk_samples"] = "\n".join(tk_files) if tk_files else "（无相关TK）"

    return data


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call DeepSeek API and return response text"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(LLM_URL, json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1200,
        }, headers={
            "Authorization": f"Bearer {LLM_KEY}",
            "Content-Type": "application/json",
        })
        if resp.status_code != 200:
            return f"LLM 调用失败 (HTTP {resp.status_code})"
        data = resp.json()
        return data["choices"][0]["message"]["content"]


@app.get("/api/analyst/{team}")
async def get_analyst(team: str, analyst: str = Query("")):
    """Analyze team using zhongnian-esports-coach / xinyu-tactical-analyst frameworks"""
    tdata = _gather_team_data(team)

    # Build data snapshot
    snapshot = f"""队伍：{tdata['name']} ({tdata['region']}-{tdata['team']})
三维数据：{tdata.get('dim_1','N/A')} | {tdata.get('dim_2','N/A')} | {tdata.get('dim_3','N/A')}
战术笔记：{tdata.get('notes','无')}
版本理解：{tdata.get('version_understanding','无')}
近期TK：
{tdata.get('tk_samples','无')}
画像摘要：{tdata.get('profile','无')}"""

    async def run_zhongnian():
        if analyst and analyst != "中年电竞人":
            return None
        system = f"""你是「中年电竞人」——一位资深LOL教练，擅长BP评估、选手状态判断、体系有效性检验。

你的分析框架如下（必须严格遵循每一条）：
{SKILL_ZHONGNIAN}

输出要求：用你的「控制层级」「预制大脑」「选手评估二元法」「体系锚点理论」四个维度，逐一分析这支队伍。给出具体的打分和判断。用生活化比喻（老干部退休、葫芦娃救爷爷、肌肉梆硬等）。200-400字。"""
        return "中年电竞人", await _call_llm(system, snapshot)

    async def run_xinyu():
        if analyst and analyst != "心语悦无言":
            return None
        system = f"""你是「心语悦无言」——一位LOL战术分析师，擅长体系框架拆解、阵容构建分析、回合概念建模。

你的分析框架如下（必须严格遵循每一条）：
{SKILL_XINYU}

输出要求：用你的「阵容构建核心链」「决策/操作分离」「回合概念」「三大体系定位」四个维度，逐一分析这支队伍。指出结构性缺陷和战术优势。200-400字。"""
        return "心语悦无言", await _call_llm(system, snapshot)

    tasks = [t for t in [run_zhongnian(), run_xinyu()] if t is not None]
    results = await asyncio.gather(*tasks)

    content = {}
    for r in results:
        if r:
            name, text = r
            content[name] = text

    if not content:
        return {"found": False, "content": "", "msg": f"暂无 {team} 的分析数据"}

    if analyst and analyst in content:
        return {"found": True, "analyst": analyst, "content": content[analyst]}

    return {"found": True, "content": content}


# ─── Sidebar links ──────────────────────────────────────

@app.get("/api/links")
def get_links(team: str = Query("")):
    links = [
        {"label": "TK 概念图", "url": "http://42.193.177.127:8768/tk-graph", "desc": "力导向关系图"},
        {"label": "知识库面板", "url": "http://42.193.177.127:8768/dashboard", "desc": "TK 统计看板"},
        {"label": "日报列表", "url": "/reports/", "desc": "历史日报"},
    ]
    if team:
        links.append({"label": f"{team} 赛前分析", "url": f"http://42.193.177.127:8768/prematch?team={team}", "desc": "赛前舆论+BP预测"})
    links.append({"label": "版本理解", "url": "http://42.193.177.127:8768/version", "desc": "当前版本体系"})
    links.append({"label": "战力排行", "url": "http://42.193.177.127:8768/ranking", "desc": "ELO 实时排名"})
    return {"links": links}




# ─── Market notes / Lightweight Trade Records ─────────────

TRADE_GAMES = {"lol", "cs", "valorant", "football"}
TRADE_RESULTS = {"未结算", "赢", "输", "走水"}

def init_market_notes_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL DEFAULT 'lol',
            match_name TEXT NOT NULL,
            match_time TEXT DEFAULT '',
            direction TEXT DEFAULT '',
            total_lean TEXT DEFAULT '放弃',
            score_note TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            confidence TEXT DEFAULT '中',
            review TEXT DEFAULT '',
            linked_team TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_notes_game_time ON market_notes(game, match_time, created_at)")
    conn.commit(); conn.close()

@app.on_event("startup")
def _init_market_notes():
    init_market_notes_table()

class MarketNoteIn(BaseModel):
    game: str = "lol"
    match_name: str
    match_time: str = ""
    direction: str = ""
    total_lean: str = "放弃"
    score_note: str = ""
    reason: str = ""
    confidence: str = "中"
    review: str = ""
    linked_team: str = ""

class MarketNoteUpdate(BaseModel):
    game: str = None
    match_name: str = None
    match_time: str = None
    direction: str = None
    total_lean: str = None
    score_note: str = None
    reason: str = None
    confidence: str = None
    review: str = None
    linked_team: str = None

def _market_row(r):
    return {
        "id": r["id"], "game": r["game"], "match_name": r["match_name"], "match_time": r["match_time"] or "",
        "direction": r["direction"] or "", "total_lean": r["total_lean"] or "放弃", "score_note": r["score_note"] or "",
        "reason": r["reason"] or "", "confidence": r["confidence"] or "中", "review": r["review"] or "",
        "linked_team": r["linked_team"] or "", "created_at": r["created_at"], "updated_at": r["updated_at"],
    }

@app.get("/api/market-notes")
def list_market_notes(game: str = Query(""), limit: int = Query(30)):
    init_market_notes_table()
    conn = get_db()
    wheres = []
    params = []
    if game:
        wheres.append("game = ?")
        params.append(_normalize_game(game))
    where_clause = "WHERE " + " AND ".join(wheres) if wheres else ""
    rows = conn.execute(f"""
        SELECT * FROM market_notes
        {where_clause}
        ORDER BY COALESCE(NULLIF(match_time, ''), created_at) DESC, id DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return {"records": [_market_row(r) for r in rows]}

@app.post("/api/market-notes")
def create_market_note(data: MarketNoteIn):
    init_market_notes_table()
    match_name = (data.match_name or "").strip()
    if not match_name:
        raise HTTPException(400, "对象不能为空")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO market_notes (game, match_name, match_time, direction, total_lean, score_note, reason, confidence, review, linked_team, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (_normalize_game(data.game), match_name, data.match_time, data.direction, data.total_lean, data.score_note, data.reason, data.confidence, data.review, data.linked_team, now, now))
    conn.commit()
    row = conn.execute("SELECT * FROM market_notes WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {"ok": True, "record": _market_row(row)}

@app.delete("/api/market-notes/{note_id}")
def delete_market_note(note_id: int):
    init_market_notes_table()
    conn = get_db()
    cur = conn.execute("DELETE FROM market_notes WHERE id=?", (note_id,))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "记录不存在")
    return {"ok": True}

def init_trade_records_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL DEFAULT 'lol',
            match_name TEXT NOT NULL,
            match_time TEXT DEFAULT '',
            pick_winner TEXT DEFAULT '放弃',
            pick_total TEXT DEFAULT '放弃',
            score_pick TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            confidence TEXT DEFAULT '中',
            result TEXT DEFAULT '未结算',
            review TEXT DEFAULT '',
            linked_team TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_game_time ON trade_records(game, match_time, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_result ON trade_records(result)")
    conn.commit(); conn.close()

@app.on_event("startup")
def _init_trade_records():
    init_trade_records_table()

class TradeRecordIn(BaseModel):
    game: str = "lol"
    match_name: str
    match_time: str = ""
    pick_winner: str = "放弃"
    pick_total: str = "放弃"
    score_pick: str = ""
    reason: str = ""
    confidence: str = "中"
    result: str = "未结算"
    review: str = ""
    linked_team: str = ""

class TradeRecordUpdate(BaseModel):
    game: str = None
    match_name: str = None
    match_time: str = None
    pick_winner: str = None
    pick_total: str = None
    score_pick: str = None
    reason: str = None
    confidence: str = None
    result: str = None
    review: str = None
    linked_team: str = None

def _normalize_game(game: str) -> str:
    value = (game or "lol").strip().lower()
    aliases = {"英雄联盟": "lol", "联盟": "lol", "无畏": "valorant", "无畏契约": "valorant", "瓦": "valorant", "足球": "football"}
    value = aliases.get(value, value)
    if value not in TRADE_GAMES:
        value = "lol"
    return value

def _trade_row(r):
    return {
        "id": r["id"], "game": r["game"], "match_name": r["match_name"], "match_time": r["match_time"] or "",
        "pick_winner": r["pick_winner"] or "放弃", "pick_total": r["pick_total"] or "放弃", "score_pick": r["score_pick"] or "",
        "reason": r["reason"] or "", "confidence": r["confidence"] or "中", "result": r["result"] or "未结算", "review": r["review"] or "",
        "linked_team": r["linked_team"] or "", "created_at": r["created_at"], "updated_at": r["updated_at"],
    }

@app.get("/api/trades")
def list_trades(game: str = Query(""), result: str = Query(""), limit: int = Query(30)):
    init_trade_records_table()
    conn = get_db()
    wheres = []
    params = []
    if game:
        wheres.append("game = ?")
        params.append(_normalize_game(game))
    if result:
        wheres.append("result = ?")
        params.append(result)
    where_clause = "WHERE " + " AND ".join(wheres) if wheres else ""
    rows = conn.execute(f"""
        SELECT * FROM trade_records
        {where_clause}
        ORDER BY COALESCE(NULLIF(match_time, ''), created_at) DESC, id DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return {"records": [_trade_row(r) for r in rows]}

@app.post("/api/trades")
def create_trade(data: TradeRecordIn):
    init_trade_records_table()
    match_name = (data.match_name or "").strip()
    if not match_name:
        raise HTTPException(400, "比赛不能为空")
    game = _normalize_game(data.game)
    result = data.result if data.result in TRADE_RESULTS else "未结算"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO trade_records (game, match_name, match_time, pick_winner, pick_total, score_pick, reason, confidence, result, review, linked_team, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (game, match_name, data.match_time, data.pick_winner, data.pick_total, data.score_pick, data.reason, data.confidence, result, data.review, data.linked_team, now, now))
    conn.commit()
    row = conn.execute("SELECT * FROM trade_records WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {"ok": True, "record": _trade_row(row)}

@app.put("/api/trades/{trade_id}")
def update_trade(trade_id: int, data: TradeRecordUpdate):
    init_trade_records_table()
    allowed = ["game", "match_name", "match_time", "pick_winner", "pick_total", "score_pick", "reason", "confidence", "result", "review", "linked_team"]
    payload = data.dict(exclude_unset=True)
    if "game" in payload:
        payload["game"] = _normalize_game(payload["game"])
    if "result" in payload and payload["result"] not in TRADE_RESULTS:
        payload["result"] = "未结算"
    updates = [(k, payload[k]) for k in allowed if k in payload]
    if not updates:
        raise HTTPException(400, "没有可更新字段")
    conn = get_db()
    if not conn.execute("SELECT id FROM trade_records WHERE id=?", (trade_id,)).fetchone():
        conn.close(); raise HTTPException(404, "记录不存在")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=?" for k, _ in updates) + ", updated_at=?"
    conn.execute(f"UPDATE trade_records SET {set_clause} WHERE id=?", [v for _, v in updates] + [now, trade_id])
    conn.commit()
    row = conn.execute("SELECT * FROM trade_records WHERE id=?", (trade_id,)).fetchone()
    conn.close()
    return {"ok": True, "record": _trade_row(row)}

@app.delete("/api/trades/{trade_id}")
def delete_trade(trade_id: int):
    init_trade_records_table()
    conn = get_db()
    cur = conn.execute("DELETE FROM trade_records WHERE id=?", (trade_id,))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "记录不存在")
    return {"ok": True}

@app.get("/api/trades/stats")
def trade_stats(game: str = Query("")):
    init_trade_records_table()
    conn = get_db()
    params = []
    where = ""
    if game:
        where = "WHERE game=?"
        params.append(_normalize_game(game))
    rows = conn.execute(f"SELECT game, result, pick_winner, pick_total FROM trade_records {where}", params).fetchall()
    conn.close()
    total = len(rows)
    settled = [r for r in rows if r["result"] in ("赢", "输", "走水")]
    wins = sum(1 for r in rows if r["result"] == "赢")
    losses = sum(1 for r in rows if r["result"] == "输")
    pushes = sum(1 for r in rows if r["result"] == "走水")
    by_game = {}
    for r in rows:
        g = r["game"]
        by_game.setdefault(g, {"total": 0, "wins": 0, "losses": 0, "pushes": 0})
        by_game[g]["total"] += 1
        if r["result"] == "赢": by_game[g]["wins"] += 1
        if r["result"] == "输": by_game[g]["losses"] += 1
        if r["result"] == "走水": by_game[g]["pushes"] += 1
    return {
        "total": total,
        "settled": len(settled),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": round(wins / len(settled) * 100, 1) if settled else 0,
        "by_game": by_game,
    }


# ─── 今日内容入口 ────────────────────────────────────────


def _daily_content_summary(text: str, max_chars: int = 180) -> str:
    """提取本地内容文件摘要；只处理白名单文件读取结果。"""
    if not text:
        return ""
    lines = []
    in_frontmatter = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not line:
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if line:
            lines.append(line)
        if len(" ".join(lines)) >= max_chars:
            break
    summary = " ".join(lines).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary


@app.get("/api/daily-content")
def get_daily_content(date: str = Query("today")):
    """只读今日内容入口：只接受 today/YYYY-MM-DD，并生成固定白名单路径。"""
    date_str = _resolve_daily_content_date(date)
    daily_content_files = _daily_content_files_for(date_str)
    items = []
    for key, meta in daily_content_files.items():
        path = meta["path"]
        exists = os.path.exists(path)
        stat = os.stat(path) if exists else None
        summary = ""
        if exists:
            try:
                with open(path, encoding="utf-8") as f:
                    summary = _daily_content_summary(f.read(12000))
            except Exception as exc:
                summary = f"摘要读取失败：{exc}"
        items.append({
            "id": key,
            "title": meta["title"],
            "kind": meta["kind"],
            "path": path,
            "exists": exists,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds") if stat else None,
            "size_bytes": stat.st_size if stat else 0,
            "summary": summary,
        })
    return {
        "ok": True,
        "date": date_str,
        "source": "local_whitelist",
        "items": items,
    }


# ─── Static ─────────────────────────────────────────────

# TK 概念图静态文件（力导向图）
_TK_GRAPH_DIR = os.path.expanduser("/home/ubuntu/tk_graph_serve")
app.mount("/tk-graph", StaticFiles(directory=_TK_GRAPH_DIR, html=True), name="tk_graph")

# 挂载构建产物静态文件
_STATIC_DIST = os.path.join(os.path.dirname(__file__), "dist")
app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIST, "assets")), name="dist_assets")


@app.get("/api/health")
def health_check():
    """快速健康检查：给飞书远程排障和 vibe-status 使用。"""
    checks = {}

    try:
        conn = get_db()
        team_count = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
        schedule_count = conn.execute("SELECT COUNT(*) AS n FROM schedules").fetchone()["n"]
        conn.close()
        checks["database"] = {
            "ok": True,
            "path": DB_PATH,
            "teams": team_count,
            "schedules": schedule_count,
        }
    except Exception as exc:
        checks["database"] = {"ok": False, "path": DB_PATH, "error": str(exc)}

    dist_index = os.path.join(os.path.dirname(__file__), "dist", "index.html")
    checks["dist"] = {"ok": os.path.exists(dist_index), "path": dist_index}
    checks["tk_dir"] = {"ok": os.path.isdir(TK_DIR), "path": TK_DIR}
    checks["skill_dirs"] = {
        "ok": os.path.isdir(SKILL_DIR_XIAOBAI) or os.path.isdir(SKILL_DIR_MAIN),
        "xiaobai": os.path.isdir(SKILL_DIR_XIAOBAI),
        "main": os.path.isdir(SKILL_DIR_MAIN),
    }

    ok = all(
        item.get("ok", True) if isinstance(item, dict) else bool(item)
        for item in checks.values()
    )
    return {
        "ok": ok,
        "service": "xiaoxue-workbench-api",
        "time": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
    }

@app.get("/")
def serve_index():
    dist_index = os.path.join(_STATIC_DIST, "index.html")
    if os.path.exists(dist_index):
        return FileResponse(dist_index)
    return FileResponse("index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)
