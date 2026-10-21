"""Reusable source-backed evidence, not a second knowledge or analysis store."""
from datetime import date, datetime
import json
import re

from .preparation import ZONE


PUBLIC_KINDS = {"author_analysis", "official_background", "reported_information"}
PUBLIC_EVIDENCE_VERSION = 2


def knowledge_provenance(item: dict) -> dict:
    if item.get("source_kind") != "knowledge_extract" and item.get("verification") != "knowledge_extract":
        return {}
    return {"source_kind": "knowledge_extract", "source": "已有知识提炼整理（未复核原文）",
            "basis_note": "已有知识提炼，未复核原文；是否适用于当前比赛仍需核实。",
            "applicability": item.get("applicability") or "unverified_knowledge_extract"}


def readable_evidence(inputs: list[dict]) -> list[dict]:
    """Publish the actual selected inputs, not their private audit identifiers."""
    from .collection_repository import is_public_url

    def prose(value):
        if not isinstance(value, str) or re.search(r"/home/|/tmp/|file://|Traceback|SKILL\.md", value, re.I):
            return ""
        if value.lstrip().startswith(("{", "[")):
            try:
                if isinstance(json.loads(value), (dict, list)):
                    return ""
            except ValueError:
                pass
        return value.strip()

    rows = []
    for item in inputs:
        if not isinstance(item, dict):
            continue
        text = prose(item.get("display_text")) or prose(item.get("text")) or prose(item.get("evidence_quote"))
        if not text:
            continue
        row = {key: value for key in ("title", "source_title", "source", "published_at", "updated_at", "verification",
                                     "kind", "source_kind", "applicability", "conditions", "counterevidence", "evidence_quote", "basis_note")
               if (value := prose(item.get(key)))}
        row["text"] = text
        if is_public_url(item.get("url")):
            row["url"] = item["url"]
        if row.get("kind", "").endswith("_background"):
            row["basis_note"] = "旧背景，适用于当前对象尚未核实"
        row.update(knowledge_provenance(item))
        rows.append(row)
    return rows


def with_readable_evidence(result: dict | None) -> dict | None:
    """Expose existing citations on reads, including old/frozen cached results.

    No source, revision or stored snapshot is changed; missing old audit data
    stays missing instead of inferring which sources the model might have used.
    """
    if not result:
        return result
    sections = []
    for section in result.get("sections", []):
        if section.get("id") in {"digest", "shared_digest"}:
            section = {**section, "items": [{**item, **knowledge_provenance(item)} for item in section.get("items", [])]}
        if section.get("id") == "analysis":
            section = {**section, "items": [
                {**item, "evidence": readable_evidence(item.get("input_evidence") or item.get("evidence") or [])}
                for item in section.get("items", [])]}
        sections.append(section)
    return {**result, "sections": sections}


def public_inputs(sections: list[dict]) -> list[dict]:
    """Normalize the same cited source for automatic analysis and discussion.

    Only explicitly screened results enter new inferences. Legacy translation
    remains readable through the original reader, never silently reclassified.
    """
    rows, seen = [], set()
    for section in sections:
        if section.get("id") not in {"digest", "shared_digest"} or section.get("selection_status") != "screened":
            continue
        for item in section.get("items", []):
            if not item.get("text") or not item.get("evidence_quote"):
                continue
            kind = "official_background" if item.get("source_category") == "official_background" else item.get("kind", "reported_information")
            if kind not in PUBLIC_KINDS:
                continue
            key = (item.get("source_id") or item.get("url"), item["text"], item["evidence_quote"])
            if key in seen:
                continue
            seen.add(key)
            row = {key: item[key] for key in ("text", "title", "source_title", "source", "verification", "url", "source_id", "content_hash", "published_at", "evidence_quote", "source_category", "source_kind", "related_teams", "roster_status", "conditions", "counterevidence", "prepared_revision", "source_scope", "applicability") if key in item}
            row.update(knowledge_provenance(item))
            for field, label in (("conditions", "适用条件"), ("counterevidence", "反证与限制")):
                addition = f"{label}：{item[field]}" if str(item.get(field) or "").strip() else ""
                if addition and addition not in row["text"]:
                    row["text"] += f"\n{addition}"
            row.setdefault("applicability", "unverified_public_evidence")
            row.update(kind=kind, recognition="system_input")
            rows.append(row)
    return rows


