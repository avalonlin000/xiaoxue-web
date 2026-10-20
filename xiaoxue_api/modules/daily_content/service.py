from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from workflow_contracts import build_daily_content_files
import xiaoxue_api.modules.current_event.public as current_event_public
from xiaoxue_api.modules.team_data.public import list_schedules
from xiaoxue_api.modules.current_event.public import get_current_event_scope_leagues, match_in_current_event_scope

from . import repository


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MATCH_CONTENT_KINDS = {"daily_report"}


class ConfigurationUnavailable(RuntimeError):
    pass


def get_operating_state() -> dict:
    try:
        daily = repository.load_config().get("daily_content") or {}
    except (OSError, ValueError, TypeError):
        return {"state": "unknown", "message": "日报运行状态配置不可用"}
    return {
        "state": daily.get("operating_state", "active"),
        "message": daily.get("operating_message", ""),
    }


def resolve_date(value: str | None) -> str:
    raw = (value or "today").strip().lower()
    if raw == "today":
        return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    if not DATE_RE.fullmatch(raw):
        raise ValueError("非法 date 参数；只支持 today 或 YYYY-MM-DD")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("非法 date 参数；只支持 today 或 YYYY-MM-DD") from exc
    return raw


def get_daily_content(date: str = "today") -> dict:
    date_str = resolve_date(date)
    try:
        config = repository.load_config()
        files = build_daily_content_files(config, date_str)
    except (OSError, ValueError) as exc:
        raise ConfigurationUnavailable(f"日报模块配置不可用：{exc}") from exc
    matches = list_schedules({"date_from": date_str, "date_to": date_str}, 200)
    leagues = get_current_event_scope_leagues()
    matches = [match for match in matches if match_in_current_event_scope(match, leagues)]
    items = []
    report = _publication_state(date_str)
    for key, meta in files.items():
        artifact = repository.read_artifact(meta["path"])
        if meta["kind"] == "daily_report":
            receipt = repository.read_publication_manifest(meta["path"], date_str)
            report = _publication_state(date_str, receipt, meta["path"], artifact)
        items.append({
            "id": key,
            "title": meta["title"],
            "kind": meta["kind"],
            "path": meta["path"],
            "exists": artifact["exists"],
            "updated_at": datetime.fromtimestamp(artifact["updated_at"]).isoformat(timespec="seconds")
            if artifact["updated_at"] else None,
            "size_bytes": artifact["size_bytes"],
            "summary": summarize(artifact["content"]),
            "required": meta["kind"] in MATCH_CONTENT_KINDS,
        })
    day_state = "ready" if report["publication_status"] == "verified" else (
        "content_missing" if matches else "no_matches")
    daily_config = config.get("daily_content") or {}
    operating = {
        "state": daily_config.get("operating_state", "active"),
        "message": daily_config.get("operating_message", ""),
        "observed_publication_status": report["publication_status"],
        "state_difference": daily_config.get("operating_state") == "paused_by_user"
        and report["published"],
    }
    if operating["state_difference"]:
        operating["state_difference_message"] = (
            "配置标记为主动暂停，但当天存在已发布回执；暂停时间未知，不据此认定自动化仍在运行。"
        )
    latest, latest_status = _latest_materials(date_str)
    return {
        "ok": True, "date": date_str, "source": "local_whitelist",
        "day_state": day_state, "match_count": len(matches), "matches": matches, "items": items,
        "report": report, "operating_state": operating,
        "latest_matches": latest, "latest_matches_status": latest_status,
    }


def _reader_url(value) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
    except ValueError:
        return ""
    return value


