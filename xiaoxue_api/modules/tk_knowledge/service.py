from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from xiaoxue_api.modules.team.public import get_team_3d, list_teams

from .models import TradingNoteIn
from . import repository


MIN_CONTENT_LEN = 80
TRADING_NOTE_TYPE = "trading_note"
GENERAL_TRADING_TK_PREFIX = "trading_tk_general_"  # 已有通用词条文件名前缀，继续兼容。
TRADING_TK_PREFIX = "trading_tk_"
TRADING_TK_SCOPES = {"global", "region", "team", "player"}
GENERAL_TRADING_TK_CATEGORIES = {
    "version", "regional_style", "team_style", "player_style",
    "roster", "lineup", "market", "execution", "general", "team",
}
GENERAL_TRADING_TK_STATUSES = {"candidate", "confirmed", "invalid"}
TRADING_TK_SCOPE_LABELS = {"global": "全局", "region": "赛区", "team": "队伍", "player": "选手"}
TRADING_TK_CATEGORY_LABELS = {
    "version": "版本", "regional_style": "赛区风格", "team_style": "队伍特点",
    "player_style": "选手特点", "roster": "换人", "lineup": "阵容",
    "market": "盘口", "execution": "执行", "general": "其他", "team": "队伍特点",
}
_TAG_PREFIXES = ("队伍:", "选手:", "赛区:", "版本:", "比赛:", "游戏:")
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
COMPACT_DATE_PATTERN = re.compile(r"(\d{4})(\d{2})(\d{2})")
CONFIG_PATH = Path(__file__).with_name("config.json")


class InvalidInput(ValueError):
    pass


class EntryNotFound(LookupError):
    pass


class TeamUnconfirmed(LookupError):
    pass


class ModuleUnavailable(RuntimeError):
    pass


def _load_config() -> dict:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ModuleUnavailable("交易 TK 配置不可用") from exc
    if not isinstance(payload, dict):
        raise ModuleUnavailable("交易 TK 配置不可用")
    return payload


def _team_aliases() -> dict[str, str]:
    lookup = {}
    module_config = _load_config().get("tk_knowledge") or {}
    for canonical, aliases in (module_config.get("team_aliases") or {}).items():
        for alias in [canonical, *(aliases or [])]:
            value = str(alias).strip()
            if value:
                lookup[value.casefold()] = str(canonical).strip().upper()
    return lookup


def _market_config() -> dict:
    return ((_load_config().get("tk_knowledge") or {}).get("market") or {})


def normalize_team(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise InvalidInput("队伍不能为空")
    candidate = _team_aliases().get(raw.casefold(), raw).strip().upper()
    try:
        teams = list_teams()
    except Exception as exc:
        raise ModuleUnavailable("队伍资料模块不可用，暂不能确认交易 TK 归属") from exc
    for team in teams:
        values = (team.get("short_name"), team.get("name"), team.get("team_id"))
        if any(str(item or "").strip().casefold() == candidate.casefold() for item in values):
            return str(team.get("short_name") or candidate).upper()
    try:
        existing_3d = get_team_3d(candidate)
    except LookupError:
        existing_3d = None
    if existing_3d:
        return str(existing_3d.get("team_name") or candidate).upper()
    raise EntryNotFound(f"队伍未找到或别名未确认：{raw}")


def _explicit_teams_in_text(text: str) -> list[str]:
    """Return only teams literally named in Junjun's words; never infer from tactics."""
    raw = str(text or "")
    if not raw:
        return []
    candidates: dict[str, set[str]] = {}
    try:
        for row in list_teams():
            canonical = str(row.get("short_name") or row.get("team_id") or "").strip().upper()
            if not canonical:
                continue
            candidates.setdefault(canonical, set()).update(
                str(value or "").strip() for value in (row.get("short_name"), row.get("name"), row.get("team_id"))
            )
        for alias, canonical in _team_aliases().items():
            if canonical:
                candidates.setdefault(canonical.upper(), set()).add(alias)
    except Exception:
        return []
    found = []
    for canonical, aliases in candidates.items():
        for alias in aliases:
            if not alias:
                continue
            if re.fullmatch(r"[A-Za-z0-9._-]+", alias):
                if len(alias) <= 2:
                    matched = bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias.upper())}(?![A-Za-z0-9])", raw))
                else:
                    matched = bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", raw, re.I))
            else:
                matched = alias.casefold() in raw.casefold()
            if matched:
                found.append(canonical)
                break
    return sorted(set(found))


def _extract_date(text: str) -> str:
    match = DATE_PATTERN.search(text or "")
    if match:
        return match.group(1)
    match = COMPACT_DATE_PATTERN.search(text or "")
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


_TECHNICAL_POINTER = re.compile(r"^\s*@?/(?:tmp|home|usr|var)/\S+\s*$")
_TECHNICAL_LOG_LINE = re.compile(r"^\s*(?:Traceback \(|File \".+\", line \d+|Exception:|Error:|INFO:|DEBUG:)" )
_INTERNAL_EVIDENCE_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:证据|路径|文件)\s*[:：]\s*@?/(?:tmp|home|usr|var)/", re.I)


