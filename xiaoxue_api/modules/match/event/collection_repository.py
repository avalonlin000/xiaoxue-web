"""I/O for current-event materials, separate from personal/knowledge records."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import urllib.request
import socket
import subprocess
import time
from time import monotonic
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode, quote
from zoneinfo import ZoneInfo

import httpx

from xiaoxue_api.core.web_search import search_web_json

from .preparation import kickoff
from .evidence import with_readable_evidence

COLLECTOR_VERSION = 10
# Per-match depth agreed with 钧钧 (2026-10-22): aim at ten usable articles, and
# allow more reads because roughly half of the pages fetched are navigation text.
MATCH_ARTICLE_TARGET = 10
MATCH_READ_ATTEMPTS = 24
SEARCH_QUERIES_PER_RUN = 6
SEARCH_RESULTS_PER_QUERY = 8
TEAM_ARTICLE_TARGET = 6
_deadline = ContextVar("collection_deadline", default=None)
_source_counts = ContextVar("collection_source_counts", default=None)
_attempt_number = ContextVar("collection_attempt_number", default=1)


class CollectionBudgetExpired(TimeoutError):
    pass


class PendingInputs(list):
    """Evidence not available/applicable yet, not a transient execution fault."""
    pass


class IncompleteCollection(list):
    """Usable source text was retained, but discovery still needs recovery."""
    pass


@contextmanager
def collection_budget(seconds: float = 720, *, attempt: int | None = None):
    previous = _deadline.get()
    limit = monotonic() + seconds
    token = _deadline.set(min(previous, limit) if previous is not None else limit)
    source_token = _source_counts.set({"search": 0, "body": 0}) if previous is None else None
    attempt_token = _attempt_number.set(attempt) if attempt is not None else None
    try:
        yield
    finally:
        _deadline.reset(token)
        if source_token is not None:
            _source_counts.reset(source_token)
        if attempt_token is not None:
            _attempt_number.reset(attempt_token)


def remaining_timeout(limit: float) -> float:
    deadline = _deadline.get()
    if deadline is None:
        return limit
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise CollectionBudgetExpired("本轮资料准备已到总耗时预算")
    return min(limit, remaining)


def check_budget() -> None:
    remaining_timeout(720)


def collection_attempt() -> int:
    return _attempt_number.get()


def consume_source_budget(kind: str, limit: int) -> bool:
    counts = _source_counts.get()
    if counts is None:
        return True
    if counts[kind] >= limit:
        return False
    counts[kind] += 1
    return True


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def root() -> Path:
    return Path(os.environ.get("XIAOXUE_COLLECTION_DIR", str(Path(__file__).resolve().parents[4] / "data" / "current_event_materials")))


WORKER_POOLS = {"match": 2, "scope": 1}


def worker_slot_paths(pool: str, directory: Path | None = None) -> list[Path]:
    """分池：单场比赛和赛事/队伍共用资料各自占用席位，互不抢占。"""
    if pool not in WORKER_POOLS:
        raise ValueError("未知的资料并发池")
    base = directory or (root() / ".scheduler")
    return [base / f"worker-{pool}-{index}.lock" for index in range(WORKER_POOLS[pool])]


@contextmanager
def collection_worker_slot(worker_slot_fd: int | None = None, pool: str = "match"):
    """Share bounded worker slots per pool across API, CLI and scheduler processes."""
    directory = root() / ".scheduler"
    directory.mkdir(parents=True, exist_ok=True)
    slots = worker_slot_paths(pool, directory)
    if worker_slot_fd is not None:
        supplied = os.fstat(worker_slot_fd)
        if not any(path.exists() and (path.stat().st_dev, path.stat().st_ino) == (supplied.st_dev, supplied.st_ino) for path in slots):
            raise ValueError("后台任务没有有效的共享并发席位")
        yield worker_slot_fd
        return
    handles = [path.open("a") for path in slots]
    try:
        while True:
            for handle in handles:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                try:
                    yield handle.fileno()
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                return
            time.sleep(0.1)
    finally:
        for handle in handles:
            handle.close()


def valid_id(task_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{24}", task_id):
        raise ValueError("无效的比赛资料任务")
    return task_id


def task_id_for(identity: dict) -> str:
    return hashlib.sha256((identity.get("scope_key") or identity["match_key"]).encode()).hexdigest()[:24]


def subject_of(task: dict) -> dict:
    return task.get("subject") or task.get("match") or {}


def identity_field(identity: dict) -> str:
    return "subject" if identity.get("scope") in {"event", "team"} else "match"


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def _locked(task_id: str):
    directory = root() / valid_id(task_id)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield directory
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read(task_id: str) -> dict:
    directory = root() / valid_id(task_id)
    task, result = _load(directory / "task.json"), _load(directory / "latest.json")
    if task and not result:
        staged = _load(directory / "checkpoint.json") or {}
        if staged.get("generation") == task["generation"]:
            sections = [section for stage in staged.get("stages", {}).values() for section in stage.get("sections", [])]
            if any(section.get("items") for section in sections):
                limitations = [item for stage in staged["stages"].values() for item in stage.get("limitations", [])]
                result = {identity_field(subject_of(task)): subject_of(task), "updated_at": staged.get("updated_at"), "status": "partial", "revision": None,
                          "summary": "已取得的材料可先阅读，其他来源仍在核对；这不是完整研究成果。", "sections": sections,
                          "limitations": list(dict.fromkeys(limitations + ["本次资料准备尚未完成"]))}
    return {"task": task, "result": with_readable_evidence(result)}


def submit(identity: dict, *, refresh: bool = False, automatic_schedule: bool = False) -> dict:
    task_id = task_id_for(identity)
    dependencies = dependency_manifest(identity)
    with _locked(task_id) as directory:
        previous = _load(directory / "task.json")
        latest = _load(directory / "latest.json")
        if previous:
            saved = _load(directory / "checkpoint.json") or {}
            active = previous["state"] == "queued" or (previous["state"] == "running" and previous.get("lease_until", "") > now())
            changed = {name for name, value in dependencies.items() if value != previous.get("dependencies", {}).get(name)}
            if previous.get("collector_version", (latest or {}).get("collector_version")) != COLLECTOR_VERSION:
                changed.add("external")
            # Reinterpreting a profile or an existing article is not a new web
            # check. Only the external stage can advance this freshness clock.
            checked_at = ((latest or {}).get("external_checked_at")
                          or (saved.get("stages", {}).get("external") or {}).get("checked_at")
                          or (latest or {}).get("updated_at"))
            fresh = (latest and latest.get("collector_version") == COLLECTOR_VERSION
                     and checked_at and datetime.fromisoformat(checked_at) > datetime.now(timezone.utc) - timedelta(minutes=source_refresh_minutes(identity)))
            if active or (fresh and previous["state"] != "paused" and not refresh and not changed):
                return {"task": previous, "result": latest}
            recovery_window = datetime.fromisoformat(previous["updated_at"]) > datetime.now(timezone.utc) - timedelta(minutes=source_refresh_minutes(identity))
            if not refresh and not changed and recovery_window and previous["state"] in {"partial", "failed"} and (previous.get("next_recovery_at") or previous["attempts"] >= 3):
                return {"task": previous, "result": latest}
        task = {
            "id": task_id, identity_field(identity): identity, "state": "queued", "created_at": (previous or {}).get("created_at", now()),
            "updated_at": now(), "generation": (previous or {}).get("generation", 0) + 1,
            "attempts": 0, "progress": [], "lease_until": "", "message": "正在准备比赛资料",
            "dependencies": dependencies, "collector_version": COLLECTOR_VERSION,
        }
        if automatic_schedule:
            task["automatic_schedule"] = True
        if previous and not refresh:
            saved = _load(directory / "checkpoint.json") or {}
            if saved.get("generation") == previous["generation"]:
                invalid = set(changed)
                if not fresh:
                    invalid.add("external")
                invalid = _invalidated_stages(saved.get("stages", {}), invalid)
                stages = {name: stage for name, stage in saved.get("stages", {}).items() if name not in invalid}
                reusable = {}
                if "external" in invalid and "library" not in invalid:
                    failed = _invalidated_stages(saved.get("stages", {}))
                    reusable = {name: stage for name, stage in saved.get("stages", {}).items()
                                if name not in failed and (name == "digest" or (name == "analysis" and "internal" not in invalid and "analysis" not in changed))}
                _save(directory / "checkpoint.json", {"generation": task["generation"], "updated_at": now(), "stages": stages,
                                                       "reusable_stages": reusable, "external_basis": _fingerprint((saved.get("stages", {}).get("external") or {}).get("sections"))})
        _save(directory / "task.json", task)
        return {"task": task, "result": latest}


def read_at(task_id: str, as_of: str) -> dict:
    cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("冻结截止时刻必须包含时区")
    directory = root() / valid_id(task_id)
    candidates = []
    for path in (directory / "snapshots").glob("*.json"):
        row = _load(path)
        try:
            stamp = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            if stamp.tzinfo and stamp <= cutoff:
                candidates.append((stamp, row))
        except (KeyError, ValueError, TypeError):
            continue
    result = max(candidates, key=lambda value: value[0])[1] if candidates else None
    return {"task": {"id": task_id, identity_field(result.get("subject") or result.get("match") or {}): result.get("subject") or result.get("match"), "state": "completed" if result.get("status") == "ok" else "partial"} if result else None, "result": with_readable_evidence(result)}


def update_task(task_id: str, values: dict, *, generation: int | None = None, attempt: int | None = None) -> dict | None:
    with _locked(task_id) as directory:
        task = _load(directory / "task.json")
        if not task or (generation is not None and task["generation"] != generation) or (attempt is not None and task["attempts"] != attempt):
            return None
        task.update(values, updated_at=now())
        _save(directory / "task.json", task)
        return task


def claim(task_id: str) -> dict | None:
    with _locked(task_id) as directory:
        task = _load(directory / "task.json")
        if not task or task["state"] not in {"queued", "running"}:
            return None
        if task["state"] == "running" and task.get("lease_until", "") > now():
            return None
        if task["attempts"] >= 3:
            task.update(state="failed", message="资料准备未能完成，已保留已有成果", updated_at=now())
            _save(directory / "task.json", task)
            return None
        task.update(state="running", attempts=task["attempts"] + 1, updated_at=now(), next_check_at="", lease_until=(datetime.now(timezone.utc) + timedelta(minutes=13)).isoformat(timespec="seconds"))
        _save(directory / "task.json", task)
        return task


def pause_scheduled_task(task: dict, message: str) -> None:
    """Withdraw idle automatic execution, retaining sources and every snapshot."""
    with _locked(task["id"]) as directory:
        current = _load(directory / "task.json")
        if not current or not current.get("automatic_schedule") or current["generation"] != task["generation"] or current["attempts"] != task["attempts"]:
            return
        if current["state"] not in {"queued", "running"}:
            return
        if current["state"] == "running" and current.get("lease_until", "") > now():
            return  # Do not interrupt work owned by another live worker.
        current.update(state="paused", lease_until="", next_recovery_at="", message=message, updated_at=now())
        _save(directory / "task.json", current)


def _invalidated_stages(stages: dict, changed=()) -> set[str]:
    """Generation changes and same-generation recovery share one dependency rule."""
    failed = {name for name, stage in stages.items()
              if stage.get("failed") or ("failed" not in stage and stage.get("limitations") and not stage.get("sections"))}
    invalid = set(changed) | failed
    if invalid & {"external", "library"} or "internal" in failed:
        invalid.update({"digest", "analysis"})
    if invalid & {"internal", "digest"}:
        invalid.add("analysis")
    return invalid


def requeue_failed_stages(task_id: str) -> dict:
    """Resume this generation; refreshing inputs is a separate explicit action."""
    with _locked(task_id) as directory:
        task = _load(directory / "task.json")
        if not task or task["state"] not in {"partial", "failed"} or task["attempts"] >= 3:
            return {"task": task, "result": _load(directory / "latest.json")}
        saved = _load(directory / "checkpoint.json") or {}
        if saved.get("generation") == task["generation"]:
            stages = saved.get("stages", {})
            failed = _invalidated_stages(stages)
            saved["stages"] = {name: stage for name, stage in stages.items() if name not in failed}
            _save(directory / "checkpoint.json", saved)
        task.update(state="queued", lease_until="", next_recovery_at="", updated_at=now(), message="正在补齐未完成内容，已取得内容保留")
        _save(directory / "task.json", task)
        return {"task": task, "result": _load(directory / "latest.json")}


def finish_budget(task: dict) -> None:
    stages = read_checkpoint(task).get("stages", {})
    sections = [section for stage in stages.values() for section in stage.get("sections", [])]
    limitations = [notice for stage in stages.values() for notice in stage.get("limitations", [])]
    result = None
    if _load(root() / valid_id(task["id"]) / "latest.json"):
        finish(task, None, message="本轮准备已到总耗时预算，保留上次可读成果及本轮断点")
        return
    if any(section.get("items") for section in sections):
        result = {identity_field(subject_of(task)): subject_of(task), "updated_at": now(), "as_of": now(),
                  "status": "partial", "summary": "本轮准备已到耗时预算，已取得内容可先阅读。", "sections": sections,
                  "limitations": list(dict.fromkeys(limitations + ["本轮准备已到总耗时预算，保留断点等待有限恢复"])),
                  "delivery": {"ready": False, "budget_exhausted": True}}
    finish(task, result, message="本轮准备已到总耗时预算，保留已有成果")


def finish(task: dict, result: dict | None, *, message: str = "") -> None:
    with _locked(task["id"]) as directory:
        current = _load(directory / "task.json")
        if not _owns_task(current, task):
            return
        saved = _load(directory / "checkpoint.json") or {}
        stages = saved.get("stages", {}) if saved.get("generation") == current["generation"] else {}
        if result:
            result["collector_version"] = COLLECTOR_VERSION
            result["dependencies"] = task.get("dependencies", {})
            result["external_checked_at"] = (stages.get("external") or {}).get("checked_at", "")
            basis = _content_basis({key: result.get(key) for key in ("match", "subject", "sections", "limitations", "summary", "status", "delivery", "conditional_capabilities", "collector_version", "dependencies")})
            revision = hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
            result["revision"] = revision
            snapshot = directory / "snapshots" / f"{revision}.json"
            if not snapshot.exists():
                _save(snapshot, result)
            _save(directory / "latest.json", result)
        readable_message = "资料已准备，可直接阅读" if result and result["status"] == "ok" else "部分资料已整理，可先阅读；仍有内容待补" if result else "本次准备失败，已有资料仍可阅读"
        current.update(state=("completed" if result["status"] == "ok" else "partial") if result else "failed", updated_at=now(), lease_until="", message=message or readable_message)
        expected = {"internal", "external", "digest", "analysis"} if current.get("subject") else {"internal", "library", "external", "digest", "analysis"}
        retryable = (not result or bool(expected - set(stages))
                     or any(stage.get("failed") or ("failed" not in stage and stage.get("limitations") and not stage.get("sections")) for stage in stages.values()))
        delay = {1: 10, 2: 30}.get(current["attempts"])
        current["next_recovery_at"] = (datetime.fromisoformat(current["updated_at"]) + timedelta(minutes=delay)).isoformat(timespec="seconds") if current["state"] in {"partial", "failed"} and retryable and delay else ""
        _save(directory / "task.json", current)


def _owns_task(current: dict | None, worker: dict) -> bool:
    return bool(current and current["generation"] == worker["generation"] and current["attempts"] == worker["attempts"] and current["state"] == "running")


def _content_basis(value):
    if isinstance(value, dict):
        return {key: ("current" if key == "freshness" and item in {"fresh", "cached"} else _content_basis(item))
                for key, item in value.items() if key not in {"captured_at", "updated_at", "as_of"}}
    if isinstance(value, list):
        return [_content_basis(item) for item in value]
    return value


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(_content_basis(value), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:24]


def source_refresh_minutes(identity: dict) -> int:
    """Six-hour ordinary window; last two hours use the existing half-hour cap."""
    try:
        start = kickoff(identity)
        if timedelta(0) <= start - datetime.now(timezone.utc) <= timedelta(hours=2):
            return 30
    except (KeyError, ValueError, TypeError):
        pass
    return 360


def dependency_manifest(identity: dict) -> dict:
    """Public, local reads only. Changes are scoped to the inputs actually used."""
    from xiaoxue_api.modules.team.public import get_current_profile
    from xiaoxue_api.modules.team.public import get_profile_bundle
    from xiaoxue_api.modules.knowledge.version.public import get_global_version_understanding
    from xiaoxue_api.modules.knowledge.tk.public import browse, get_entry, list_match_trading_tk
    from .analysis_repository import METHODS, SKILLS
    from .evidence import PUBLIC_EVIDENCE_VERSION
    from .service import get_current_event

    def safely(operation):
        try:
            return operation()
        except Exception:
            return {"availability": "unreadable"}

    teams = ([identity["team"]] if identity.get("scope") == "team" else [] if identity.get("scope") == "event" else [identity["team_a"], identity["team_b"]])
    config = safely(get_current_event)
    version = safely(get_global_version_understanding)
    version_item = (version.get("data") or {}).get("item") or {}
    internal = {"version": {key: version_item.get(key) for key in ("id", "content", "topic", "content_type")}, "teams": {}}
    library, players, regions = [], [], set()
    for team in teams:
        profile = safely(lambda: get_current_profile(team))
        bundle = safely(lambda: get_profile_bundle(team)) or {}
        roster = bundle.get("players") or []
        players.extend(row.get("name") for row in roster if row.get("name"))
        if (bundle.get("team") or {}).get("region"):
            regions.add(bundle["team"]["region"])
        internal["teams"][team] = {"profile": profile, "roster": roster}
        count = 0
        for offset in range(0, 150, 30):
            page = safely(lambda: browse(period="30d", team=team, offset=offset, limit=30)) or {}
            for record in page.get("results", []):
                if record.get("type") != "knowledge_tk":
                    continue
                entry = safely(lambda: get_entry(record["filename"]))
                library.append({"filename": record["filename"], "content": entry.get("content"), "date": entry.get("date")})
                count += 1
                if count == 3:
                    break
            if count == 3 or not page.get("has_more"):
                break
    if teams:
        internal["trading_tk"] = safely(lambda: list_match_trading_tk(region=next(iter(regions)) if len(regions) == 1 else "", teams=teams, players=players, limit=12))
    if identity_field(identity) == "match":
        from .evidence import prepared_sections
        internal["prepared"] = [
            {**section, "items": [{key: value for key, value in row.items() if key != "prepared_revision"} for row in section.get("items", [])]}
            for section in prepared_sections(identity)
        ]
        from xiaoxue_api.modules.team.public import get_match_context
        from .service import list_score_match_results
        internal["cycle"] = safely(lambda: get_match_context(identity["team_a"], identity["team_b"], event=identity.get("event", "")))
        internal["recent"] = {team: safely(lambda: list_score_match_results(team=team, date_to=identity["match_date"], limit=2)) for team in teams}
    source_config = {key: config.get(key) for key in ("event", "aliases", "team_aliases", "source_hints", "confirmed_teams", "participant_sources")}
    methods = {name: [_fingerprint(safely(lambda: {"text": (SKILLS / path).read_text()})) for path in paths] for name, (_, paths) in METHODS.items()}
    return {"internal": _fingerprint(internal), "library": _fingerprint(library), "external": _fingerprint({"config": source_config, "collector_version": COLLECTOR_VERSION}),
            "analysis": _fingerprint({"methods": methods, "version": version_item, "evidence_contract": PUBLIC_EVIDENCE_VERSION})}


def read_checkpoint(task: dict) -> dict:
    checkpoint = _load(root() / valid_id(task["id"]) / "checkpoint.json") or {}
    return checkpoint if checkpoint.get("generation") == task["generation"] else {}


def checkpoint(task: dict, stages: dict) -> bool:
    with _locked(task["id"]) as directory:
        current = _load(directory / "task.json")
        if not _owns_task(current, task):
            return False
        saved = _load(directory / "checkpoint.json") or {}
        metadata = {key: saved[key] for key in ("reusable_stages", "external_basis") if key in saved} if saved.get("generation") == task["generation"] else {}
        _save(directory / "checkpoint.json", {**metadata, "generation": task["generation"], "updated_at": now(), "stages": stages})
        return True


def reuse_unchanged_derived(task: dict, stages: dict) -> None:
    saved = read_checkpoint(task)
    if "external" not in stages or _fingerprint(stages["external"].get("sections")) != saved.get("external_basis"):
        return
    for name, stage in saved.get("reusable_stages", {}).items():
        if not stage.get("failed") and not (stage.get("limitations") and not stage.get("sections")):
            stages.setdefault(name, stage)
    if saved.get("reusable_stages"):
        checkpoint(task, stages)


def list_saved(date_value: str, limit: int = 30) -> list[dict]:
    if not root().is_dir():
        return []
    matches = []
    for directory in root().iterdir():
        if not re.fullmatch(r"[a-f0-9]{24}", directory.name):
            continue
        data = read(directory.name)
        if (data["task"] or {}).get("match", {}).get("match_date") == date_value:
            matches.append(data)
    matches.sort(key=lambda item: (item["task"]["match"].get("match_time", ""), item["task"]["id"]))
    return matches[:max(1, min(limit, 200))]


def resumable_ids(*, include_leased: bool = False) -> list[str]:
    if not root().is_dir():
        return []
    ids = []
    for directory in root().iterdir():
        if re.fullmatch(r"[a-f0-9]{24}", directory.name):
            task = read(directory.name)["task"]
            recovery_due = task and task["state"] in {"partial", "failed"} and task["attempts"] < 3 and task.get("next_recovery_at") and (include_leased or task["next_recovery_at"] <= now())
            if task and (recovery_due or task["state"] == "queued" or (task["state"] == "running" and (include_leased or task.get("lease_until", "") < now()))):
                ids.append(task["id"])
    return ids


def is_public_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not host or parsed.port not in {None, 80, 443}:
            return False
        if host == "localhost" or "." not in host or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


def _public_dns(url: str) -> bool:
    if not is_public_url(url):
        return False
    try:
        return all(ipaddress.ip_address(item[4][0]).is_global for item in socket.getaddrinfo(urlparse(url).hostname, 443, type=socket.SOCK_STREAM))
    except OSError:
        return False


def parse_search_results(payload) -> list[dict]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            # Exa MCP text format is a discovery list, never a read article.
            rows = []
            for block in re.split(r"(?m)(?=^Title:[ \t]*)", payload):
                title = re.search(r"(?m)^Title:[ \t]*([^\n]+)", block)
                url = re.search(r"(?m)^URL:[ \t]*(https?://\S+)", block)
                published = re.search(r"(?m)^Published(?: Date)?:[ \t]*([^\n]+)", block)
                if not title or not url or not is_public_url(url[1]):
                    continue
                date_value = published[1].strip() if published else ""
                rows.append({"title": title[1].strip(), "url": url[1],
                             "published_at": date_value if re.match(r"\d{4}-\d{2}-\d{2}", date_value) else "",
                             "verification": "search_lead"})
            return rows[:SEARCH_RESULTS_PER_QUERY]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("results") or payload.get("web") or payload.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("web") or rows.get("results") or []
        if not rows and payload.get("content"):
            return parse_search_results("\n".join(item.get("text", "") for item in payload["content"] if isinstance(item, dict)))
    else:
        rows = []
    return [{"title": str(item.get("title") or "来源原文")[:200], "url": item.get("url") or item.get("link") or "",
             "published_at": item.get("publishedDate") or item.get("published_at") or item.get("published_date") or "",
             "snippet": re.sub(r"\s+", " ", str(item.get("snippet") or item.get("description") or item.get("content") or ""))[:400],
             "verification": "search_lead"}
            for item in rows if isinstance(item, dict) and is_public_url(item.get("url") or item.get("link") or "")][:SEARCH_RESULTS_PER_QUERY]


def _search_via_local(query: str) -> str:
    """项目直连本机零 Key 搜索服务（searxng 兼容端）。"""
    return search_web_json(query, limit=SEARCH_RESULTS_PER_QUERY, timeout=remaining_timeout(20))


def _search_via_exa(query: str) -> str:
    """Exa（免费公共端点，易被 429 限流）。"""
    binary = shutil.which("mcporter")
    if not binary:
        raise RuntimeError("mcporter 不可用")
    completed = subprocess.run([binary, "call", "exa.web_search_exa", "--args", json.dumps({
        "query": query, "numResults": SEARCH_RESULTS_PER_QUERY,
        "objective": "Find substantive reporting, player or coach interviews and reasoned match analysis about the specified current League of Legends event and teams. Prioritize original, recent sources with publication dates. Return distinct articles with dates and URLs, not category pages, navigation, betting advertisements or AI-generated summaries."
    }), "--output", "json"], capture_output=True, text=True, timeout=remaining_timeout(22), check=False)
    if completed.returncode or not completed.stdout.strip():
        raise RuntimeError("Exa 未返回")
    return completed.stdout


def compact_query(query: str) -> str:
    """必应中国对长查询会返回无关兜底结果；压成四个以内的核心词再搜。"""
    text = re.sub(r"-site:\S+", " ", query)
    tokens = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9.]{2,}", text) if word.casefold() not in SEARCH_STOPWORDS]
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    event = max(cjk_runs, key=len)[:14] if cjk_runs else ""
    lowered = query.casefold()
    intent = ("复盘" if re.search(r"\breview\b", lowered) or "复盘" in query else
              "赛前分析" if any(word in lowered for word in ("preview", "analysis")) else
              "赔率" if "odds" in lowered or "赔率" in query else
              "采访" if "interview" in lowered or "采访" in query else
              "版本" if "version" in lowered or "版本" in query else "")
    parts = ([event] if event else []) + tokens[:3] + ([intent] if intent else [])
    return " ".join(dict.fromkeys(parts)) or query[:40]


def _search_via_domestic(query: str) -> str:
    """国内直连搜索（必应中国），Exa 与 Hermes 都不可用时兜底。"""
    script = Path("/home/ubuntu/.local/bin/dsearch")
    if not script.is_file():
        raise RuntimeError("dsearch 不可用")
    completed = subprocess.run(["/usr/bin/python3", str(script), compact_query(query), "-n", str(SEARCH_RESULTS_PER_QUERY)],
                               capture_output=True, text=True, timeout=remaining_timeout(20), check=False)
    if completed.returncode or not completed.stdout.strip():
        raise RuntimeError("dsearch 未返回")
    return completed.stdout


def _search_via_bilibili(query: str) -> str:
    """B站搜索：单场赛前分析、锐评、数据复盘的主要中文来源，不需要 key。"""
    keyword = compact_query(query)
    url = "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=" + quote(keyword)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124",
                                                   "Referer": "https://www.bilibili.com"})
    with urllib.request.urlopen(request, timeout=remaining_timeout(15)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = []
    for group in ((payload.get("data") or {}).get("result") or []):
        if group.get("result_type") != "video":
            continue
        for video in (group.get("data") or [])[:SEARCH_RESULTS_PER_QUERY]:
            if not isinstance(video, dict) or not video.get("bvid"):
                continue
            rows.append({"title": re.sub(r"<[^>]+>", "", str(video.get("title") or "")),
                         "url": f"https://www.bilibili.com/video/{video['bvid']}",
                         "snippet": re.sub(r"\s+", " ", str(video.get("description") or ""))[:400],
                         "published_at": datetime.fromtimestamp(video["pubdate"]).isoformat() if video.get("pubdate") else ""})
    if not rows:
        raise RuntimeError("B站无结果")
    return json.dumps({"results": rows}, ensure_ascii=False)


# 实测顺序：本机零 Key 搜索 → Exa → B站 → 必应。
SEARCH_PROVIDERS = (
    ("local/searxng", _search_via_local),
    ("agent-reach/exa", _search_via_exa),
    ("bilibili", _search_via_bilibili),
    ("domestic/bing", _search_via_domestic),
)


def is_video_lead(lead: dict) -> bool:
    host = (urlparse(lead.get("url") or "").hostname or "").lower()
    return any(host == bad or host.endswith("." + bad) for bad in VIDEO_HOSTS)


ENCYCLOPEDIA_HOSTS = ("baike.baidu.com", "zhidao.baidu.com", "jingyan.baidu.com", "wenku.baidu.com",
                     "iciba.com", "3dmgame.com", "gamersky.com", "douban.com", "cctv.com", "zhihu.com")
TRUSTED_HOSTS = ("lolesports.com", "leagueoflegends.com", "liquipedia.net", "lol.fandom.com", "gol.gg",
                 "op.gg", "invenglobal.com", "sheepesports.com", "dotesports.com", "oneesports.gg",
                 "esports.gg", "thespike.gg", "espn.com", "strafe.com", "bilibili.com", "hupu.com",
                 "weibo.com", "scoregg.com", "wanplus.com", "17173.com", "zhibo8.com", "sina.cn",
                 "sina.com.cn", "163.com", "ithome.com", "smzdm.com", "qq.com", "huya.com", "douyu.com")
# 这些站点的正文取不到：只当线索，永远不能顶掉文字来源。
VIDEO_HOSTS = ("bilibili.com", "youtube.com", "youtu.be", "weibo.com", "douyin.com",
               "tiktok.com", "x.com", "twitter.com", "facebook.com", "instagram.com")
SEARCH_STOPWORDS = {"the", "and", "with", "for", "match", "analysis", "review", "preview", "league",
                    "legends", "site", "http", "https", "com", "www"}


def query_tokens(query: str) -> set[str]:
    """关键词集合：英文词 + 中文二元片，用于丢掉搜索引擎的无关兜底结果。"""
    tokens = {word.casefold() for word in re.findall(r"[A-Za-z]{3,}", query) if word.casefold() not in SEARCH_STOPWORDS}
    run = ""
    for char in query + " ":
        if "\u4e00" <= char <= "\u9fff":
            run += char
            continue
        for index in range(len(run) - 1):
            tokens.add(run[index:index + 2])
        run = ""
    return tokens


def relevant_leads(query: str, leads: list[dict], focus: tuple[str, ...] = ()) -> list[dict]:
    """丢弃与查询无关的结果，并按来源可信度排序；不因搜索引擎兜底污染候选。

    focus 是队名/赛事名：陌生站点必须在标题、摘要或域名里出现其中之一，
    否则一律当兜底页丢掉——正文预算比线索数量值钱。
    """
    tokens = query_tokens(query)
    needles = sorted({str(term).casefold().strip() for term in focus if str(term).strip()})
    focus_probe = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(needle) for needle in needles) + r")(?![a-z0-9])") if needles else None
    kept = []
    for lead in leads:
        host = (urlparse(lead.get("url", "")).hostname or "").lower()
        if any(host == bad or host.endswith("." + bad) for bad in ENCYCLOPEDIA_HOSTS):
            continue
        haystack = f"{lead.get('title', '')} {lead.get('snippet', '')} {host}".casefold()
        if tokens and not any(token in haystack for token in tokens):
            continue
        trusted = any(host == good or host.endswith("." + good) for good in TRUSTED_HOSTS)
        if focus_probe is not None and not trusted and not focus_probe.search(haystack):
            continue
        video_host = any(host == bad or host.endswith("." + bad) for bad in VIDEO_HOSTS)
        lead = {**lead, "host_rank": 5 if video_host else (0 if trusted else 1)}
        kept.append(lead)
    kept.sort(key=lambda lead: lead["host_rank"])
    return kept


def search(query: str, focus: tuple[str, ...] = ()) -> tuple[list[dict], str]:
    """按本机搜索 → Hermes → Exa → B站 → 必应取结果，拿到能读正文的线索才收工。

    视频和社媒线索读不到正文，不能顶掉文字来源；所有通道都只剩视频时，
    才把视频线索原样退回，让上游如实记下"只找到视频"。
    单一通道失败不让整轮采集失败，全部失败时才报“普通网页搜索未完成”。
    """
    errors: list[str] = []
    videos: list[dict] = []
    for name, provider in SEARCH_PROVIDERS:
        try:
            raw = provider(query)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{name}: {type(exc).__name__}")
            continue
        try:
            results = parse_search_results(raw)
        except (ValueError, TypeError) as exc:
            errors.append(f"{name}: parse {type(exc).__name__}")
            continue
        results = relevant_leads(query, results, focus)
        readable = [lead for lead in results if not is_video_lead(lead)]
        if readable:
            return readable, ""
        if results:
            if not videos:
                videos = results
            errors.append(f"{name}: 仅视频线索")
            continue
        errors.append(f"{name}: 无相关结果")
    if videos:
        return videos, ""
    return [], "普通网页搜索未完成（" + "；".join(errors) + "）"


PREDICTION_HUNT_SCRIPT = Path("/home/ubuntu/.agents/skills/esports/opinion-sources/scripts/prediction_hunt.py")


def search_predictions(query: str, limit: int = 8) -> dict:
    """搜集「别人怎么预测」：虎扑预测帖 + 虎扑LOL版 + B站预测视频 + 本地搜索前瞻。

    这是他人观点，不是事实；调用方必须带来源与时间引用，不把多条预测平均成共识。
    """
    if not PREDICTION_HUNT_SCRIPT.is_file():
        return {"status": "unavailable", "reason": "预测采集脚本缺失", "query": query}
    completed = subprocess.run(
        ["/usr/bin/python3", str(PREDICTION_HUNT_SCRIPT), query, "--limit", str(max(3, min(limit, 12)))],
        capture_output=True, text=True, timeout=150, check=False,
    )
    if completed.returncode:
        return {"status": "unavailable", "reason": "预测采集未完成", "query": query}
    payload = json.loads(completed.stdout or "{}")
    sections = {
        "hupu_posts": payload.get("hupu_search") or [],
        "hupu_board": payload.get("hupu_board") or [],
        "bilibili": payload.get("bili") or [],
        "web": payload.get("web") or [],
    }
    return {
        "status": "ok" if any(sections.values()) else "empty",
        "query": query,
        "provider": "domestic/prediction_hunt",
        "counts": {k: len(v) for k, v in sections.items()},
        "notice": "他人预测/前瞻，观点非事实；引用需带来源与时间。",
        **sections,
    }


def read_article(url: str) -> str:
    with collection_budget(30):
        return _read_article(url)


_MIRROR_STATE = {"tried": False, "dead": False}
_EXA_STATE = {"tried": False, "dead": False}
_BROWSER_STATE = {"missing": False}


def _read_article(url: str) -> str:
    check_budget()
    if not _public_dns(url):
        raise ValueError("来源地址不可读取")
    # The product's configured extract backend is the primary reader; the external
    # mirror is only a fallback, so an unreachable mirror costs one timeout, not one
    # per article. Do not install another scraper or bypass access controls.
    try:
        return _read_with_extract_backend(url)
    except CollectionBudgetExpired:
        raise
    except (OSError, ValueError, RuntimeError):
        pass
    if not _EXA_STATE["dead"]:
        try:
            return _read_with_exa(url)
        except CollectionBudgetExpired:
            raise
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if shutil.which("mcporter") is None:
                _EXA_STATE["dead"] = True
    if not _MIRROR_STATE["dead"]:
        try:
            return _read_with_mirror(url)
        except CollectionBudgetExpired:
            raise
        except (OSError, ValueError, httpx.HTTPError):
            _MIRROR_STATE["dead"] = True
    try:
        return _read_with_browser(url)
    except CollectionBudgetExpired:
        raise
    except (OSError, ValueError, RuntimeError):
        raise ValueError("来源正文未能取得") from None


def _read_with_browser(url: str) -> str:
    """本地无头浏览器兜底：读 JS 渲染或被前两条通道拒绝的页面。"""
    if _BROWSER_STATE["missing"]:
        raise ValueError("本地浏览器不可用")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001 - 缺依赖时按不可用处理
        _BROWSER_STATE["missing"] = True
        raise ValueError("本地浏览器不可用") from exc
    budget_ms = max(4000, min(15000, int(remaining_timeout(15) * 1000)))
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path="/snap/bin/chromium", args=["--no-sandbox"])
            page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
            try:
                page.goto(url, timeout=budget_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                text = page.inner_text("body")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - 浏览器失败按正文取不到处理
        raise ValueError("来源正文未能取得") from exc
    text = (text or "")[:40000]
    _validate_article_text(text)
    return text


def _read_with_mirror(url: str) -> str:
    with httpx.stream("GET", "https://r.jina.ai/" + url, timeout=remaining_timeout(6), follow_redirects=False, headers={"X-Return-Format": "text"}) as response:
        response.raise_for_status()
        chunks, length = [], 0
        for chunk in response.iter_text():
            check_budget()
            chunks.append(chunk)
            length += len(chunk)
            if length >= 40000:
                break
    text = "".join(chunks)[:40000]
    _validate_article_text(text)
    return text


def _read_with_extract_backend(url: str) -> str:
    """Read the article with the project's guarded public reader."""
    from xiaoxue_api.core.public_reader import extract_public_page

    payload = extract_public_page([url], char_limit=40000, timeout=remaining_timeout(12))
    row = next((item for item in payload.get("results", [])
                if isinstance(item, dict) and not item.get("error")), {})
    text = str(row.get("content") or "")[:40000]
    _validate_article_text(text)
    return text


