"""Bounded execution of existing methods; stores no user or formal knowledge writes."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

from . import collection_repository as repository


SKILLS = Path("/home/ubuntu/.agents/skills")
METHODS = {
    "cycle": ("周期与实力判断", ["esports/lol-cycle/references/tournament.md"]),
    "version": ("版本与双方赢输法", ["esports/xiaoxue-version-team-brief/SKILL.md"]),
    "trading": ("主要矛盾与失效条件", ["trading/junjun-trading-system/SKILL.md", "trading/junjun-trading-system/references/pre-match-preparation.md"]),
}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def collect_library(identity: dict) -> tuple[list[dict], list[str]]:
    from xiaoxue_api.modules.tk_knowledge.public import browse, get_entry
    rows, seen = [], set()
    for team in (identity["team_a"], identity["team_b"]):
        kept = 0
        # Limit useful knowledge, not the mixed stream of knowledge/trading TK.
        for offset in range(0, 150, 30):
            page = browse(period="30d", team=team, offset=offset, limit=30)
            for record in page.get("results", []):
                name = record["filename"]
                if name in seen or record.get("type") != "knowledge_tk":
                    continue
                seen.add(name)
                entry = get_entry(name)
                text = entry.get("content", "")[:8000]
                if len(text) < 120:
                    continue
                rows.append({"title": entry.get("concept") or "相关已有分析", "text": text,
                             "source_id": fingerprint({"document": name}), "content_hash": fingerprint(text),
                             "source": "已有知识提炼，非原始全文", "published_at": entry.get("date", ""),
                             "verification": "knowledge_extract", "url": ""})
                kept += 1
                if kept == 3:
                    break
            if kept == 3 or not page.get("has_more"):
                break
    return ([{"id": "library", "title": "相关已有分析依据", "items": rows}] if rows else []), []


def collect_inputs(identity: dict, sections: list[dict]) -> list[dict]:
    from .service import list_score_match_results
    from xiaoxue_api.modules.fundamentals.public import get_match_context
    # Present-day knowledge must not become historical pre-match evidence.
    if date.fromisoformat(identity["match_date"]) < datetime.now(ZoneInfo("Asia/Shanghai")).date():
        return []
    evidence = []
    for section in sections:
        if not section.get("id", "").startswith("team_") and section.get("id") != "knowledge":
            continue
        for item in section.get("items", []):
            if item.get("source") == "已有队伍画像" or section.get("id") == "knowledge":
                current_profile = (item.get("applicability") == "verified" and item.get("applicable_event") == identity.get("event") and bool(item.get("applicability_evidence")))
                evidence.append({"kind": ("team_profile" if current_profile else "team_profile_background") if section.get("id") != "knowledge" else "confirmed_tk" if item.get("verification") == "confirmed" else "candidate_rule",
                                 "text": f"{section.get('title', '')}：{item.get('text', '')}", "updated_at": item.get("updated_at")})
    try:
        context = get_match_context(identity["team_a"], identity["team_b"], event=identity.get("event", ""))
        sides = [context.get(side) or {} for side in ("team_a", "team_b")]
        # INTL is an event bucket, not proof that two teams share a rating scale.
        comparable = sides[0].get("region") in {"LPL", "LCK"} and sides[0].get("region") == sides[1].get("region")
        complete = comparable and all(all(row.get(key) is not None and str(row[key]).strip() for key in ("power_score", "volatility_score", "trend", "momentum", "status")) for row in sides)
        recent = {}
        cutoff = (date.fromisoformat(identity["match_date"]) - timedelta(days=1)).isoformat()
        if complete:
            for team in (identity["team_a"], identity["team_b"]):
                recent[team] = list_score_match_results(team=team, date_to=cutoff, limit=2).get("results", [])
            complete = all(len(rows) >= 2 for rows in recent.values())
        if complete:
            fields = ("team", "region", "power_score", "volatility_score", "trend", "momentum", "status", "cycle")
            display = "\n".join(f"{row['team']}：综合实力 {row['power_score']}，稳定性 {row['volatility_score']}，趋势 {row['trend']}，势头 {row['momentum']}。" for row in sides)
            display += "\n" + "\n".join(f"{team} 最近赛果：" + "；".join(f"{r.get('match_time', '')} {r.get('team_a')} {r.get('score_a')}:{r.get('score_b')} {r.get('team_b')}" for r in rows) for team, rows in recent.items())
            evidence.append({"kind": "cycle", "comparable": True, "display_text": display, "text": json.dumps({"teams": [{key: row.get(key) for key in fields} for row in sides], "recent": recent}, ensure_ascii=False)})
    except Exception:
        pass
    try:
        # The old brief collector still reads July stage rows and retired skill
        # mirrors. Use the existing current-object public source, never those.
        from xiaoxue_api.modules.version_understanding.public import get_global_version_understanding
        payload = get_global_version_understanding()
        item = (payload.get("data") or {}).get("item") or {}
        if payload.get("status") == "ok" and item.get("content"):
            text = f"已有版本理解（尚未核对本场比赛版本）：{item.get('topic', '')}\n{item['content']}"
            evidence.append({"kind": "version_background", "text": text[:12000], "updated_at": item.get("created_at")})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return [{**row, "id": f"I{index}"} for index, row in enumerate(evidence, 1)]


def analyze(identity: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    inputs = collect_inputs(identity, sections)
    eligible = {"trading"} if any(row.get("kind") in {"team_profile", "confirmed_tk", "candidate_rule"} for row in inputs) else set()
    if any(row.get("kind") == "cycle" and row.get("comparable") for row in inputs):
        eligible.update({"cycle", "trading"})
    if any(row.get("kind") == "version" for row in inputs):
        eligible.add("version")
    if not eligible:
        return [], repository.PendingInputs(["现有资料尚不足以按原方法推导本场，不用泛泛结论代替分析"])
    try:
        methods = []
        for key in sorted(eligible):
            title, paths = METHODS[key]
            instruction = "\n\n".join((SKILLS / path).read_text() for path in paths)
            methods.append({"id": key, "title": title, "version": fingerprint(instruction), "instruction": instruction})
        public = [{**item, "id": f"P{index}"} for index, item in enumerate(
            [item for section in sections if section.get("id") == "digest" for item in section.get("items", [])], 1)]
        scope = "supported" if any(row.get("kind") in {"team_profile", "cycle", "version"} for row in inputs) else "conditional"
        packet = {"operation": "match_analysis", "match": identity, "as_of": repository.now(), "methods": methods,
                  "inputs": inputs, "public_analysis": public, "inference_scope": scope,
                  "team_strength_roles": None, "user_adopted_rule": False, "market": None}
        payload = json.loads(repository.call_digest_model(packet))
        versions = {m["id"]: m["version"] for m in methods}
        refs = {row["id"]: row for row in inputs}
        revision = fingerprint(inputs)
        items, used = [], set()
        for index, row in enumerate(payload.get("items", [])[:3], 1):
            method, ids = row.get("method_id"), row.get("source_ids")
            if method not in eligible or method in used or not isinstance(ids, list) or not ids or any(not isinstance(ref, str) or ref not in refs for ref in ids):
                continue
            if any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("text", "basis", "confirmation", "invalidation")):
                continue
            if method in {"trading", "version"}:
                windows = row["confirmation"] + row["invalidation"]
                for team in (identity["team_a"], identity["team_b"]):
                    windows = windows.replace(team, "")
                number = r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)"
                if re.search(number + r"\s*(?:分钟|秒|%|％|成胜率|块经济)" + r"|(?:经济|人头|击杀|赔率|胜率|仓位)[^，。；]{0,8}\d", windows):
                    continue
            if method == "cycle" and not any(refs[ref].get("kind") == "cycle" for ref in ids):
                continue
            if method == "version" and not any(refs[ref].get("kind") == "version" for ref in ids):
                continue
            used.add(method)
            items.append({"id": f"M{index}", "title": METHODS[method][0] + ("（条件推导）" if scope == "conditional" else ""), "method_id": method,
                          "method_version": versions[method], "input_revision": revision, "as_of": packet["as_of"],
                          "inference_scope": scope,
                          "text": f"{row['text'][:700]}\n依据：{row['basis'][:500]}\n确认：{row['confirmation'][:400]}\n失效：{row['invalidation'][:400]}",
                          "verification": "system_inference", "source": "按现有方法推导，未确认采用", "source_ids": ids,
                          "evidence": [{"text": refs[ref].get("display_text", refs[ref]["text"])} for ref in ids],
                          "input_evidence": [refs[ref] for ref in ids]})
        if not items:
            return [], ["本次个人方法推导未取得有依据的结果，已保留其他内容"]
        outputs = [{"id": "analysis", "title": "按我的方法看本场", "items": items}]
        comparisons = []
        personal_refs = {item["id"] for item in items}
        public_refs = {item["id"] for item in public}
        for row in payload.get("comparison", [])[:3]:
            if row.get("public_id") in public_refs and row.get("analysis_id") in personal_refs and row.get("relation") in {"agree", "disagree", "conditional"} and isinstance(row.get("text"), str) and row["text"].strip():
                comparisons.append({"text": row["text"][:700], "verification": "system_inference", "source": "公开观点与个人方法对照", "source_ids": [row["public_id"], row["analysis_id"]]})
        if comparisons:
            outputs.append({"id": "comparison", "title": "两边怎么看", "items": comparisons})
        return outputs, []
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return [], ["本次个人方法分析未完成，其他已筛内容仍可阅读"]


def _asserts_confirmed_roster(text: str) -> bool:
    """Reject affirmative roster confirmation, retaining unknown/conditional prose."""
    for clause in re.split(r"[。；;\n]", text):
        if not re.search(r"首发|名单|阵容", clause):
            continue
        for assertion in re.finditer(r"(?:确认|确定).{0,25}(?:首发|名单|阵容)|(?:首发|名单|阵容)(?:已确认|已确定|为|是)", clause):
            prefix = clause[:assertion.start()]
            if re.search(r"(?:尚未|没有|不能|无法|不足以|未|待|有待|不代表|并非).{0,8}$", prefix):
                continue
            if re.match(r"\s*(?:若|如果|假如|待|只有|除非)", clause):
                continue
            return True
    return False


def analyze_scope(identity: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    """Apply the existing version lens without fabricating two-team input."""
    inputs = []
    for section in sections:
        if section.get("id") == "digest":
            for row in section.get("items", []):
                if not row.get("text") or not row.get("evidence_quote"):
                    continue
                inputs.append({"kind": "official_background" if row.get("source_category") == "official_background" else row.get("kind", "reported_information"),
                               "title": row.get("source_title") or row.get("title", ""), "url": row.get("url", ""),
                               "source_category": row.get("source_category", "unclassified"), "subject": identity,
                               "roster_status": row.get("roster_status", "not_officially_confirmed"),
                               "text": row["text"], "evidence_quote": row["evidence_quote"], "source_id": row.get("source_id"),
                               "published_at": row.get("published_at"), "applicability": "current_public_evidence", "recognition": "system_input"})
        elif section.get("id") == "version" or section.get("id", "").startswith("team_"):
            for row in section.get("items", []):
                if row.get("text") and "登记选手" not in row.get("source", ""):
                    inputs.append({"kind": "version_background" if section["id"] == "version" else "team_profile_background",
                                   "text": row["text"], "content_hash": row.get("content_hash"), "record_id": row.get("record_id"),
                                   "applicability": row.get("applicability", "unverified"), "recognition": row.get("recognition", "unknown")})
    if not any(row["kind"] in {"author_analysis", "official_background"} for row in inputs):
        return [], repository.PendingInputs(["当前公开证据尚不足以对照已有认识，不以旧背景生成本届结论"])
    refs = {f"I{index}": {**row, "id": f"I{index}"} for index, row in enumerate(inputs, 1)}
    try:
        instruction = "\n\n".join((SKILLS / path).read_text() for path in METHODS["version"][1])
        method_version = fingerprint(instruction)
        packet = {"operation": "scope_analysis", "subject": identity, "as_of": repository.now(),
                  "methods": [{"id": "version", "title": "版本与当前对象理解", "version": method_version, "instruction": instruction}],
                  "inputs": list(refs.values()), "inference_scope": "conditional", "user_adopted_rule": False, "market": None}
        payload = json.loads(repository.call_digest_model(packet))
        items = []
        for row in payload.get("items", [])[:1]:
            ids = row.get("source_ids")
            if row.get("method_id") != "version" or not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in refs for key in ids):
                continue
            if not any(refs[key]["kind"] in {"author_analysis", "official_background"} for key in ids):
                continue
            if any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("text", "basis", "confirmation", "invalidation")):
                continue
            official_roster = any(refs[key].get("source_category") == "official_background" and refs[key].get("roster_status") == "officially_confirmed" for key in ids)
            if not official_roster and _asserts_confirmed_roster(row["text"] + "\n" + row["basis"]):
                continue
            items.append({"id": "M1", "method_id": "version", "title": "已有认识与当前证据对照", "verification": "system_inference",
                          "source": "按原版本理解方法推导，未确认采用", "inference_scope": "conditional", "method_version": method_version,
                          "input_revision": fingerprint(list(refs.values())), "source_ids": ids, "input_evidence": [refs[key] for key in ids],
                          "text": f"{row['text'][:700]}\n依据：{row['basis'][:500]}\n确认：{row['confirmation'][:400]}\n失效：{row['invalidation'][:400]}"})
        return ([{"id": "analysis", "title": "按已有方法理解", "items": items}] if items else []), ([] if items else ["当前方法对照未取得有依据的结果"])
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return [], ["当前方法对照未完成，其他已筛内容仍可阅读"]
