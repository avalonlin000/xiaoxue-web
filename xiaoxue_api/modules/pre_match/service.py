from __future__ import annotations

from datetime import datetime
import re

from xiaoxue_api.modules.fundamentals.public import get_match_context
from xiaoxue_api.modules.team_data.public import list_schedules, list_teams
from xiaoxue_api.modules.tk_knowledge.public import list_team_trading_notes

from . import repository


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InvalidDate(ValueError):
    pass


def get_report(date: str = "today", limit: int = 12) -> dict:
    date_str = resolve_date(date)
    matches = list_schedules({"date_from": date_str, "date_to": date_str}, limit)
    return {
        "ok": True,
        "date": date_str,
        "matches": len(matches),
        "markdown": render_report(date_str, matches),
        "boundary": "只读预览；写文件由脚本负责；不恢复 tk_library，不接旧 /api/trades",
    }


def resolve_date(value: str | None) -> str:
    raw = (value or "today").strip().lower()
    if raw == "today":
        return datetime.now().strftime("%Y-%m-%d")
    if not DATE_PATTERN.fullmatch(raw):
        raise InvalidDate("非法 date 参数；只支持 today 或 YYYY-MM-DD")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise InvalidDate("非法 date 参数；只支持 today 或 YYYY-MM-DD") from exc
    return raw


def build_view(match: dict) -> dict:
    team_a = _normalize_team(match.get("team_a") or "")
    team_b = _normalize_team(match.get("team_b") or "")
    try:
        fundamentals = get_match_context(team_a, team_b)
    except LookupError:
        fundamentals = {}
    context_a = fundamentals.get("team_a")
    context_b = fundamentals.get("team_b")
    comparison = fundamentals.get("compare")
    notes_a = list_team_trading_notes(team_a, status="active", limit=8)["notes"] if team_a else []
    notes_b = list_team_trading_notes(team_b, status="active", limit=8)["notes"] if team_b else []
    notes = (notes_a + notes_b)[:3]
    primary = _primary_note(notes)
    if primary and comparison:
        market = primary.get("market") or ""
        direction = primary.get("market_label") or repository.market_labels().get(market, market) or "待判断"
        entry_point = _entry_point(market, primary.get("scenario") or "", primary.get("team") or "")
        divergence = primary.get("daily_hint") or primary.get("original") or comparison["market_note"]
        backup = "无；先围绕主方向观察。"
        avoid = "低赔独赢 / 过深让分 / 没有 BP 支持的人头大小"
    elif primary:
        direction = "暂不推荐"
        entry_point = "只有历史交易 TK，当前基础面/TS/盘口信息不足，先提示不下方向。"
        divergence = primary.get("daily_hint") or primary.get("original") or "命中历史交易 TK，但缺当前比赛支撑。"
        backup = "无"
        avoid = "数据不足时不硬推"
    else:
        direction = "暂不推荐"
        entry_point = "没有命中有效交易 TK，等待 BP/盘口/赛中信息。"
        divergence = comparison["market_note"] if comparison else "基础数据不足，市场分歧不编。"
        backup = "无"
        avoid = "无备注、无数据时不硬推"
    return {
        "match": match,
        "team_a": team_a,
        "team_b": team_b,
        "ts": {"team_a": context_a, "team_b": context_b, "compare": comparison},
        "trading_notes": notes,
        "trading_summary": {
            "primary_direction": direction,
            "entry_point": entry_point,
            "market_divergence": divergence,
            "backup": backup,
            "avoid": avoid,
            "bp_pending": "BP 出来后只确认是否支持原方向，不重写整场。",
        },
    }


def render_report(date_str: str, matches: list[dict]) -> str:
    views = [build_view(match) for match in matches]
    lines = [
        f"# 赛前交易判断日报 {date_str}",
        "",
        "> 保留原日报基础面；本文件只增加赛前交易判断层。交易 TK 跟随队伍 TK，按比赛优先展示；RAG/搜索只作补充。",
        "",
        "## 今日优先交易方向",
    ]
    priorities = []
    for view in views:
        summary = view["trading_summary"]
        if summary["primary_direction"] != "暂不推荐":
            priorities.append(
                f"- {view['team_a']} vs {view['team_b']}：{summary['primary_direction']}；入场点：{summary['entry_point']}"
            )
    if priorities:
        lines.extend(priorities[:3])
    else:
        lines.append("- 暂无强方向；没有有效交易 TK 或当前基础面不足时不硬编。")
    lines.extend([
        "", "## 今日不碰", "- 过深让分", "- 没有 BP 支持的人头大小",
        "- 队伍不明确或数据不足的场次", "",
    ])
    for view in views:
        match = view["match"]
        summary = view["trading_summary"]
        comparison = view["ts"]["compare"]
        notes = view["trading_notes"]
        lines.extend([f"## {view['team_a']} vs {view['team_b']}", "", "### 1. 基础面"])
        if comparison:
            lines.extend([f"- {comparison['daily_summary']}", f"- {comparison['risk_note']}"])
        else:
            lines.append("- 基础面/TS 数据不足；保留赛程信息，不补编强弱判断。")
        metadata = " / ".join(
            value
            for value in (match.get("time"), match.get("region"), match.get("format"), match.get("stage"))
            if value
        )
        if metadata:
            lines.append(f"- 赛程：{metadata}")
        lines.extend(["", "### 2. 交易 TK"])
        if notes:
            for note in notes[:3]:
                hint = note.get("daily_hint") or note.get("original") or note.get("title")
                lines.append(f"- {note.get('team') or ''}：{hint}")
        else:
            lines.append("- 无有效交易 TK 命中。")
        lines.extend([
            "", "### 3. 市场分歧", f"- {summary['market_divergence']}", "",
            "### 4. 交易小结", f"- 主方向：{summary['primary_direction']}",
            f"- 入场点：{summary['entry_point']}", f"- 备选方向：{summary['backup']}",
            f"- 不碰项：{summary['avoid']}", "", "### 5. BP 待确认",
            f"- {summary['bp_pending']}", "",
        ])
    if not views:
        lines.extend(["## 今日赛程", "", "- 未找到当日赛程；不生成交易方向。", ""])
    return "\n".join(lines).rstrip() + "\n"


def _normalize_team(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    folded = raw.casefold()
    try:
        catalog = list_teams()
    except Exception:
        return raw.upper()
    for team in catalog:
        candidates = (team.get("short_name"), team.get("name"), team.get("team_id"))
        if any(str(candidate or "").strip().casefold() == folded for candidate in candidates):
            return str(team.get("short_name") or raw).upper()
    return raw.upper()


def _entry_point(market: str, scenario: str, team: str) -> str:
    if market == "kills_over":
        return f"{team} 对手偏弱、BP 有强开/滚雪球条件，或前期已拿主动但人头线未明显抬高时。"
    if market == "time_over":
        return "两队 BP 没有速推/强开滚雪球阵容，前期资源交换偏慢时。"
    if market == "live_entry":
        return f"{team} 前期小劣但经济没崩、阵容团战链仍完整时，等赛中赔率抬高。"
    if market == "handicap":
        return f"{team} 强弱差和 TS 下界同时支持，且让分没有过深时。"
    if market == "winner":
        return f"{team} 基础面和盘口方向同向，且赛前赔率没有被强队热度压得过低时。"
    return "等 BP、首发、盘口或赛中走势补齐后再判断。"


def _primary_note(notes: list[dict]) -> dict | None:
    for note in notes:
        if note.get("market"):
            return note
    return notes[0] if notes else None
