"""Contextual access to existing interpretations; discussion never writes knowledge."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import xiaoxue_api.modules.profiles.public as profile_public
import xiaoxue_api.modules.team_data.public as team_public
import xiaoxue_api.modules.tk_knowledge.public as tk_public
import xiaoxue_api.modules.version_understanding.public as version_public

from . import analysis_repository as analysis
from . import collection_repository as materials_repository


HANDLERS = {"version", "team", "cycle", "trading", "match"}
DESCRIPTION_FIELDS = ("title", "purpose", "when_to_use", "what_it_needs", "boundary")
PROFILE_FIELDS = {"positioning": "队伍定位", "win_path": "怎么赢", "lose_path": "怎么输", "key_points": "关键点", "bp_tendency": "BP倾向"}


def catalogue(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cards, seen = [], set()
    if not isinstance(payload.get("methods"), list):
        raise ValueError("判断入口配置不可读")
    for index, row in enumerate(payload["methods"]):
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in DESCRIPTION_FIELDS):
            raise ValueError("判断入口说明不完整")
        key = str(row.get("id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", key) or key in seen:
            raise ValueError("判断入口标识缺失或重复")
        seen.add(key)
        scopes = row.get("scopes")
        if not isinstance(scopes, list) or not scopes or any(scope not in {"event", "team", "match"} for scope in scopes):
            raise ValueError("判断入口适用对象不明确")
        cards.append({**{field: row[field].strip() for field in DESCRIPTION_FIELDS},
                      "id": key, "handler": str(row.get("handler") or ""), "scopes": scopes,
                      "content_type": str(row.get("content_type") or ""), "save_target": str(row.get("save_target") or ""),
                      "status": "ready" if row.get("handler") in HANDLERS else "unavailable",
                      "primary": row.get("primary", True) is not False,
                      "channel": str(row.get("channel") or "workbench"),
                      "order": int(row.get("order", index))})
    return {"version": str(payload.get("version") or "1.0.0"), "methods": sorted(cards, key=lambda row: row["order"])}


def _scope_result(scope: str, event: str, team: str = "", as_of: str = "") -> dict | None:
    from .collection import get_scope_materials
    return get_scope_materials({"scope": scope, "event": event, "team": team}, as_of=as_of).get("result")


def _content(key: str, title: str, text: str, kind: str, updated_at: str = "", recognition: str = "unknown", **extra) -> dict:
    return {"id": key, "title": title, "text": text, "kind": kind,
            "source_label": "小雪整理，未确认采用" if kind == "system_inference" else "已有内容",
            "updated_at": updated_at or "", "recognition": recognition,
            "hash": analysis.fingerprint(text), **extra}


def _saved_contents(result: dict | None, handler: str) -> tuple[list[dict], list[dict]]:
    contents, outputs = [], []
    allowed = {"version": {"version", "version_background"}, "team": {"team_profile", "roster"},
               "cycle": {"cycle"}, "trading": {"knowledge", "confirmed_tk", "candidate_rule"}}
    for section in (result or {}).get("sections", []):
        if not isinstance(section, dict):
            continue
        sid = str(section.get("id") or "")
        if sid == "digest" and section.get("selection_status") != "screened":
            continue
        for index, item in enumerate(section.get("items", [])):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
                continue
            kind = str(item.get("kind") or sid)
            if sid.startswith("team_"):
                kind = "team_profile" if "画像" in str(item.get("source") or "") else "roster" if "选手" in str(item.get("source") or "") else kind
            if sid == "analysis":
                if item.get("method_version") and (handler == "match" or item.get("method_id") == {"version": "version", "team": "version", "cycle": "cycle", "trading": "trading"}.get(handler)):
                    output = {key: item.get(key) for key in ("title", "text", "verification", "inference_scope", "method_id", "method_version")}
                    output["evidence"] = [{"text": str(row.get("display_text") or row.get("evidence_quote") or row.get("text") or ""),
                                           "kind": str(row.get("kind") or ""),
                                           "url": row.get("url") if materials_repository.is_public_url(row.get("url") or "") else ""}
                                          for row in item.get("input_evidence", item.get("evidence", []))
                                          if isinstance(row, dict) and (row.get("display_text") or row.get("evidence_quote") or row.get("text"))]
                    outputs.append(output)
                continue
            if handler != "match" and kind not in allowed.get(handler, set()) and sid not in allowed.get(handler, set()) and sid not in {"digest", "news"} and not (handler == "team" and sid.startswith("team_")):
                continue
            if sid == "news":
                continue  # Raw articles are not a second wall of text.
            text = item["text"]
            for field, label in (("conditions", "适用条件"), ("counterevidence", "反证与限制")):
                if str(item.get(field) or "").strip():
                    text += f"\n{label}：{item[field]}"
            source_title = str(item.get("title") or "")
            if sid == "digest" and not source_title:
                from urllib.parse import urlparse
                host = urlparse(str(item.get("url") or "")).hostname or "公开来源"
                source_title = ("作者分析：" if kind == "author_analysis" else "公开信息：") + host
            contents.append(_content(f"saved-{analysis.fingerprint([sid, index, item.get('source_id'), text])}",
                                     str(source_title or section.get("title") or "相关依据"), text,
                                     "system_inference" if sid in {"analysis", "comparison"} else kind,
                                     str(item.get("updated_at") or (result or {}).get("as_of") or ""),
                                     "system" if sid in {"analysis", "comparison"} else "unknown",
                                     source_label=("作者观点 · AI整理，请结合原文" if kind == "author_analysis" else "公开信息 · AI整理，请结合原文") if sid == "digest" else str(item.get("source") or "已有准备内容"),
                                     record_id=item.get("record_id"),
                                     subject_team=sid[5:] if sid.startswith("team_") else "",
                                     url=item.get("url") if materials_repository.is_public_url(item.get("url") or "") else "",
                                     evidence_quote=str(item.get("evidence_quote") or ""), published_at=str(item.get("published_at") or "")))
    return contents, outputs


def _as_of(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("查看截止时刻需要包含时区") from exc
    return parsed.isoformat()


def context(values: dict, cards: dict) -> dict:
    from . import service, collection
    key = str(values.get("method_id") or "")
    method = next((card for card in cards["methods"] if card["id"] == key), None)
    if method is None:
        raise ValueError("没有找到这个判断入口")
    handler = method["handler"]
    event = str(values.get("event") or service.get_current_event().get("event") or "").strip()
    team = str(values.get("team") or "").strip().upper()
    if len(event) > 120 or len(team) > 40 or any(c in team for c in ("/", "\\", "\n", "\x00")):
        raise ValueError("判断对象不正确")
    cutoff = _as_of(str(values.get("as_of") or ""))
    identity, run = None, {}
    if values.get("team_a") and values.get("team_b"):
        identity = collection._identity({**values, "event": event})
        run = service.get_match_run(identity)
        if run.get("mode") == "virtual_pre" and not run.get("result_unlocked"):
            start = datetime.fromisoformat(f"{identity['match_date']}T{identity['match_time']}").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            if not cutoff or datetime.fromisoformat(cutoff) > start:
                cutoff = start.isoformat()
    if handler == "version" and not identity:
        team = ""  # A leftover team selection is not a new version question.
    teams = list(dict.fromkeys([team] if team else [identity[side] for side in ("team_a", "team_b")] if identity else []))
    needed = ["team"] if handler == "team" and not teams else ["match"] if handler in {"cycle", "match"} and not identity else []
    response = {"method": method, "object": {"event": event, "team": team, "match": identity},
                "status": "unavailable" if method["status"] != "ready" else "needs_context" if needed else "ok",
                "needed": needed, "contents": [], "analysis": [], "limitations": [], "revision": "", "discussion_available": False, "as_of": cutoff}
    if response["status"] != "ok":
        return response
    contents, outputs, limitations = [], [], []
    try:
        if identity:
            result = collection.get_prepared_materials(identity, as_of=cutoff).get("result")
        else:
            # The event version does not disappear when a previous view left a
            # team selected. Team-specific caches supplement that shared base.
            result = _scope_result("team" if team and handler != "version" else "event", event, team if handler != "version" else "", cutoff)
        frozen, outputs = _saved_contents(result, handler)
        contents.extend(frozen)
        if identity or (team and handler != "version"):
            shared_subjects = [("event", ""), *[("team", code) for code in teams]] if identity else [("event", "")]
            for shared_scope, shared_team in shared_subjects:
                shared, _ = _saved_contents(_scope_result(shared_scope, event, shared_team, cutoff), handler)
                # A scope-wide inference is not automatically a match-specific
                # inference. Only shared evidence is carried into this view.
                contents.extend(row for row in shared if row["kind"] != "system_inference")
    except (LookupError, OSError, ValueError, RuntimeError, TypeError):
        limitations.append("已有准备结果暂时不可读，其他内容仍可使用。")
    if not cutoff:
        if handler in {"version", "team", "match"}:
            try:
                payload = version_public.get_global_version_understanding()
                row = (payload.get("data") or {}).get("item") or {}
                if payload.get("status") == "ok" and row.get("content"):
                    contents = [item for item in contents if not (item["kind"] in {"version", "version_background"} and str(item.get("record_id")) == str(row.get("id")))]
                    contents.append(_content(f"version-{row.get('id', 'current')}", str(row.get("topic") or "版本理解"),
                                             str(row["content"]), "version", str(row.get("created_at") or ""), record_id=row.get("id")))
                    limitations.append("已有版本理解尚需核对本届实际比赛版本，不能直接当成本届已成立的结论。")
            except (LookupError, OSError, ValueError, RuntimeError):
                limitations.append("版本理解暂时不可读。")
        if handler in {"team", "match"}:
            for code in teams:
                try:
                    row = profile_public.get_current_profile(code)
                    text = "\n".join(f"{label}：{row.get('profile', {}).get(field, '')}" for field, label in PROFILE_FIELDS.items() if str(row.get("profile", {}).get(field) or "").strip())
                    if row.get("found") and text:
                        contents = [item for item in contents if not (item["kind"] == "team_profile" and item.get("subject_team") == code)]
                        contents.append(_content(f"team-{code}", f"{code}已有队伍画像", text, "team_profile", str(row.get("updated_at") or "")))
                        limitations.append(f"{code}画像的本届适用性需结合人员和近期表现核对。")
                    players = team_public.list_players(code)
                    if players:
                        contents = [item for item in contents if not (item["kind"] == "roster" and item.get("subject_team") == code)]
                        contents.append(_content(f"roster-{code}", f"{code}已有登记名单", "、".join(f"{p.get('role', '')} {p.get('name', '')}".strip() for p in players), "roster", source_label="登记名单，不等于本场已确认首发"))
                except (LookupError, OSError, ValueError, RuntimeError):
                    limitations.append(f"{code}的部分已有资料暂时不可读。")
        if handler in {"trading", "match"}:
            try:
                rows = tk_public.list_match_trading_tk(teams=teams, region="", players=[], limit=12)
                for index, row in enumerate(rows.get("items", rows.get("notes", []))):
                    text = str(row.get("original") or row.get("content") or row.get("statement") or row.get("text") or "").strip()
                    if text:
                        for field, label in (("context", "适用条件"), ("version_context", "适用版本"), ("review_note", "复查与反例")):
                            if str(row.get(field) or "").strip():
                                text += f"\n{label}：{row[field]}"
                        reference = analysis.fingerprint(row.get("filename") or [index, text])
                        contents.append(_content(f"tk-{reference}", str(row.get("title") or "已有交易规律"), text, "trading_tk", str(row.get("updated_at") or row.get("created_at") or ""), str(row.get("status") or "unknown"), source_ref=reference))
            except (LookupError, OSError, ValueError, RuntimeError):
                limitations.append("相关交易规律暂时不可读。")
        if handler == "cycle" and identity:
            for row in analysis.collect_inputs(identity, []):
                if row.get("kind") == "cycle" and row.get("comparable"):
                    contents.append(_content("cycle-current", "周期与近期比赛依据", row.get("display_text") or row["text"], "cycle"))
            if not any(row["kind"] == "cycle" for row in contents):
                limitations.append("双方当前数据不满足原周期方法的比较条件，不硬套分差。")
        if handler == "match":
            for index, entry in enumerate(run.get("entries") or []):
                if isinstance(entry, dict) and str(entry.get("content") or "").strip():
                    contents.append(_content(f"user-entry-{index}", str(entry.get("label") or "本场已有个人记录"), str(entry["content"]), "user_record", str(entry.get("updated_at") or ""), "user_record", source_label="你的原记录，不自动代表当前采用"))
            virtual = run.get("virtual_judgment") or {}
            text = "\n".join(f"{label}：{virtual[key]}" for key, label in (("direction", "原判断"), ("reasons", "理由"), ("handling", "处理"), ("change_conditions", "改变条件")) if virtual.get(key))
            if text:
                contents.append(_content("user-judgment", "本场已有个人判断", text, "user_record", str(run.get("updated_at") or ""), "user_record", source_label="你的原记录，不自动代表当前采用"))
    elif not contents:
        limitations.append("该截止时点尚无可读的冻结依据，不用今天的认识补写过去。")
    # A current canonical record supersedes its cached copy; duplicate text is read once.
    unique = {}
    for row in contents:
        unique[row["hash"]] = row
    contents = list(unique.values())
    if handler == "team":
        contents.sort(key=lambda row: {"team_profile": 0, "roster": 1}.get(row["kind"], 2))
    if cutoff and contents:
        limitations.append("此处只读当时冻结依据；尚未保留当时完整方法正文，不用现有方法重写历史判断。")
    response.update(contents=contents, analysis=outputs, limitations=list(dict.fromkeys(limitations)), discussion_available=bool(contents) and not cutoff,
                    revision=analysis.fingerprint({"method": method["id"], "object": response["object"], "cutoff": cutoff,
                                                   "contents": [{"id": row["id"], "hash": row["hash"], "recognition": row["recognition"]} for row in contents],
                                                   "analysis": outputs}))
    return response


def discuss(values: dict, cards: dict) -> dict:
    question = str(values.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise ValueError("请写下这次想判断的问题，最多2000字")
    history = values.get("history") or []
    if not isinstance(history, list) or len(history) > 8 or any(not isinstance(row, dict) or row.get("role") not in {"user", "assistant"} or not isinstance(row.get("content"), str) or len(row["content"]) > 4000 for row in history):
        raise ValueError("本次讨论记录过长或格式不正确")
    data = context(values, cards)
    if data["status"] != "ok" or not data["discussion_available"]:
        raise ValueError("请先选择对应对象并取得可用内容，再继续判断")
    handler = data["method"]["handler"]
    method_key = "version" if handler in {"version", "team"} else "cycle" if handler == "cycle" else "trading"
    title, paths = analysis.METHODS[method_key]
    instruction = "\n\n".join((analysis.SKILLS / path).read_text(encoding="utf-8") for path in paths)
    packet = {"operation": "judgment_discussion", "object": data["object"], "question": question, "history": history,
              "methods": [{"id": method_key, "title": title, "instruction": instruction, "version": analysis.fingerprint(instruction)}],
              "inputs": [{**row, "text": row["text"][:8000], "text_limited": len(row["text"]) > 8000} for row in data["contents"][:18]],
              "limitations": data["limitations"], "as_of": data["as_of"], "context_revision": data["revision"], "user_confirmed": False}
    try:
        result = json.loads(materials_repository.call_digest_model(packet))
        answer, ids = result.get("answer"), result.get("source_ids")
        refs = {row["id"]: row for row in packet["inputs"]}
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000 or not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in refs for key in ids):
            raise ValueError("unsupported discussion")
    except Exception as exc:
        raise RuntimeError("这次讨论暂未完成，已有内容仍保留，可以稍后重试。") from exc
    return {"answer": answer.strip(), "references": [{"id": key, "title": refs[key]["title"]} for key in dict.fromkeys(ids)],
            "context_revision": data["revision"], "saved": False}