def _read_with_exa(url: str) -> str:
    binary = shutil.which("mcporter")
    if not binary:
        raise ValueError("已有正文备用工具不可用")
    completed = subprocess.run(
        [binary, "call", "exa.web_fetch_exa", "--args",
         json.dumps({"urls": [url], "maxCharacters": 40000}), "--output", "json"],
        capture_output=True, text=True, timeout=remaining_timeout(16), check=False,
    )
    if completed.returncode:
        raise ValueError("来源正文未能取得")
    payload = json.loads(completed.stdout)
    if payload.get("isError"):
        raise ValueError("来源正文未能取得")
    text = "\n".join(row.get("text", "") for row in payload.get("content", []) if isinstance(row, dict))[:40000]
    _validate_article_text(text)
    return text


def _validate_article_text(text: str) -> None:
    if len(text.strip()) < 120 or re.search(r"(?i)^(error|warning):|captcha|access denied|verify you are human", text[:1000]):
        raise ValueError("来源正文未能取得")


def canonical_source_url(url: str) -> str:
    """Keep resource queries, removing only fragments and known tracking fields."""
    if not is_public_url(url):
        raise ValueError("来源地址不可读取")
    parsed = urlsplit(url)
    query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                       if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}])
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, query, ""))


def read_shared_article(url: str) -> str:
    return read_shared_source(url)["body"]