def _clean_content(body: str) -> str:
    """Return only human-readable TK text; never expose internal artifacts."""
    text = (body or "").strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2].strip()
    lines = text.split("\n")
    start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("📰", "👤", "📅", "🔗")):
            start = index + 1
            continue
        break

    cleaned, in_code_block = [], False
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or _TECHNICAL_POINTER.fullmatch(stripped):
            continue
        if _TECHNICAL_LOG_LINE.match(stripped) or _INTERNAL_EVIDENCE_LINE.match(stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _concept(filename: str, content: str) -> str:
    index = content.find("【结论】")
    if index < 0:
        return filename
    end = content.find("\n", index)
    if end < 0:
        end = min(len(content), index + 120)
    return content[index:end][:80]


def _frontmatter(content: str) -> dict:
    fields = {"source": "", "team": "", "player": "", "tags": [], "type": ""}
    if not content.startswith("---"):
        return fields
    parts = content.split("---", 2)
    if len(parts) < 3:
        return fields
    for raw_line in parts[1].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"\'')
        if key == "tags":
            fields["tags"] = [item.strip() for item in value.strip("[]").split(",") if item.strip()][:8]
        elif key in fields:
            fields[key] = value
    return fields


def _library_record(document: dict) -> dict | None:
    raw = document["content"]
    content = _clean_content(raw)
    if len(content) < 10:
        return None
    fields = _frontmatter(raw)
    if fields.get("type") == "trading_note" or document["filename"].startswith("trading_tk_"):
        record_type = "trading_tk"
    elif "交易" in fields["tags"]:
        record_type = "legacy_trade_label"
    else:
        record_type = "knowledge_tk"
    date = ""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        for line in parts[1].splitlines() if len(parts) >= 3 else []:
            if line.strip().lower().startswith("created:"):
                date = _extract_date(line)
                break
    if not date:
        date = datetime.fromtimestamp(document["mtime"]).strftime("%Y-%m-%d")
    conclusion = re.search(r"【结论】\s*([^\n【]+)", content)
    if conclusion and conclusion.group(1).strip():
        concept = f"【结论】{conclusion.group(1).strip()}"[:140]
    else:
        meaningful = []
        for line in content.splitlines():
            cleaned = re.sub(r"^[#>*\-\s]+", "", line).strip()
            cleaned = re.sub(r"^【[^】]+】\s*", "", cleaned).strip()
            if cleaned:
                meaningful.append(cleaned)
        concept = meaningful[0][:140] if meaningful else "未命名TK"
    return {
        "id": hashlib.md5(document["path"].encode()).hexdigest()[:12],
        "concept": concept,
        "preview": content[:360],
        "date": date,
        "team": fields["team"],
        "player": fields["player"],
        "tags": fields["tags"],
        "type": record_type,
        "source": fields["source"],
        "filename": document["filename"],
        "content_length": len(content),
        "mtime": document["mtime"],
    }


def _period_matches(date: str, period: str, month: str) -> bool:
    if period == "all":
        return True
    if period == "month":
        return bool(month and date.startswith(month))
    try:
        item_date = datetime.strptime(date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    today = datetime.now().date()
    if period == "today":
        return item_date == today
    days = 7 if period == "7d" else 30
    return today.fromordinal(today.toordinal() - days + 1) <= item_date <= today


def _document_game(content: str) -> str:
    """读取文档 frontmatter 的「游戏:」标记；无标记或标记为 LOL 时返回 'LOL'。

    tk 默认 LOL：瓦/CS 等条目通过 tags 里的「游戏:」标记区分，LOL 语境聚合（队伍列表、
    统计、单场相关 TK）只匹配 LOL 条目；显式搜索（/api/tk/search）保持全量。
    """
    if not (content or "").startswith("---"):
        return "LOL"
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "LOL"
    tags_line = ""
    for line in parts[1].splitlines():
        if line.strip().lower().startswith("tags:"):
            tags_line = line
            break
    match = re.search(r"游戏\s*[:：]\s*([^,\[\]，\n]+)", tags_line)
    if not match:
        return "LOL"
    value = match.group(1).strip()
    return "LOL" if not value or value.casefold() in ("lol", "英雄联盟") else value


def _strict_team_marker(filename: str, content: str, team: str, game: str = "LOL") -> bool:
    if _document_game(content).casefold() != game.casefold():
        return False
    code = (team or "").strip().upper()
    if not code:
        return False
    if re.search(rf"(^|[_\-\W]){re.escape(code)}([_\-\W]|$)", filename.upper()):
        return True
    head = content[:1600].upper()
    if f"队伍:{code}".upper() in head or f"队伍：{code}".upper() in head:
        return True
    return bool(re.search(rf"(队伍|战队|简称|TEAM)\s*[:：/]\s*[^\n#|]*\b{re.escape(code)}\b", head))


def _file_search(query: str, team: str, limit: int, *, strict_team: bool = False, game: str | None = None) -> list[dict]:
    keywords = query.lower().split()
    team_code = (team or "").strip().upper()
    results = []
    for document in repository.list_documents():
        raw = document["content"]
        if game and _document_game(raw).casefold() != game.casefold():
            continue
        if team_code:
            if strict_team and not _strict_team_marker(document["filename"], raw, team_code, game or "LOL"):
                continue
            if not strict_team and team_code not in document["filename"].upper() and team_code not in raw[:500].upper():
                continue
        clean = _clean_content(raw)
        score = sum(1 for keyword in keywords if keyword in clean.casefold())
        if score == 0 and query.strip():
            continue
        if len(clean) < MIN_CONTENT_LEN:
            continue
        fields = _frontmatter(raw)
        date = ""
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            for line in parts[1].splitlines() if len(parts) >= 3 else []:
                if line.strip().lower().startswith("created:"):
                    date = _extract_date(line)
                    break
        if not date:
            date = datetime.fromtimestamp(document["mtime"]).strftime("%Y-%m-%d")
        results.append({
            "id": hashlib.md5(document["path"].encode()).hexdigest()[:12],
            "concept": _concept(document["filename"], raw).replace(".md", ""),
            "content": clean[:800],
            "date": date,
            "source": fields["source"],
            "source_type": "file",
            "strength": score * 20,
            "tags": fields["tags"][:5],
            "filename": document["filename"],
        })
    results.sort(key=lambda item: item.get("date") or "0000-00-00", reverse=True)
    return results[:limit]


def search(query: str, team: str | None = None, limit: int = 20, game: str | None = None) -> dict:
    rag_query = f"{team} {query}" if team else query
    raws = repository.search_rag(rag_query, limit * 2)
    seen, merged = set(), []
    for raw in raws:
        key = raw.get("title", "")
        filename = os.path.basename(key) if key else ""
        raw_text = raw.get("text", "") or ""
        text = _clean_content(raw_text)
        if game and _document_game(raw_text).casefold() != game.casefold():
            continue
        if team and not _strict_team_marker(filename, raw_text, team, game or "LOL"):
            continue
        if key in seen or filename in seen or len(text.strip()) < MIN_CONTENT_LEN:
            continue
        seen.add(key)
        if filename:
            seen.add(filename)
        merged.append({
            "id": key,
            "concept": key[:80],
            "content": text[:800],
            "date": _extract_date(str(raw.get("date", "")) + " " + raw_text),
            "source": raw.get("author", ""),
            "source_type": raw.get("source_type", "rag"),
            "strength": 0,
            "tags": [],
            "filename": filename if filename.endswith(".md") else "",
        })
    for item in _file_search(query, team or "", limit, strict_team=bool(team), game=game):
        if item["id"] in seen or item.get("filename") in seen:
            continue
        seen.add(item["id"])
        if item.get("filename"):
            seen.add(item["filename"])
        merged.append(item)
    merged.sort(key=lambda item: item.get("date") or "0000-00-00", reverse=True)
    return {"results": merged[:limit]}


def browse(period: str = "all", month: str = "", query: str = "", team: str = "", offset: int = 0, limit: int = 30) -> dict:
    if period not in {"today", "7d", "30d", "month", "all"}:
        raise InvalidInput("不支持的时间范围")
    if period == "month" and not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise InvalidInput("月份格式应为 YYYY-MM")
    records = [record for document in repository.list_documents() if (record := _library_record(document))]
    months = sorted({item["date"][:7] for item in records if item.get("date")}, reverse=True)
    words = [word.casefold() for word in query.split() if word.strip()]
    code = team.strip().upper()
    filtered = []
    documents = {item["filename"]: item for item in repository.list_documents()}
    for item in records:
        if not _period_matches(item["date"], period, month):
            continue
        raw = documents[item["filename"]]["content"]
        folded = _clean_content(raw).casefold()
        if words and not all(word in folded for word in words):
            continue
        if code and (item.get("team") or "").upper() != code and not _strict_team_marker(item["filename"], raw, code):
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: (item.get("date") or "", item.get("mtime") or 0, item["filename"]), reverse=True)
    total = len(filtered)
    page = filtered[offset:offset + limit]
    for item in page:
        item.pop("mtime", None)
        item.pop("source", None)
    return {
        "results": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < total,
        "available_months": months,
        "latest_date": max((item["date"] for item in records if item.get("date")), default=""),
    }


def _safe_filename(filename: str) -> str:
    safe = os.path.basename(filename or "")
    if not safe or safe != filename or not safe.endswith(".md"):
        raise InvalidInput("非法 TK 文件名")
    return safe


def get_entry(filename: str) -> dict:
    safe = _safe_filename(filename)
    document = repository.read_document(safe)
    record = _library_record(document) if document else None
    if not record:
        raise EntryNotFound("TK 不存在或没有可读正文")
    content = _clean_content(document["content"])
    return {
        "concept": record["concept"], "content": content, "date": record["date"],
        "team": record["team"], "player": record["player"], "tags": record["tags"],
        "content_length": len(content),
    }


def _clean_tags(values: list[str]) -> list[str]:
    """Keep only directional/source labels; never persist lifecycle metadata."""
    result = []
    for raw in values:
        tag = str(raw or "").strip()
        if tag in {"交易", "钧钧口述", "B站", "公众号"} or tag.startswith(_TAG_PREFIXES):
            if tag not in result:
                result.append(tag)
    return result


def _markdown(data: dict, *, source: str = "手动录入", created: str | None = None) -> str:
    content = data.get("content", "")
    tags, team, player = data.get("tags", ""), data.get("team", ""), data.get("player", "")
    tag_list = []
    if team:
        tag_list.append(f"队伍:{team}")
    if player:
        tag_list.append(f"选手:{player}")
    if isinstance(tags, str) and tags:
        tag_list.extend(_clean_tags(tags.split(",")))
    if not tag_list:
        tag_list.append("通用")
    extra_lines = []
    extra = "\n" + "\n".join(extra_lines) if extra_lines else ""
    date_str = created or datetime.now().strftime("%Y-%m-%d")
    return f"---\nsource: {source}\nsource_type: manual\ntags: [{', '.join(tag_list)}]\ncreated: {date_str}{extra}\n---\n\n{content}\n"


def create(data: dict) -> dict:
    content = _clean_content(str(data.get("content", "")))
    if not content or len(content.strip()) < 10:
        raise InvalidInput("内容太短")
    title = content.strip().split("\n")[0][:60]
    stem = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", title)[:50].strip("_") or "untitled"
    filename = f"manual_{hash(content) % 10000}_{stem}.md"
    clean_data = {**data, "content": content}
    path = repository.write_document(filename, _markdown(clean_data, source=data.get("source", "手动录入")))
    repository.request_reindex()
    _invalidate_teams_cache()
    return {"ok": True, "filename": filename, "path": path}


def remember_personal_note(text: str, explicit_tags: list[str] | None = None) -> dict:
    """Write Junjun's words as an ordinary manual TK without inferring fields."""
    content = _clean_content(str(text or ""))
    if len(content) < 2:
        raise InvalidInput("记录内容太短")
    tag_seed = ",".join(_clean_tags(explicit_tags or []))
    digest = hashlib.sha256(f"{content}\n{tag_seed}".encode("utf-8")).hexdigest()[:16]
    filename = f"manual_{digest}.md"
    teams = _explicit_teams_in_text(content)
    explicit = [str(tag).strip() for tag in (explicit_tags or []) if str(tag).strip() == "交易" or re.fullmatch(r"(?:队伍|选手|赛区|版本|比赛|游戏):[^:]{1,80}", str(tag).strip())]
    tags = ["钧钧口述", *explicit, *(f"队伍:{team}" for team in teams)]
    path = repository.write_document(filename, _markdown(
        {"content": content, "tags": ",".join(tags)}, source="钧钧口述",
    ))
    indexed = repository.request_reindex()
    _invalidate_teams_cache()
    return {
        "ok": True, "filename": filename, "path": path, "content": content,
        "source": "钧钧口述", "teams": teams, "indexed": indexed,
    }


def update(filename: str, data: dict) -> dict:
    safe = _safe_filename(filename)
    old = repository.read_document(safe)
    if not old:
        raise EntryNotFound("TK 未找到")
    content = _clean_content(str(data.get("content", "")))
    if not content or len(content.strip()) < 10:
        raise InvalidInput("内容太短")
    created = None
    for line in old["content"][:1000].split("\n"):
        if line.strip().startswith("created:"):
            created = _extract_date(line.replace("created:", "").strip()) or None
            break
    clean_data = {**data, "content": content}
    path = repository.write_document(safe, _markdown(clean_data, source=data.get("source", "手动录入"), created=created))
    repository.request_reindex()
    _invalidate_teams_cache()
    return {"ok": True, "filename": safe, "path": path}


def delete(filename: str) -> dict:
    safe = _safe_filename(filename)
    if not repository.delete_document(safe):
        raise EntryNotFound("TK 未找到")
    repository.request_reindex()
    _invalidate_teams_cache()
    return {"ok": True}


def _invalidate_teams_cache() -> None:
    """TK 写入/删除后失效 fundamentals 列表缓存（延迟 import 防循环）。"""
    try:
        from xiaoxue_api.modules.team.public import invalidate_teams_cache
    except ImportError:
        return
    invalidate_teams_cache()


def _normalize_market(value: str) -> str:
    raw = (value or "").strip()
    return (_market_config().get("aliases") or {}).get(raw, raw) if raw else ""


def _infer(value: str, key: str) -> str:
    for hint, normalized in (_market_config().get(key) or {}).items():
        if hint and hint in value:
            return normalized
    return ""


def parse_trading_note_text(text: str) -> TradingNoteIn:
    raw = (text or "").strip()
    if len(raw) < 4:
        raise InvalidInput("交易 TK 内容太短")
    clean = re.sub(r"^\s*小雪\s*记到\s*", "", raw).strip()
    clean = re.sub(r"^\s*记到\s*", "", clean).strip()
    match = re.match(r"^([A-Za-z0-9\.\-_\u4e00-\u9fff]+)\s*[:：]\s*(.+)$", clean)
    if not match:
        match = re.match(r"^([A-Za-z0-9\.\-_\u4e00-\u9fff]+)\s+(.+)$", clean)
    if not match:
        raise TeamUnconfirmed("队伍不明确，未写入正式 TK；请写成“小雪记到 HLE：虐菜大人头”")
    team_hint, note = match.group(1).strip(), match.group(2).strip()
    if len(note) < 4:
        raise InvalidInput("交易 TK 内容太短")
    try:
        team = normalize_team(team_hint)
    except (InvalidInput, EntryNotFound):
        raise TeamUnconfirmed(f"队伍未确认，未写入正式 TK：{team_hint}")
    return TradingNoteIn(
        team=team, note=note, market=_infer(note, "aliases"),
        scenario=_infer(note, "scenario_aliases"), status="active",
    )


def _strip_team_prefix(text: str, team: str) -> str:
    clean, code = (text or "").strip(), (team or "").strip()
    if not clean or not code:
        return clean
    changed = True
    while changed:
        changed = False
        for pattern in (rf"^{re.escape(code)}\s*[:：]\s*", rf"^{re.escape(code)}\s+"):
            new = re.sub(pattern, "", clean, count=1, flags=re.I).strip()
            if new != clean:
                clean, changed = new, True
    return clean


def _render_trading_note(data: TradingNoteIn, team: str) -> dict:
    note = (data.note or "").strip()
    if len(note) < 4:
        raise InvalidInput("交易 TK 内容太短")
    status = (data.status or "active").strip().lower()
    if status not in ("active", "inactive"):
        status = "active"
    market = _normalize_market(data.market) or _infer(note, "aliases")
    scenario = (data.scenario or "").strip()
    scenario = (_market_config().get("scenario_aliases") or {}).get(scenario, scenario) or _infer(note, "scenario_aliases")
    clean_title = (data.title or note.splitlines()[0][:40]).strip() or f"{team} 交易 TK"
    title = clean_title if clean_title.upper().startswith(team.upper()) else f"{team} {clean_title}"
    label = (_market_config().get("labels") or {}).get(market, market or "待判断")
    content = f"""## 交易 TK

### {title}

原话：{note}

日报提示：{note}

用途：归入 {team} 队伍 TK；日报命中该队比赛时优先展示。
"""
    return {"content": content, "title": title, "market": market, "market_label": label, "scenario": scenario or "待判断", "status": status}


def create_team_trading_note(data: TradingNoteIn) -> dict:
    team = normalize_team(data.team)
    rendered = _render_trading_note(data, team)
    created = create({
        "content": rendered["content"], "team": team,
        "tags": f"交易 TK,{TRADING_NOTE_TYPE},{rendered['market']},{rendered['scenario']}",
        "source": "钧钧手动交易 TK", "type": TRADING_NOTE_TYPE,
        "market": rendered["market"], "scenario": rendered["scenario"], "status": rendered["status"],
    })
    return {
        "ok": True, "team": team,
        "note": {key: rendered[key] for key in ("title", "market", "market_label", "scenario", "status")},
        "tk": created,
        "boundary": "写入现有队伍 TK/Wiki 正源，不新增交易 TK 实体",
    }


def _single_line(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _normalize_trading_scope(value: str) -> str:
    scope = _single_line(value or "global", 20).lower()
    if scope == "general":
        return "global"
    if scope not in TRADING_TK_SCOPES:
        raise InvalidInput("交易 TK 范围不支持")
    return scope


def _normalize_trading_region(value: str) -> str:
    return _single_line(value, 40).upper()


def _normalize_trading_subject(value: str) -> str:
    return _single_line(value, 80)


def _general_trading_tk_filename(statement: str, scope: str, region: str = "", subject: str = "", version_context: str = "") -> str:
    key = "|".join((scope, region.casefold(), subject.casefold(), version_context.casefold(), statement.casefold()))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"{TRADING_TK_PREFIX}{scope}_{digest}.md"


def _legacy_general_trading_tk_filename(statement: str) -> str:
    digest = hashlib.sha256(statement.casefold().encode("utf-8")).hexdigest()[:16]
    return f"{GENERAL_TRADING_TK_PREFIX}{digest}.md"


def _general_trading_tk_meta(content: str) -> dict:
    if not (content or "").startswith("---"):
        return {}
    parts = content.split("---", 2)
    return _parse_simple_yaml(parts[1]) if len(parts) >= 3 else {}


def _line_value(content: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", content or "", re.M)
    return match.group(1).strip() if match else ""


def _general_trading_tk_payload(document: dict) -> dict | None:
    content = document.get("content") or ""
    meta = _general_trading_tk_meta(content)
    filename = document.get("filename") or ""
    if meta.get("type") != TRADING_NOTE_TYPE or not filename.startswith(TRADING_TK_PREFIX):
        return None
    statement = _line_value(content, "规律")
    if not statement:
        return None
    raw_scope = (meta.get("scope") or "global").lower()
    scope = "global" if raw_scope == "general" else raw_scope
    if scope not in TRADING_TK_SCOPES:
        return None
    category = meta.get("category") or "general"
    status = (meta.get("status") or "candidate").lower()
    status_label = {"candidate": "待验证", "confirmed": "已确认", "invalid": "已失效"}.get(status, status)
    tags = ["交易", "交易 TK", status_label, category]
    if meta.get("region"):
        tags.append(str(meta.get("region")))
    if meta.get("subject"):
        tags.append(str(meta.get("subject")))
    return {
        "id": document["filename"], "filename": document["filename"],
        "scope": scope, "scope_label": TRADING_TK_SCOPE_LABELS[scope],
        "region": meta.get("region") or "", "subject": meta.get("subject") or "",
        "version_context": meta.get("version_context") or "",
        "category": category, "category_label": TRADING_TK_CATEGORY_LABELS.get(category, category), "statement": statement,
        "context": _line_value(content, "适用范围"),
        "review_note": _line_value(content, "复查记录"),
        "type": "trading_tk",
        "status": status,
        "tags": tags,
        "created_at": meta.get("created") or "", "updated_at": datetime.fromtimestamp(document["mtime"]).strftime("%Y-%m-%d %H:%M:%S"),
        "source_type": "scoped_trading_tk", "editable": True,
    }


def _tagged_trading_tk_payload(document: dict) -> dict | None:
    """Read legacy trade-labeled ordinary TKs without upgrading them to trading TKs."""
    content = document.get("content") or ""
    meta = _general_trading_tk_meta(content)
    labels = [item.strip() for item in (meta.get("tags") or "").strip("[]").split(",") if item.strip()]
    if "交易" not in labels:
        return None
    def label(prefix: str) -> str:
        return next((item.split(":", 1)[1].strip() for item in labels if item.startswith(prefix)), "")
    team, player, region, version = label("队伍:"), label("选手:"), label("赛区:"), label("版本:")
    game = label("游戏:") or "LOL"
    scope, subject = ("team", team) if team else (("player", player) if player else (("region", "") if region else ("global", "")))
    return {
        "id": document["filename"], "filename": document["filename"], "scope": scope,
        "scope_label": TRADING_TK_SCOPE_LABELS[scope], "region": region, "subject": subject,
        "version_context": version, "statement": _clean_content(content), "context": "", "tags": labels,
        "game": game,
        "created_at": meta.get("created") or "", "updated_at": datetime.fromtimestamp(document["mtime"]).strftime("%Y-%m-%d %H:%M:%S"),
        "type": "legacy_trade_label",
        "source_type": "tagged_trading_tk", "editable": True,
    }


def _render_general_trading_tk(values: dict) -> str:
    status_labels = {"candidate": "待验证", "confirmed": "已确认", "invalid": "已失效"}
    status = values["status"]
    scope = values["scope"]
    scope_label = TRADING_TK_SCOPE_LABELS[scope]
    category = values["category"]
    category_label = TRADING_TK_CATEGORY_LABELS.get(category, category)
    context = values.get("context") or "未限定，按具体比赛验证"
    review_note = values.get("review_note") or "尚未复查"
    tags = ["交易 TK", f"{scope_label}交易 TK", status_labels[status], category]
    if scope == "global":
        tags.insert(2, "通用交易 TK")
    if values.get("region"):
        tags.append(values["region"])
    if values.get("subject"):
        tags.append(values["subject"])
    return f"""---
source: 钧钧手动交易 TK
source_type: manual
tags: [{', '.join(tags)}]
created: {values['created_at']}
type: {TRADING_NOTE_TYPE}
scope: {scope}
region: {values.get('region') or ''}
subject: {values.get('subject') or ''}
version_context: {values.get('version_context') or ''}
category: {category}
status: {status}
---

## 交易 TK

【结论】{values['statement']}

层级：{scope_label}

主题：{category_label}

适用赛区：{values.get('region') or '全部'}

对象：{values.get('subject') or '未限定'}

适用版本：{values.get('version_context') or '未限定'}

规律：{values['statement']}

适用范围：{context}

状态：{status_labels[status]}

复查记录：{review_note}

原话：{values['source_command']}

用途：统一保存在 TK 资料库；单场按“全局 → 赛区 → 队伍/选手”调用，是否采用由钧钧确认。
"""


def create_general_trading_tk(values: dict) -> dict:
    """Write a distinct, reviewable trading TK in the shared TK library."""
    statement = _single_line(values.get("statement"), 500)
    context = _single_line(values.get("context"), 500)
    if len(statement) < 2:
        raise InvalidInput("记录内容太短")
    scope = _normalize_trading_scope(values.get("scope") or "global")
    region = _normalize_trading_region(values.get("region") or "")
    subject = _normalize_trading_subject(values.get("subject") or "")
    version_context = _single_line(values.get("version_context") or "", 80)
    category = _single_line(values.get("category") or "general", 40).lower()
    filename = _general_trading_tk_filename(statement, scope, region, subject, version_context)
    existing = repository.read_document(filename)
    if existing:
        return {"ok": True, "filename": filename, "item": _general_trading_tk_payload(existing), "indexed": False, "idempotent": True}
    created_at = datetime.now().strftime("%Y-%m-%d")
    rendered = _render_general_trading_tk({
        "statement": statement, "context": context, "scope": scope, "region": region,
        "subject": subject, "version_context": version_context, "category": category,
        "status": "candidate", "review_note": "尚未复查", "created_at": created_at,
        "source_command": _single_line(values.get("source_command") or "", 500),
    })
    path = repository.write_document(filename, rendered)
    indexed = repository.request_reindex()
    return {"ok": True, "filename": filename, "path": path, "item": _general_trading_tk_payload(repository.read_document(filename)), "indexed": indexed}


def list_general_trading_tk(
    query: str = "", status: str = "all", limit: int = 100, *, scope: str = "all",
    region: str = "", subject: str = "", version_context: str = "", game: str = "",
) -> dict:
    clean_query = _single_line(query, 100).casefold()
    clean_status = _single_line(status or "all", 20).lower()
    if clean_status not in GENERAL_TRADING_TK_STATUSES | {"all"}:
        raise InvalidInput("交易 TK 状态不支持")
    clean_scope = _single_line(scope or "all", 20).lower()
    if clean_scope == "general":
        clean_scope = "global"
    if clean_scope not in TRADING_TK_SCOPES | {"all"}:
        raise InvalidInput("交易 TK 范围不支持")
    clean_region = _normalize_trading_region(region)
    clean_subject = _normalize_trading_subject(subject)
    clean_version = _single_line(version_context, 80)
    clean_game = _single_line(game or "", 30)
    bounded = max(1, min(int(limit or 100), 200))
    items = []
    for document in sorted(repository.list_documents(), key=lambda item: item["mtime"], reverse=True):
        for item in _unified_trading_tk_payloads(document):
            if clean_game and str(item.get("game") or "LOL").casefold() != clean_game.casefold():
                continue
            if clean_status != "all" and item.get("status") != clean_status:
                continue
            if clean_scope != "all" and item["scope"] != clean_scope:
                continue
            if clean_region and item["region"].casefold() != clean_region.casefold():
                continue
            if clean_subject and item["subject"].casefold() != clean_subject.casefold():
                continue
            if clean_version and item["version_context"].casefold() != clean_version.casefold():
                continue
            haystack = " ".join((item["statement"], item["context"], item.get("category", ""), item["scope"], item["region"], item["subject"], item["version_context"], " ".join(item.get("tags") or []))).casefold()
            if clean_query and clean_query not in haystack:
                continue
            items.append(item)
            if len(items) >= bounded:
                break
        if len(items) >= bounded:
            break
    return {
        "query": query, "status": clean_status, "scope": clean_scope, "region": clean_region,
        "subject": clean_subject, "version_context": clean_version, "items": items, "source": "existing_tk_library",
    }


def list_match_trading_tk(region: str, teams: list[str], players: list[str], limit: int = 12, *, version_context: str = "") -> dict:
    clean_region = _normalize_trading_region(region)
    clean_version = _single_line(version_context, 80)
    team_set = {str(item or "").strip().casefold() for item in teams if str(item or "").strip()}
    player_set = {str(item or "").strip().casefold() for item in players if str(item or "").strip()}
    rank = {"global": 0, "region": 1, "team": 2, "player": 3}
    items = []
    for document in repository.list_documents():
        for item in _unified_trading_tk_payloads(document):
            if str(item.get("game") or "LOL") != "LOL":
                continue
            if clean_version and item["version_context"] and item["version_context"].casefold() != clean_version.casefold():
                continue
            if item["scope"] == "region" and item["region"].casefold() != clean_region.casefold():
                continue
            if item["scope"] == "team" and item["subject"].casefold() not in team_set:
                continue
            if item["scope"] == "player" and item["subject"].casefold() not in player_set:
                continue
            items.append(item)
    items.sort(key=lambda item: (rank[item["scope"]], item.get("updated_at") or "", item["filename"]), reverse=False)
    return {
        "region": clean_region, "teams": sorted(team_set), "players": sorted(player_set), "version_context": clean_version,
        "call_order": ["全局", "赛区", "队伍/选手"], "items": items[:max(1, min(int(limit or 12), 30))],
        "boundary": "只找与本场有关的交易 TK；待验证只作提醒，是否采用由钧钧确认。",
    }


def update_general_trading_tk_status(filename: str, status: str, review_note: str = "") -> dict:
    safe = _safe_filename(filename)
    if not safe.startswith(TRADING_TK_PREFIX):
        raise InvalidInput("不是交易 TK 词条")
    clean_status = _single_line(status, 20).lower()
    if clean_status not in GENERAL_TRADING_TK_STATUSES:
        raise InvalidInput("交易 TK 状态不支持")
    document = repository.read_document(safe)
    item = _general_trading_tk_payload(document) if document else None
    if not item:
        raise EntryNotFound("交易 TK 不存在")
    source_command = _line_value(document["content"], "原话") or item["statement"]
    rendered = _render_general_trading_tk({
        **item, "status": clean_status, "review_note": _single_line(review_note, 500),
        "source_command": source_command,
    })
    repository.write_document(safe, rendered)
    indexed = repository.request_reindex()
    return {
        "ok": True, "item": _general_trading_tk_payload(repository.read_document(safe)), "indexed": indexed,
        "boundary": "只更新原交易 TK 词条，不复制新记录",
    }


def _parse_simple_yaml(block: str) -> dict:
    data = {}
    for raw in (block or "").splitlines():
        if ":" in raw:
            key, value = raw.split(":", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _trading_notes_from_content(content: str, team: str = "") -> list[dict]:
    notes = []
    labels = _market_config().get("labels") or {}
    for match in re.finditer(r"```yaml\s*(.*?)```", content or "", re.S):
        meta = _parse_simple_yaml(match.group(1))
        if meta.get("type") != TRADING_NOTE_TYPE:
            continue
        code = (meta.get("team") or team or "").strip().upper()
        if team and code and code != team.upper():
            continue
        prefix = content[:match.start()]
        titles = re.findall(r"^#{2,4}\s+(.+)$", prefix, re.M)
        tail = content[match.end():match.end() + 1200]
        original = daily_hint = ""
        for line in tail.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            if stripped.startswith(("原话：", "原话:")):
                original = stripped.split("：", 1)[-1] if "：" in stripped else stripped.split(":", 1)[-1]
            if stripped.startswith(("日报提示：", "日报提示:")):
                daily_hint = stripped.split("：", 1)[-1] if "：" in stripped else stripped.split(":", 1)[-1]
        market = meta.get("market", "")
        status = (meta.get("status") or "active").strip().lower()
        if "已过期作废" in f"{titles[-1] if titles else ''}\n{original}\n{daily_hint}":
            status = "inactive"
        notes.append({
            "team": code, "title": titles[-1].strip() if titles else f"{code} 交易 TK",
            "market": market, "market_label": labels.get(market, market),
            "scenario": meta.get("scenario", ""), "status": status,
            "source": meta.get("source", ""), "original": _strip_team_prefix(original, code),
            "daily_hint": _strip_team_prefix(daily_hint, code),
        })
    return notes


def _legacy_team_trading_tk_payloads(document: dict) -> list[dict]:
    """Expose old team trading notes in the unified view without rewriting them."""
    content = document.get("content") or ""
    meta = _general_trading_tk_meta(content)
    updated_at = datetime.fromtimestamp(document["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
    items = []
    for note in _trading_notes_from_content(content):
        team = note.get("team") or ""
        original = note.get("original") or note.get("title") or ""
        if not team or not original:
            continue
        items.append({
            "id": document["filename"], "filename": document["filename"],
            "scope": "team", "scope_label": TRADING_TK_SCOPE_LABELS["team"],
            "region": "", "subject": team, "version_context": "",
            "category": "market", "category_label": TRADING_TK_CATEGORY_LABELS["market"],
            "statement": f"{team}：{original}", "context": note.get("daily_hint") or "原有队伍交易备注",
            "tags": ["交易", f"队伍:{team}"],
            "created_at": meta.get("created") or "", "updated_at": updated_at,
            "source_type": "legacy_team_trading_note", "editable": False,
        })
    return items


def _unified_trading_tk_payloads(document: dict) -> list[dict]:
    tagged = _tagged_trading_tk_payload(document)
    if tagged:
        return [tagged]
    scoped = _general_trading_tk_payload(document)
    return [scoped] if scoped else _legacy_team_trading_tk_payloads(document)


def _scoped_team_trading_note(item: dict, team: str) -> dict | None:
    if str(item.get("game") or "LOL") != "LOL":
        return None
    if item.get("scope") != "team" or item.get("subject", "").casefold() != team.casefold():
        return None
    status = item.get("status") or "active"
    return {
        "team": team, "title": f"{team} 交易 TK · {item.get('statement', '')}",
        "market": "", "market_label": "", "scenario": item.get("category_label") or item.get("category") or "",
        "source": "junjun_manual", "original": item.get("statement") or "",
        "daily_hint": item.get("context") or "", "filename": item.get("filename") or "",
        "source_type": "scoped_trading_tk",
    }


def list_team_trading_notes(team: str, status: str = "active", limit: int = 20) -> dict:
    code = normalize_team(team)
    wanted = (status or "").strip().lower()
    notes = []
    for document in sorted(repository.list_documents(), key=lambda item: item["mtime"], reverse=True):
        scoped = _scoped_team_trading_note(
            _general_trading_tk_payload(document) or _tagged_trading_tk_payload(document) or {}, code,
        )
        if scoped:
            if not wanted or wanted in {"all", "active"}:
                notes.append(scoped)
            if len(notes) >= limit:
                break
            continue
        if not _strict_team_marker(document["filename"], document["content"], code):
            continue
        for note in _trading_notes_from_content(document["content"], code):
            # Legacy status values are intentionally not exposed or filtered.
            note.pop("status", None)
            note["filename"] = document["filename"]
            note["source_type"] = "tk_file"
            notes.append(note)
            if len(notes) >= limit:
                break
        if len(notes) >= limit:
            break
    return {"ok": True, "team": code, "status": status, "notes": notes, "source": "tk_files_structured_blocks", "boundary": "结构化读取 type=trading_note；RAG/搜索不作为主链路"}


def _summary(text: str, limit: int) -> str:
    cleaned = re.sub(r"[#>*`\[\]_|-]+", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def get_version_understanding(team: str, limit: int = 8) -> dict:
    code = (team or "").strip().upper()
    if not code:
        raise InvalidInput("队伍不能为空")
    try:
        team_3d = get_team_3d(code)
    except LookupError:
        team_3d = {}
    results = search_team_entries("版本 理解", code, limit)
    if not results:
        results = search_team_entries("版本", code, limit)
    items = [{
        "id": item.get("id"), "title": item.get("concept") or item.get("filename") or "TK",
        "date": item.get("date") or "", "source": item.get("source") or item.get("source_type") or "",
        "summary": _summary(item.get("content") or "", 180), "filename": item.get("filename") or "",
    } for item in results[:limit]]
    return {
        "ok": True, "team": code, "source": "team_3d_data + tk_files",
        "version_understanding": team_3d.get("version_understanding", ""),
        "notes_summary": _summary(team_3d.get("notes", ""), 160),
        "updated_at": team_3d.get("updated_at", ""), "tk_items": items,
        "boundary": "只读聚合现有资料，不自动生成版本判断",
    }


def count_team_entries(team: str) -> int:
    code = (team or "").strip().upper()
    if not code:
        return 0
    count = 0
    for document in repository.list_documents():
        if _document_game(document["content"]) != "LOL":
            continue
        if code in document["filename"].upper() or code in document["content"][:800].upper():
            count += 1
    return count


def search_team_entries(query: str, team: str, limit: int = 20) -> list[dict]:
    return _file_search(query, team, limit, strict_team=True)