def source_fingerprints(sources: list[dict]) -> list[dict]:
    """Exact body identity only; fetch time and model prose are not revisions."""
    pairs = {(row.get("source_id"), row.get("content_hash")) for row in sources
             if isinstance(row.get("source_id"), str) and row["source_id"]
             and isinstance(row.get("content_hash"), str)
             and re.fullmatch(r"[0-9a-f]{64}", row["content_hash"])}
    return [{"source_id": key, "content_hash": value} for key, value in sorted(pairs)]


def unseen_source_sections(identity: dict, sections: list[dict]) -> list[dict]:
    """A match can reuse an unchanged body only after both teams screened it."""
    if identity.get("scope") or not identity.get("team_b"):
        return sections
    if identity.get("match_date") and date.fromisoformat(identity["match_date"]) < datetime.now(ZONE).date():
        return sections
    coverage = {}
    for section in sections:
        if section.get("id") != "shared_digest" or section.get("selection_status") != "screened":
            continue
        for row in section.get("screened_sources", []):
            for source in source_fingerprints([row]):
                key = (source["source_id"], source["content_hash"])
                coverage.setdefault(key, set()).add(row.get("team"))
    teams = {identity["team_a"], identity["team_b"]}
    covered = {key for key, readers in coverage.items() if teams <= readers}
    return [{**section, "items": [row for row in section.get("items", [])
                                  if row.get("verification") != "source_text"
                                  or row.get("freshness") == "revalidation_failed"
                                  or (row.get("source_id"), row.get("content_hash")) not in covered]}
            if section.get("id") == "news" else section for section in sections]


def prepared_sections(identity: dict, *, as_of: str = "") -> list[dict]:
    """Read source-backed scope results only; dependency direction stays acyclic."""
    if identity.get("scope") or not identity.get("team_a") or not identity.get("event"):
        return []
    if not as_of and identity.get("match_date") and date.fromisoformat(identity["match_date"]) < datetime.now(ZONE).date():
        return []
    from .collection import get_scope_materials
    from .service import get_current_event

    config = get_current_event()
    event = identity["event"]
    aliases = [config.get("event"), *config.get("aliases", []), *config.get("leagues", [])]
    if event.casefold() in {str(value).casefold() for value in aliases if value}:
        event = config.get("event") or event
    subjects = [{"scope": "event", "event": event}, *({"scope": "team", "event": event, "team": identity[side]} for side in ("team_a", "team_b"))]
    related = {identity["team_a"], identity["team_b"]}
    rows, screened = [], []
    for subject in subjects:
        result = (get_scope_materials(subject, as_of=as_of).get("result") or {})
        for row in public_inputs(result.get("sections", [])):
            if row.get("related_teams") and not related.intersection(row["related_teams"]):
                continue
            rows.append({**row, "source_scope": subject, "prepared_revision": result.get("revision")})
        # The source and its selected quote must coexist in the same saved
        # parent snapshot. Old prose alone cannot prove which body was read.
        if subject["scope"] == "team":
            bodies = [row for section in result.get("sections", []) if section.get("id") == "news"
                      for row in section.get("items", [])[:6]
                      if row.get("verification") == "source_text" and row.get("freshness") != "revalidation_failed"]
            for section in result.get("sections", []):
                if section.get("id") != "digest" or section.get("selection_status") != "screened" or section.get("incomplete"):
                    continue
                explicit = {(row["source_id"], row["content_hash"])
                            for row in source_fingerprints(section.get("screened_sources", []))}
                proven = [body for body in bodies if (body.get("source_id"), body.get("content_hash")) in explicit
                          or any(item.get("source_id") == body.get("source_id")
                                 and item.get("evidence_quote") and item["evidence_quote"] in body.get("text", "")[:8000]
                                 and (not item.get("content_hash") or item["content_hash"] == body.get("content_hash"))
                                 for item in section.get("items", []))]
                screened.extend({**row, "team": subject["team"]} for row in source_fingerprints(proven))
    # Each source is represented once even when event and both teams used it.
    unique = public_inputs([{"id": "digest", "selection_status": "screened", "items": rows}])
    section = {"id": "shared_digest", "title": "赛事与双方已准备依据", "selection_status": "screened", "items": unique}
    if screened:
        section["screened_sources"] = screened
    return [section] if unique or screened else []