def _publication_state(date_str: str, receipt=None, report_path="", artifact=None) -> dict:
    receipt = receipt or {"status": "missing", "manifest": {}}
    manifest = receipt.get("manifest") or {}
    report = {
        "date": date_str, "run_id": "", "snapshot_at": None,
        "published": False, "publication_status": receipt["status"], "url": "",
        "verification": {"manifest_valid": False, "audit_ok": False, "artifact_matches": False,
                         "destinations": {}, "parts_verified": False},
    }
    if receipt["status"] != "ok":
        return report
    if manifest.get("schema") != "xiaoxue-daily-run-manifest-v2" or manifest.get("date") != date_str:
        report["publication_status"] = "invalid"
        return report
    destinations = manifest.get("destinations")
    destinations = destinations if isinstance(destinations, dict) else {}
    statuses = {}
    for name in ("scripts", "wiki", "feishu"):
        destination = destinations.get(name)
        statuses[name] = destination.get("status", "missing") if isinstance(destination, dict) else "missing"
    feishu = destinations.get("feishu")
    feishu = feishu if isinstance(feishu, dict) else {}
    parts = feishu.get("parts")
    parts_verified = (isinstance(parts, list) and bool(parts) and feishu.get("part_count") == len(parts)
                      and feishu.get("semantic_errors", []) == [] and all(
                          isinstance(part, dict) and part.get("status") == "verified"
                          and part.get("semantic_errors", []) == [] for part in parts))
    artifacts = manifest.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    expected_hash = artifacts.get(Path(report_path).name)
    artifact_matches = bool(artifact and artifact.get("exists") and expected_hash
                            and expected_hash == artifact.get("sha256"))
    audit_ok = manifest.get("audit_ok") is True and manifest.get("validation_errors") == []
    url = _reader_url(feishu.get("url"))
    run_id = manifest.get("run_id")
    snapshot_at = manifest.get("snapshot_at") or manifest.get("as_of") or manifest.get("created_at")
    snapshot_identity = isinstance(run_id, str) and bool(run_id) and isinstance(snapshot_at, str) and bool(snapshot_at)
    verified = (manifest.get("published") is True and audit_ok and artifact_matches and bool(url) and snapshot_identity
                and parts_verified and all(status == "verified" for status in statuses.values())
                and all(isinstance(destinations.get(name), dict)
                        and destinations[name].get("matches_source") is True for name in ("scripts", "wiki")))
    mode = manifest.get("mode")
    if verified:
        status = "verified"
    elif isinstance(mode, str) and mode in {"blocked-by-data-readiness", "blocked-by-audit", "dry-run"}:
        status = mode
    elif manifest.get("published") is True:
        status = "unverified"
    elif "failed" in statuses.values():
        status = "failed"
    else:
        status = "unpublished"
    report.update({
        "run_id": run_id if isinstance(run_id, str) else "",
        "snapshot_at": snapshot_at if isinstance(snapshot_at, str) else None,
        "snapshot_at_basis": "snapshot_at" if manifest.get("snapshot_at") else (
            "as_of" if manifest.get("as_of") else "manifest_created_at"),
        "published": manifest.get("published") is True,
        "publication_status": status, "url": url,
        "verification": {"manifest_valid": True, "audit_ok": audit_ok, "artifact_matches": artifact_matches,
                         "destinations": statuses, "parts_verified": parts_verified,
                         "snapshot_identity": snapshot_identity},
    })
    return report


def _latest_materials(date_str: str) -> tuple[list, str]:
    try:
        payload = current_event_public.list_prepared_materials(date_str, limit=200)
        if not isinstance(payload, dict) or payload.get("date") != date_str or not isinstance(payload.get("items"), list):
            return [], "unavailable"
        items = payload["items"]
        return items, "ok" if items else "empty"
    except Exception:
        return [], "unavailable"


def summarize(text: str, max_chars: int = 180) -> str:
    if not text:
        return ""
    lines, in_frontmatter = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not line:
            continue
        lines.append(line.lstrip("#").strip() if line.startswith("#") else line)
        if len(" ".join(lines)) >= max_chars:
            break
    summary = " ".join(lines).strip()
    return summary[:max_chars].rstrip() + "…" if len(summary) > max_chars else summary