def read_shared_source(url: str) -> dict:
    """Reuse one verified public body across teams/matches without formal imports."""
    canonical = canonical_source_url(url)
    source_id = hashlib.sha256(canonical.encode()).hexdigest()[:24]
    directory = root() / "sources" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            cached = _load(directory / "body.json") or {}
            try:
                fresh = datetime.fromisoformat(cached["captured_at"]) > datetime.now(timezone.utc) - timedelta(minutes=30)
            except (KeyError, TypeError, ValueError):
                fresh = False
            if fresh and cached.get("url") == canonical and cached.get("body"):
                return {**cached, "freshness": "cached"}
            failed = _load(directory / "read-failure.json") or {}
            if failed.get("retry_after", "") > now():
                if cached.get("body"):
                    return {**cached, "freshness": "revalidation_failed"}
                raise ValueError("来源本轮读取失败，短暂退避后恢复")
            try:
                text = read_article(canonical)
                _validate_article_text(text)
            except (OSError, ValueError, httpx.HTTPError, subprocess.TimeoutExpired):
                _save(directory / "read-failure.json", {"retry_after": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")})
                if cached.get("body"):
                    return {**cached, "freshness": "revalidation_failed"}
                raise
            record = {"url": canonical, "body": text, "captured_at": now(), "content_hash": hashlib.sha256(text.encode()).hexdigest()}
            _save(directory / "body.json", record)
            return {**record, "freshness": "fresh"}
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def collect_external(identity: dict) -> tuple[list[dict], list[str]]:
    from datetime import date
    from zoneinfo import ZoneInfo
    date_value = identity.get("match_date") or identity.get("reference_date") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    is_past = date.fromisoformat(date_value) < datetime.now(ZoneInfo("Asia/Shanghai")).date()
    exclusions = "-site:bilibili.com -site:youtube.com -site:facebook.com -site:instagram.com -site:douyin.com"
    from .service import get_current_event
    config = get_current_event()
    aliases = [str(value).strip() for value in config.get("aliases", []) if str(value).strip()]
    configured = str(identity["event"]).casefold() in {
        str(value).casefold() for value in [config.get("event"), *aliases, *config.get("leagues", [])] if value
    }
    hints = []
    if configured:
        for hint in config.get("source_hints", [])[:8]:
            if not isinstance(hint, dict) or not is_public_url(hint.get("url", "")):
                continue
            if hint.get("scopes") and (identity.get("scope") or "match") not in hint["scopes"]:
                continue
            hinted_teams = hint.get("teams") or []
            actual_teams = {str(identity.get(key) or "").upper() for key in ("team", "team_a", "team_b")} - {""}
            if hinted_teams and actual_teams and not actual_teams.intersection(str(team).upper() for team in hinted_teams):
                continue
            hints.append({"url": hint["url"], "title": str(hint.get("title") or "已配置公开来源"),
                          "published_at": str(hint.get("published_at") or ""),
                          "source_category": hint.get("source_category") if hint.get("source_category") in {"official_background", "author_analysis"} else "unclassified",
                          "weight": "low" if hint.get("weight") == "low" else "normal"})
    teams = [identity["team"]] if identity.get("scope") == "team" else [] if identity.get("scope") == "event" else [identity["team_a"], identity["team_b"]]
    team_aliases = config.get("team_aliases") or {} if configured else {}
    team_terms = [term for team in teams for term in [team, *team_aliases.get(team, [])] if isinstance(term, str) and term.strip()]
    subject = " ".join(teams)
    english_event = next((value for value in aliases if re.search(r"[A-Za-z]{3,}", value)), identity["event"]) if configured else identity["event"]
    english_teams = {team: next((name for name in team_aliases.get(team, []) if re.search(r"[A-Za-z]{3,}", name)), team) for team in teams}
    english_subject = " vs ".join(english_teams.values())
    focus_terms = tuple(term for term in [*team_terms, *english_teams.values()] if len(str(term).strip()) >= 2)
    queries = [
        f"League of Legends {english_event} {english_subject} {'match analysis review' if is_past else 'match preview analysis'} {date_value[:4]} {exclusions}",
        f"{identity['event']} {subject} 赛前 采访 备战 人员变化 {date_value[:7]}",
        *[f"League of Legends {english_event} {english_teams[team]} player coach interview roster preparation {date_value[:7]} {exclusions}" for team in teams],
        f"{identity['event']} {subject} 战术 复盘 近期表现 {date_value[:7]}",
        f"League of Legends {english_event} {english_subject} recent matches form champion pool patch analysis {exclusions}",
    ]
    articles, limitations, seen, bodies = [], [], set(), {}
    incomplete = False
    def source_time_available():
        # Two model stages may each take 100s. Reserve that time plus durable
        # publication, and allow one last bounded 30s source operation.
        try:
            return remaining_timeout(720) >= 250
        except CollectionBudgetExpired:
            return False
    body_reads = 0
    target = TEAM_ARTICLE_TARGET if identity.get("scope") == "team" else MATCH_ARTICLE_TARGET
    # Discovery has its own bounded pass. Background seeds cannot satisfy it,
    # and one query's top unreadable hits cannot hide later usable candidates.
    discovered = []
    for query in queries[:SEARCH_QUERIES_PER_RUN]:
        if not source_time_available():
            incomplete = True
            break
        if not consume_source_budget("search", SEARCH_QUERIES_PER_RUN):
            incomplete = True
            limitations.append("本轮检索预算已用完，保留已取得内容")
            break
        try:
            leads, error = search(query, focus_terms)
        except CollectionBudgetExpired:
            incomplete = True
            break
        discovered.append(leads[:SEARCH_RESULTS_PER_QUERY])
        if error:
            limitations.append(error)
    candidates = [leads[index] for index in range(SEARCH_RESULTS_PER_QUERY) for leads in discovered if index < len(leads)]
    hints_by_url = {canonical_source_url(lead["url"]): lead for lead in hints}
    for lead in [*candidates, *hints]:
        if len(articles) >= target:
            break
        if not source_time_available():
            incomplete = True
            break
        url = canonical_source_url(lead["url"])
        if url in seen:
            continue
        seen.add(url)
        hint = hints_by_url.get(url, {})
        lead = {**hint, **lead, "published_at": lead.get("published_at") or hint.get("published_at", "")}
        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path
        if (re.search(r"/(?:all|category|tag|search|Played_Matches)/?$", path, re.I)
                or (host.endswith("sheepesports.com") and re.search(r"/lol/teams/[^/]+/?$", path, re.I))):
            limitations.append("发现资讯目录，未将目录摘要当作已读报道")
            continue
        if any(host == domain or host.endswith("." + domain) for domain in ("bilibili.com", "youtube.com", "youtu.be", "facebook.com", "instagram.com", "douyin.com", "tiktok.com")):
            if "发现视频或社交线索，但未取得对应正文，不将网页标题当作已读材料" not in limitations:
                limitations.append("发现视频或社交线索，但未取得对应正文，不将网页标题当作已读材料")
            continue
        try:
            if body_reads >= MATCH_READ_ATTEMPTS or not consume_source_budget("body", MATCH_READ_ATTEMPTS):
                incomplete = True
                limitations.append("本轮正文预算已用完，保留已取得内容")
                break
            body_reads += 1
            source_record = read_shared_source(url)
            text = source_record["body"]
            if source_record.get("freshness") == "revalidation_failed":
                limitations.append("部分来源重核暂未完成，保留原取得时间的旧原文，不当作新消息")
            relevant = [line.strip() for line in text.splitlines()
                        if len(line.strip()) >= 40 and "![" not in line
                        and not re.match(r"\s*(#|\||\[.*?\]\(https?://|Title:|URL Source:)", line)]
            cleaned = "\n".join(relevant)
            if team_terms:
                focused = focused_team_text(text, team_terms)
                if focused:
                    cleaned = focused
            excerpt = cleaned[:8000]
            subjects = team_terms or [identity["event"], *(aliases if configured else [])]
            if len(excerpt) < 120 or not any(re.search(rf"(?i)(?<!\w){re.escape(team)}(?!\w)", excerpt) for team in subjects):
                limitations.append("部分网页未取得与双方相关的有效正文，未把标题或导航算作材料")
                continue
            body_hash = hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()
            if body_hash in bodies:
                bodies[body_hash]["source_urls"].append(url)
                continue
            article = {**lead, "url": url, "source_urls": [url], "source_id": hashlib.sha256(url.encode()).hexdigest()[:24], "content_hash": body_hash,
                       "source": host, "captured_at": source_record.get("captured_at"), "freshness": source_record.get("freshness"), "verification": "source_text", "relevance": "team_background", "text_limited": len(cleaned) > 8000,
                       "text": excerpt, "is_excerpt": True, "body": text, "body_limited": len(text) >= 40000}
            if teams:
                article["related_teams"] = [team for team in teams if any(re.search(rf"(?i)(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", excerpt) for term in [team, *team_aliases.get(team, [])])]
            bodies[body_hash] = article
            articles.append(article)
        except CollectionBudgetExpired:
            incomplete = True
            break
        except (OSError, ValueError, httpx.HTTPError):
            limitations.append("部分来源正文暂不可读，已继续核对其他来源")
    if not articles:
        limitations.append("外部正文尚未取得，当前不能视为完整研究成果")
    if any(not item.get("published_at") for item in articles):
        limitations.append("部分原文缺少可核验发布时间，仅作背景材料，不代表最新消息")
    if incomplete:
        limitations.append("本轮先整理已取得原文，其余来源等待自动恢复")
    notices = list(dict.fromkeys(limitations))
    return articles, IncompleteCollection(notices) if incomplete else notices


def focused_team_text(text: str, terms: list[str]) -> str:
    """Retain contiguous team paragraphs even deep inside all-team articles."""
    normalize = lambda value: value.replace("’", "'").replace("‘", "'")
    pattern = re.compile(r"(?i)(?<!\w)(?:" + "|".join(re.escape(normalize(term)) for term in sorted(set(terms), key=len, reverse=True)) + r")(?!\w)")
    headings = list(re.finditer(r"(?m)^#{2,4}\s*\*{0,2}\s*\d+\.\s*[^\n]+", text))
    selected = []
    for index, heading in enumerate(headings):
        if pattern.search(normalize(heading.group())):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            section = text[heading.start():end]
            # Keep article prose, removing embedded recommendations/player cards.
            selected.append("\n".join(line for line in section.splitlines() if "![" not in line and not re.match(r"\s*\*\s+\[|\s*###? \[Recent|\s*You need to be logged|\s*## Comments", line)))
    if selected:
        return "\n\n".join(selected)[:8000]
    ranges = []
    for match in pattern.finditer(normalize(text)):
        start = text.rfind("\n\n", max(0, match.start() - 350), match.start())
        start = start + 2 if start >= 0 else max(0, match.start() - 150)
        end = text.find("\n\n", match.end() + 300, match.end() + 1800)
        end = end if end >= 0 else min(len(text), match.end() + 1600)
        chunk = text[start:end]
        # A logo/navigation/name list alone has no useful team paragraph.
        prose = " ".join(line for line in chunk.splitlines() if len(line.strip()) >= 40 and "![" not in line and not re.match(r"\s*(#|\||\[.*?\]\(https?://)", line))
        if len(prose) < 120 or not pattern.search(normalize(prose)):
            continue
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(end, ranges[-1][1]))
        else:
            ranges.append((start, end))
        if sum(end - start for start, end in ranges) >= 8000:
            break
    return "\n\n".join(text[start:end] for start, end in ranges)[:8000]


def call_digest_model(packet: dict) -> str:
    script = Path(__file__).resolve().parents[4] / "scripts" / "summarize_match_materials.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(packet, ensure_ascii=False), capture_output=True, text=True,
        timeout=remaining_timeout(100), check=False,
    )
    if completed.returncode:
        raise ValueError("中文整理暂不可用")
    return completed.stdout


def official_event_calendar(identity: dict | None = None) -> list[dict]:
    """Read already retained official dates; never search while interpreting."""
    from .service import get_current_event
    config = get_current_event()
    if identity and identity.get("event") and str(identity["event"]).casefold() not in {
        str(value).casefold() for value in [config.get("event"), *config.get("aliases", []), *config.get("leagues", [])] if value
    }:
        return []
    months = r"January|February|March|April|May|June|July|August|September|October|November|December|janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|月"
    calendar = []
    for source in config.get("participant_sources", []):
        url = canonical_source_url(source.get("url", ""))
        host = (urlparse(url).hostname or "").lower()
        if host not in {"lolesports.com", "www.lolesports.com", "leagueoflegends.com", "www.leagueoflegends.com"}:
            continue
        record = _load(root() / "sources" / (hashlib.sha256(url.encode()).hexdigest()[:24]) / "body.json") or {}
        if record.get("url") != url:
            continue
        lines = [line.strip() for line in record.get("body", "").splitlines()
                 if len(line) < 350 and re.search(r"\d", line) and re.search(months, line, re.I)]
        if lines:
            calendar.append({"url": url, "date_lines": "\n".join(lines)[:2400]})
    return calendar[:1]


MARKET_PATTERN = re.compile(r"赔率|盘口|概率|预测市场|胜率|odds|moneyline|market")


def select_digest_items(items: list[dict], limit: int = 8, *, preserve_source_coverage: bool = False) -> list[dict]:
    """按信息类别配额输出：本场变化优先，市场预期最多一条，背景少量，不靠赔率凑数。"""
    updates, market, background = [], [], []
    for item in items:
        text = f"{item.get('text', '')} {item.get('event_key', '')}"
        if item.get("relevance") == "match_update" and not MARKET_PATTERN.search(text):
            updates.append(item)
        elif MARKET_PATTERN.search(text):
            market.append(item)
        else:
            background.append(item)
    updates, market = updates[:5], market[:1]
    background_cap = max(0, limit - len(updates) - len(market)) if preserve_source_coverage else min(2, max(0, limit - len(updates) - len(market)))
    selected = updates + background[:background_cap] + market
    return selected[:limit]


def summarize_materials(identity: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    from .evidence import source_fingerprints, unseen_source_sections
    original = sections
    sections = unseen_source_sections(identity, sections)
    sources = [item for section in sections if section.get("id") in {"news", "library"}
               for item in section.get("items", [])[:MATCH_ARTICLE_TARGET]
               if item.get("verification") in {"source_text", "knowledge_extract"} and item.get("text")]
    if not sources and sections != original:
        return [{"id": "digest", "title": "本场值得知道", "selection_status": "screened", "items": [],
                 "summary": "已复用双方筛选过的相同原文，本次没有新增待筛内容。"}], []
    event_scope = identity.get("scope") == "event"
    if ((not event_scope and sum(len(row["text"][:8000]) for row in sources) <= 6400)
            or (len(sources) <= 2 and all(len(row["text"]) <= 1600 for row in sources))):
        return _summarize_materials_once(identity, sections)
    # Keep each source's complete evidence window. Successful batches survive a
    # later model failure; recovery does not pay to read them again.
    script = Path(__file__).resolve().parents[4] / "scripts" / "summarize_match_materials.py"
    if not script.is_file():
        from . import service
        script = Path(service.__file__).resolve().parents[4] / "scripts" / "summarize_match_materials.py"
    prompt_revision = hashlib.sha256(script.read_bytes()).hexdigest()
    windows = [{**row, "text": row["text"][start:start + 1600],
                "excerpt_start": start, "excerpt_end": min(start + 1600, len(row["text"][:8000]))}
               for row in sources for start in range(0, len(row["text"][:8000]), 1600)]
    if not event_scope:
        # Cover different authors first; a long first article must not occupy
        # every batch before the first readable publication.
        windows.sort(key=lambda row: row["excerpt_start"])
    batches, incomplete = [], False
    for offset in range(0, len(windows), 2):
        check_budget()
        subset = windows[offset:offset + 2]
        cache_key = _fingerprint({"subject": identity, "sources": subset, "calendar": official_event_calendar(identity),
                                  "as_of_date": now()[:10],
                                  "prompt": prompt_revision, "screening": 2})
        path = root() / "screening" / (cache_key + ".json")
        cached = _load(path)
        if cached is not None:
            batch, missing = cached["sections"], []
        elif remaining_timeout(720) < 240:
            # Leave time for interpretation and durable publication. Continue
            # loading later cached batches rather than discarding their work.
            batch, missing = [], ["本轮先交付已筛选内容，其余来源沿断点恢复"]
        else:
            batch, missing = _summarize_materials_once(identity, [{"id": "news", "items": subset}])
            if batch and not missing:
                _save(path, {"sections": batch})
        incomplete = incomplete or bool(missing)
        batches.append(next((section.get("items", []) for section in batch if section.get("id") == "digest"), []))
    if incomplete and not any(batches):
        return [], ["本次信息粗筛未完成，保留原文和已完成断点等待恢复"]
    # Interleave batches so a long official source cannot crowd out every author
    # analysis. Merge the same event/quote across sources without another model.
    items, seen = [], set()
    for index in range(max((len(batch) for batch in batches), default=0)):
        for batch in batches:
            if index >= len(batch):
                continue
            item = batch[index]
            keys = {"event:" + item["event_key"].casefold(),
                    "text:" + re.sub(r"\W+", "", item["text"]).casefold(),
                    "quote:" + re.sub(r"\s+", " ", item["evidence_quote"]).strip().casefold()}
            if keys & seen:
                continue
            seen.update(keys)
            items.append(item)
    # 赛事级筛选每批只收一篇来源，类别配额不能随后把独立来源吞掉。
    # 单场/队伍仍保留市场一条、背景少量，避免赔率或总览灌水。
    items = select_digest_items(items, preserve_source_coverage=event_scope)
    notice = ["部分来源仍在整理，已筛选内容可先阅读"] if incomplete else []
    subject_label = "本届赛事" if event_scope else "本队" if identity.get("scope") == "team" else "本场"
    summary = ("已筛选部分来源，" if incomplete else "已粗筛，") + f"保留 {len(items)} 条与{subject_label}有关的内容。"
    if not items and not incomplete:
        summary = "已粗筛，未发现值得补充的信息，不以旧闻或泛泛表态凑数。"
    return [{"id": "digest", "title": subject_label + "值得知道", "selection_status": "screened",
             "incomplete": incomplete, "summary": summary, "items": items,
             "screened_sources": source_fingerprints(sources) if not incomplete else []}], notice


def _summarize_materials_once(identity: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    from .evidence import source_fingerprints, knowledge_provenance
    prepared_at = datetime.fromisoformat(now())
    sources = {}
    for section in sections:
        if section.get("id") not in {"news", "library"}:
            continue
        for item in section.get("items", [])[:MATCH_ARTICLE_TARGET]:
            if item.get("verification") in {"source_text", "knowledge_extract"} and item.get("text"):
                sources[f"S{len(sources) + 1}"] = item
    if not sources:
        return [], []
    packet = {identity_field(identity): identity, "as_of": now(), "official_event_calendar": official_event_calendar(identity), "sources": [
        {"id": key, "title": row.get("title", ""), "url": row.get("url", ""), "published_at": row.get("published_at", ""),
         "text": row["text"][:8000], "source_kind": row.get("verification"), "source_category": row.get("source_category", "unclassified"),
         "weight": row.get("weight", "normal"), "relevance": row.get("relevance", "team_background")}
        for key, row in sources.items()]}
    try:
        payload = json.loads(call_digest_model(packet))
        selected = payload.get("items")
        if not isinstance(selected, list):
            raise ValueError("粗筛结果格式不完整")
        items, seen = [], set()
        for row in selected[:8]:
            if not isinstance(row, dict):
                continue
            ids, text, quote = row.get("source_ids"), row.get("text"), row.get("evidence_quote")
            reason, relevance, event_key = row.get("why_relevant"), row.get("relevance"), row.get("event_key")
            if (not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str)
                    or ids[0] not in sources or not isinstance(text, str)
                    or not re.search(r"[\u4e00-\u9fff]", text)
                    or not isinstance(reason, str) or not re.search(r"[\u4e00-\u9fff]", reason)
                    or relevance not in {"match_update", "useful_background"}
                    or not isinstance(event_key, str) or not event_key.strip()
                    or not isinstance(quote, str) or len(quote) < 15
                    or quote not in sources[ids[0]]["text"][:8000]):
                continue
            source = sources[ids[0]]
            if relevance == "match_update":
                if source.get("freshness") == "revalidation_failed":
                    continue
                try:
                    raw_date = source.get("published_at", "")
                    published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    local = ZoneInfo("Asia/Shanghai")
                    date_value = identity.get("match_date") or identity["reference_date"]
                    match_day = datetime.fromisoformat(date_value).date()
                    cutoff = prepared_at
                    if identity_field(identity) == "match":
                        time_value = identity.get("match_time") or "00:00"
                        start_value = time_value if time_value.startswith(date_value) else date_value + "T" + time_value
                        start = datetime.fromisoformat(start_value)
                        if start.tzinfo is None:
                            start = start.replace(tzinfo=local)
                        cutoff = min(prepared_at, start)
                    if not 0 <= (match_day - published.date()).days <= 30:
                        continue
                    if len(raw_date) == 10:
                        # A date alone cannot prove a same-day item was pre-match.
                        if published.date() >= cutoff.astimezone(local).date():
                            continue
                    elif published.tzinfo is None or published > cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
            keys = {"event:" + event_key.strip().casefold(), "text:" + re.sub(r"\W+", "", text).casefold(),
                    "quote:" + re.sub(r"\s+", " ", quote).strip().casefold()}
            if keys & seen:
                continue
            seen.update(keys)
            media_roster = source.get("source_category") != "official_background" and bool(re.search(r"首发|名单|五人|阵容(?:为|是|包括|由)", text))
            if media_roster:
                text = "媒体列举（未获官方首发确认）：" + text.replace("首发", "阵容")
            items.append({"text": text[:1200], "url": source.get("url", ""),
                          "source_title": source.get("title", ""), "subject": identity,
                          "roster_status": "media_reported_unconfirmed" if media_roster else "not_applicable",
                          "source": "原文中文整理" + (" · 发布时间待核实，仅作背景" if not source.get("published_at") else ""),
                          "published_at": source.get("published_at", ""), "verification": "ai_summary",
                          "why_relevant": reason.strip()[:500], "relevance": relevance,
                          "event_key": event_key.strip()[:160], "evidence_quote": quote, "source_ids": ids,
                          "source_id": source.get("source_id", ""), "source_kind": source.get("verification"),
                          "content_hash": source.get("content_hash", ""),
                          "kind": row.get("kind") if source.get("source_category") != "official_background" and row.get("kind") in {"author_analysis", "reported_information"} else "reported_information",
                          "source_category": source.get("source_category", "unclassified"), "weight": source.get("weight", "normal"),
                          "related_teams": source.get("related_teams", []),
                          "conditions": str(row.get("conditions") or "")[:600], "counterevidence": str(row.get("counterevidence") or "")[:600],
                          **knowledge_provenance({"source_kind": source.get("verification")})})
        if items or not selected:
            return [{"id": "digest", "title": "本场值得知道", "selection_status": "screened",
                     "summary": f"已粗筛，保留 {len(items)} 条与本场有关的内容。" if items else "已粗筛，未发现值得补充的本场信息，不以旧闻或泛泛表态凑数。",
                     "items": items, "screened_sources": source_fingerprints(list(sources.values()))}], []
    except (OSError, ValueError, TypeError, AttributeError, TimeoutError, subprocess.TimeoutExpired):
        pass
    return [], ["本次信息粗筛未完成，原文保留在依据中，不将未筛材料当作阅读成果"]


def collect_internal(identity: dict) -> tuple[list[dict], list[str]]:
    from xiaoxue_api.modules.team.public import get_match_context
    from xiaoxue_api.modules.team.public import get_profile_bundle
    from xiaoxue_api.modules.knowledge.tk.public import list_match_trading_tk
    from xiaoxue_api.modules.team.public import get_current_profile

    from .evidence import prepared_sections
    from .lolesports_facts import facts
    sections, limitations, player_names, regions = prepared_sections(identity), [], set(), set()
    try:
        fact_sections, fact_limits = facts(identity)
        sections.extend(fact_sections)
        limitations.extend(fact_limits)
    except Exception:
        limitations.append("本场事实：赛程与战绩区块本次未生成")
    try:
        context = get_match_context(identity["team_a"], identity["team_b"], event=identity["event"])
        rows = []
        for side in ("team_a", "team_b"):
            value = context.get(side) or {}
            if value.get("team") and value.get("ts") is not None:
                rows.append({"text": f"{value['team']}：实力评级 {value['ts']}", "source": "已有实力资料", "verification": "internal_record"})
        if rows:
            sections.append({"id": "strength", "title": "双方实力资料", "items": rows})
    except Exception:
        limitations.append("双方实力资料暂不可读")
    for team in (identity["team_a"], identity["team_b"]):
        rows = []
        try:
            bundle = get_profile_bundle(team) or {}
            if bundle.get("team", {}).get("region"):
                regions.add(bundle["team"]["region"])
            players = bundle.get("players") or []
            player_names.update(p.get("name", "") for p in players if p.get("name"))
            if players:
                rows.append({"text": "、".join(f"{p.get('role', '')} {p.get('name', '')}".strip() for p in players), "source": "已登记选手（不代表本场首发确认）", "verification": "internal_record"})
            else:
                limitations.append(f"{team} 尚未取得可用的登记名单，本场首发仍需从公开信息核验")
        except Exception:
            limitations.append(f"{team} 登记名单暂不可读")
        try:
            profile = get_current_profile(team)
            fields = profile.get("profile") or {}
            for key, label in (("positioning", "队伍定位"), ("win_path", "怎么赢"), ("lose_path", "怎么输"), ("key_points", "关键点"), ("bp_tendency", "BP倾向")):
                if fields.get(key):
                    rows.append({"text": f"{label}：{fields[key]}", "source": "已有队伍画像", "updated_at": profile.get("updated_at"), "verification": "internal_record"})
            if not profile.get("found"):
                limitations.append(f"{team} 当前没有可用的五项画像，不用旧笔记或镜像替代")
        except Exception:
            limitations.append(f"{team} 当前画像暂不可读，其他资料继续整理")
        if rows:
            sections.append({"id": f"team_{team}", "title": f"{team} 已有资料", "items": rows})
    try:
        payload = list_match_trading_tk(region=next(iter(regions)) if len(regions) == 1 else "", teams=[identity["team_a"], identity["team_b"]], players=sorted(player_names), limit=12)
        rows = [{"text": str(item.get("statement") or item.get("original") or item.get("content") or item.get("title") or "")[:1500], "source": "已有交易 TK", "verification": str(item.get("status") or "待核对")} for item in payload.get("items", [])]
        if rows:
            sections.append({"id": "knowledge", "title": "相关已有认识", "items": rows})
    except Exception:
        limitations.append("相关已有认识暂不可读")
    return sections, limitations


def collect_library(identity: dict) -> tuple[list[dict], list[str]]:
    from .analysis_repository import collect_library as collect
    return collect(identity)


def collect_scope_internal(identity: dict) -> tuple[list[dict], list[str]]:
    """Read formal content, never promote old content to verified event facts."""
    from xiaoxue_api.modules.team.public import get_current_profile
    from xiaoxue_api.modules.team.public import get_profile_bundle
    from xiaoxue_api.modules.knowledge.version.public import get_global_version_understanding

    sections, limitations = [], []
    try:
        payload = get_global_version_understanding()
        item = (payload.get("data") or {}).get("item") or {}
        if item.get("content"):
            sections.append({"id": "version", "title": "已有版本理解", "items": [{
                "text": item["content"], "source": "已有正式版本理解（本届适用性未核对）", "record_id": item.get("id"),
                "content_hash": hashlib.sha256(item["content"].encode()).hexdigest(), "updated_at": item.get("created_at"),
                "verification": "internal_record", "applicability": "unverified", "recognition": "unknown"}]})
        limitations.append("已有版本理解尚未核对本届实际比赛版本")
    except Exception:
        limitations.append("正式版本理解暂不可读")
    if identity["scope"] == "team":
        team = identity["team"]
        rows = []
        try:
            profile = get_current_profile(team)
            fields = profile.get("profile") or {}
            for key, label in (("positioning", "队伍定位"), ("win_path", "怎么赢"), ("lose_path", "怎么输"), ("key_points", "关键点"), ("bp_tendency", "BP倾向")):
                if fields.get(key):
                    rows.append({"text": f"{label}：{fields[key]}", "source": "已有队伍画像（本届适用性未核对）", "updated_at": profile.get("updated_at"),
                                 "verification": "internal_record", "applicability": "unverified", "recognition": "unknown",
                                 "content_hash": hashlib.sha256(str(fields[key]).encode()).hexdigest()})
            limitations.append(f"{team} 已有画像尚需核对当前人员、版本和时期" if profile.get("found") else f"{team} 当前没有可读正式画像")
        except Exception:
            limitations.append(f"{team} 正式画像暂不可读")
        try:
            bundle = get_profile_bundle(team) or {}
            players = bundle.get("players") or []
            if players:
                rows.append({"text": "、".join(f"{row.get('role', '')} {row.get('name', '')}".strip() for row in players),
                             "source": "已登记选手（不代表本届名单或首发确认）", "verification": "internal_record", "applicability": "unverified"})
        except Exception:
            limitations.append(f"{team} 登记名单暂不可读")
        if rows:
            sections.append({"id": f"team_{team}", "title": f"{team} 已有内容", "items": rows})
    return sections, limitations


def analyze_materials(identity: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    from .analysis_repository import analyze
    return analyze(identity, sections)
