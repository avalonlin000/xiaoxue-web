"""One resumable collector for current-event consumers, never personal judgments."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Timer
from zoneinfo import ZoneInfo

from . import collection_repository as repository
from .service import get_current_event, normalize_match_identity
from xiaoxue_api.modules.team_data.public import list_schedules


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="match-materials")


def _identity(values: dict) -> dict:
    if str(values.get("match_date") or "today").lower() == "today":
        values = {**values, "match_date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()}
    identity = normalize_match_identity(values)
    if identity["game"] != "lol":
        raise ValueError("当前自动资料来源只适用于 LOL，其他项目暂不套用此模板")
    if any(identity[side].casefold() in {"tbd", "待定", "-", "unknown"} for side in ("team_a", "team_b")):
        raise ValueError("对阵尚未确定，不生成虚构比赛资料")
    if not identity["match_time"]:
        rows = list_schedules({"date_from": identity["match_date"], "date_to": identity["match_date"], "team": identity["team_a"]}, 200)
        pair = {identity["team_a"], identity["team_b"]}
        candidates = [row for row in rows if {str(row.get("team_a") or "").upper(), str(row.get("team_b") or "").upper()} == pair]
        if len(candidates) > 1:
            raise ValueError("同日双方有多场比赛，需要从明确的比赛入口准备资料")
        if not candidates or not candidates[0].get("time"):
            raise ValueError("尚未找到明确开赛时间，不生成无法区分场次的资料")
        row = candidates[0]
        identity = normalize_match_identity({**identity, "match_time": row["time"], "event": identity["event"] or row.get("stage", ""), "match_format": identity["match_format"] or row.get("format", "")})
    return identity


def get_prepared_materials(values: dict, *, as_of: str = "") -> dict:
    task_id = repository.task_id_for(_identity(values))
    return repository.read_at(task_id, as_of) if as_of else repository.read(task_id)


def get_collection_task(task_id: str) -> dict:
    data = repository.read(task_id)
    if not data["task"]:
        raise LookupError("没有找到这项比赛资料任务")
    return data


def prepare_materials(values: dict, *, refresh: bool = False, dispatch: bool = True) -> dict:
    data = repository.submit(_identity(values), refresh=refresh)
    if dispatch and data["task"]["state"] == "queued":
        _executor.submit(run_collection_bounded, data["task"]["id"])
    return data


def resume_collection(task_id: str, *, dispatch: bool = True) -> dict:
    data = get_collection_task(task_id)
    task = data["task"]
    if task["state"] == "completed":
        return data
    if task["state"] == "running" and task.get("lease_until", "") > repository.now():
        return data
    if task["attempts"] >= 3:
        return data
    if task["state"] in {"partial", "failed"}:
        data = repository.requeue_failed_stages(task_id)
        if dispatch and data["task"]["state"] == "queued":
            _executor.submit(run_collection_bounded, task_id)
        return data
    # claim() is the sole queued/expired -> running transition; do not requeue a
    # task using a stale read that might race a finishing worker.
    if dispatch:
        _executor.submit(run_collection_bounded, task_id)
    return get_collection_task(task_id)


def resume_pending_collections() -> int:
    ids = repository.resumable_ids(include_leased=True)
    for task_id in ids:
        task = repository.read(task_id)["task"]
        if task and task["state"] in {"partial", "failed"}:
            _schedule_recovery(task_id)
        elif task and task["state"] == "running" and task.get("lease_until", "") > repository.now():
            delay = max(0.1, (datetime.fromisoformat(task["lease_until"]) - datetime.now(timezone.utc)).total_seconds() + 0.1)
            timer = Timer(delay, lambda identity=task_id: _executor.submit(run_collection_bounded, identity))
            timer.daemon = True
            timer.start()
        else:
            _executor.submit(run_collection_bounded, task_id)
    return len(ids)


def _recover_due(task_id: str) -> None:
    task = repository.read(task_id)["task"]
    if not task or not task.get("next_recovery_at") or task["next_recovery_at"] > repository.now():
        return
    data = repository.requeue_failed_stages(task_id)
    if data["task"] and data["task"]["state"] == "queued":
        _executor.submit(run_collection_bounded, task_id)


def _schedule_recovery(task_id: str) -> None:
    task = repository.read(task_id)["task"]
    if not task or not task.get("next_recovery_at") or task["attempts"] >= 3:
        return
    delay = max(0.1, (datetime.fromisoformat(task["next_recovery_at"]) - datetime.now(timezone.utc)).total_seconds())
    timer = Timer(delay, lambda: _recover_due(task_id))
    timer.daemon = True
    timer.start()


def run_collection(task_id: str) -> None:
    task = repository.claim(task_id)
    if not task:
        return
    with repository.collection_budget(attempt=task["attempts"]):
        _run_claimed_collection(task)


def _call_stage(operation, *args):
    """One immediate retry; later retries reuse the persisted successful stages."""
    total = 2 if repository.collection_attempt() == 1 else 1
    for attempt in range(total):
        repository.check_budget()
        try:
            result = operation(*args)
            if result[0] or not result[1] or isinstance(result[1], repository.PendingInputs) or attempt == total - 1:
                return result
        except repository.CollectionBudgetExpired:
            raise
        except Exception:
            if attempt == total - 1:
                raise


def _stage_result(sections: list, limitations: list) -> dict:
    return {"sections": sections, "limitations": limitations,
            "failed": bool(any(section.get("incomplete") for section in sections)
                           or (not sections and limitations and not isinstance(limitations, repository.PendingInputs)))}


def _worker_command() -> list[str]:
    script = "import sys,json;sys.path.insert(0,sys.argv[1]);from xiaoxue_api.modules.current_event.collection import _run_claimed_collection;from xiaoxue_api.modules.current_event.collection_repository import collection_budget;task=json.load(sys.stdin)\nwith collection_budget(attempt=task['attempts']): _run_claimed_collection(task)"
    return [sys.executable, "-c", script, str(Path(__file__).resolve().parents[3])]


def run_collection_bounded(task_id: str, *, budget_seconds: float = 720, worker_slot_fd: int | None = None) -> None:
    """Background/CLI worker: kill the complete process group at the wall cap."""
    if not 0 < budget_seconds <= 720:
        raise ValueError("资料任务预算必须在0至720秒之间")
    with repository.collection_worker_slot(worker_slot_fd) as slot_fd:
        _run_collection_in_slot(task_id, budget_seconds=budget_seconds, worker_slot_fd=slot_fd)


def _run_collection_in_slot(task_id: str, *, budget_seconds: float, worker_slot_fd: int) -> None:
    task = repository.claim(task_id)
    if not task:
        return
    try:
        process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, text=True, start_new_session=True, pass_fds=(worker_slot_fd,))
        try:
            process.communicate(input=json.dumps(task, ensure_ascii=False), timeout=budget_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)
            repository.finish_budget(task)
            return
        if process.returncode:
            repository.finish(task, None, message="后台资料准备中断，保留原有成果与恢复断点")
    except OSError:
        repository.finish(task, None, message="后台资料任务暂不可启动，保留已有成果")
    finally:
        _schedule_recovery(task_id)


def _run_claimed_collection(task: dict) -> None:
    task_id = task["id"]
    if task.get("subject"):
        _run_scope_collection(task)
        return
    stages = repository.read_checkpoint(task).get("stages", {})
    sections, limitations = [], []
    try:
        if "internal" not in stages:
            repository.check_budget()
            try:
                internal, missing = _call_stage(repository.collect_internal, task["match"])
                stages["internal"] = _stage_result(internal, missing)
            except Exception:
                stages["internal"] = {"sections": [], "limitations": ["已有资料暂不可读，仍尝试外部来源"]}
            if not repository.checkpoint(task, stages):
                return
        repository.update_task(task_id, {"progress": ["已有资料已检查", "正在读取外部来源"]}, generation=task["generation"], attempt=task["attempts"])
        if "library" not in stages:
            repository.check_budget()
            try:
                knowledge, missing = _call_stage(repository.collect_library, task["match"])
                stages["library"] = _stage_result(knowledge, missing)
            except Exception:
                stages["library"] = {"sections": [], "limitations": ["相关已有分析本次未能读回，其他来源继续准备"]}
            if not repository.checkpoint(task, stages):
                return
        if "external" not in stages:
            repository.check_budget()
            try:
                articles, missing = _call_stage(repository.collect_external, task["match"])
                external = [{"id": "news", "title": "赛事相关原文", "items": articles}] if articles else []
                stages["external"] = _stage_result(external, missing)
            except Exception:
                stages["external"] = {"sections": [], "limitations": ["外部资料本次未能完成，已保留其他内容"]}
            if not repository.checkpoint(task, stages):
                return
        repository.reuse_unchanged_derived(task, stages)
        for stage in stages.values():
            sections.extend(stage["sections"])
            limitations.extend(stage["limitations"])
        if "digest" not in stages:
            repository.check_budget()
            repository.update_task(task_id, {"progress": ["原文已取得", "正在整理中文要点"]}, generation=task["generation"], attempt=task["attempts"])
            digest, missing = _call_stage(repository.summarize_materials, task["match"], sections)
            stages["digest"] = _stage_result(digest, missing)
            if not repository.checkpoint(task, stages):
                return
            sections = digest + sections
            limitations.extend(missing)
        if "analysis" not in stages:
            repository.check_budget()
            repository.update_task(task_id, {"progress": ["公开内容已筛选", "正在按现有方法分析本场"]}, generation=task["generation"], attempt=task["attempts"])
            try:
                analysis, missing = _call_stage(repository.analyze_materials, task["match"], sections)
            except Exception:
                analysis, missing = [], ["本场方法分析未完成，其他内容仍可读"]
            stages["analysis"] = _stage_result(analysis, missing)
            if not repository.checkpoint(task, stages):
                return
            sections.extend(analysis)
            limitations.extend(missing)
        order = {"digest": 0, "analysis": 1, "comparison": 2}
        sections.sort(key=lambda section: order.get(section.get("id"), 3))
        result = None
        if any(section.get("items") for section in sections):
            match = task["match"]
            digest = next((section for section in sections if section.get("id") == "digest" and section.get("selection_status") == "screened"), None)
            summary = digest["summary"] if digest else "已有资料可按需查看；本场外部信息尚未完成粗筛。"
            own = next((section for section in sections if section.get("id") == "analysis" and section.get("items")), None)
            author_analysis = bool(digest and any(item.get("kind") == "author_analysis" for item in digest.get("items", [])))
            own_scope = "supported" if own and any(item.get("inference_scope") == "supported" for item in own["items"]) else "conditional" if own else "unavailable"
            ready = bool(author_analysis and own_scope == "supported")
            result = {"match": match, "updated_at": repository.now(), "as_of": repository.now(), "status": "ok" if ready and not limitations else "partial", "summary": f"{match['team_a']} vs {match['team_b']}：{summary}" + ("个人方法分析已备好。" if own else ""), "sections": sections, "limitations": list(dict.fromkeys(limitations)),
                      "delivery": {"public_analysis": "screened" if digest else "unavailable", "public_author_analysis": "available" if author_analysis else "unavailable",
                                   "personal_analysis": "prepared" if own else "unavailable", "personal_analysis_scope": own_scope, "ready": ready},
                      "conditional_capabilities": {"live_bp": "unverified", "market_quotes": "unverified"}}
        repository.finish(task, result)
    except repository.CollectionBudgetExpired:
        repository.finish_budget(task)
    except Exception:
        repository.finish(task, None, message="本次资料准备未完成，已保留原有成果")


def list_prepared_materials(date_value: str = "today", limit: int = 30) -> dict:
    date_value = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat() if date_value == "today" else datetime.fromisoformat(date_value).date().isoformat()
    items = []
    for data in repository.list_saved(date_value, limit):
        task, result = data["task"], data["result"]
        items.append({"task_id": task["id"], "match": task["match"], "state": task["state"], "revision": (result or {}).get("revision"), "updated_at": (result or {}).get("updated_at"), "summary": (result or {}).get("summary", task["message"]), "status": (result or {}).get("status", "empty"), "result_url": f"/api/current-event/collection/{task['id']}"})
    return {"date": date_value, "items": items}


def prepare_date(date_value: str = "today", *, event: str = "", refresh: bool = False, dispatch: bool = True) -> dict:
    """Shared scheduler entry. Does not register or enable any production job."""
    date_value = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat() if date_value == "today" else datetime.fromisoformat(date_value).date().isoformat()
    scope = event.strip() or str(get_current_event().get("event") or "").strip()
    if not scope:
        raise ValueError("尚未配置关注赛事，不自动扩大到全部比赛")
    rows = list_schedules({"date_from": date_value, "date_to": date_value, "event": scope}, 200)
    tasks, skipped = [], []
    for row in rows:
        values = {"team_a": row.get("team_a"), "team_b": row.get("team_b"), "event": row.get("stage") or scope,
                  "match_date": row.get("date") or date_value, "match_time": row.get("time") or "", "match_format": row.get("format") or ""}
        try:
            tasks.append(prepare_materials(values, refresh=refresh, dispatch=dispatch)["task"])
        except ValueError as exc:
            skipped.append({"match": values, "reason": str(exc)})
    return {"date": date_value, "event": scope, "tasks": tasks, "skipped": skipped, "source": "configured_schedule"}


def prepare_upcoming(*, hours: int = 24, now_value: datetime | None = None, refresh: bool = False, dispatch: bool = True) -> dict:
    """Existing scheduler can call this before its 90-minute delivery node."""
    if not 1 <= hours <= 48:
        raise ValueError("提前准备窗口应在1至48小时之间")
    start = now_value or datetime.now(ZoneInfo("Asia/Shanghai"))
    if start.tzinfo is None:
        raise ValueError("准备窗口必须包含时区")
    start = start.astimezone(ZoneInfo("Asia/Shanghai"))
    end = start + timedelta(hours=hours)
    scope = str(get_current_event().get("event") or "").strip()
    if not scope:
        raise ValueError("尚未配置关注赛事，不自动扩大到全部比赛")
    rows = list_schedules({"date_from": start.date().isoformat(), "date_to": end.date().isoformat(), "event": scope}, 200)
    tasks, skipped = [], []
    for row in rows:
        try:
            raw_time = str(row["time"])
            when = datetime.fromisoformat(raw_time if re_match_date_time(raw_time) else f"{row['date']}T{raw_time}")
            when = when.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if when.tzinfo is None else when.astimezone(ZoneInfo("Asia/Shanghai"))
            if not start < when <= end:
                continue
            values = {"team_a": row.get("team_a"), "team_b": row.get("team_b"), "event": row.get("stage") or scope,
                      "match_date": row["date"], "match_time": row["time"], "match_format": row.get("format") or ""}
            tasks.append(prepare_materials(values, refresh=refresh, dispatch=dispatch)["task"])
        except (KeyError, ValueError, TypeError):
            skipped.append({"match": row, "reason": "对阵或时间尚未明确，未生成比赛分析"})
    return {"date": start.date().isoformat(), "event": scope, "window_start": start.isoformat(), "window_end": end.isoformat(), "tasks": tasks, "skipped": skipped, "source": "configured_schedule"}


def re_match_date_time(value: str) -> bool:
    return len(value) > 10 and value[4:5] == "-" and value[7:8] == "-"


def _scope_identity(values: dict) -> dict:
    scope = str(values.get("scope") or "").strip()
    event = str(values.get("event") or get_current_event().get("event") or "").strip()
    team = str(values.get("team") or "").strip().upper()
    if scope not in {"event", "team"} or not event or len(event) > 200:
        raise ValueError("需要明确赛事及赛事/队伍准备范围")
    if scope == "team" and (not team or len(team) > 40 or team.casefold() in {"tbd", "待定", "-", "unknown"}):
        raise ValueError("队伍尚未确定，不生成虚构队伍资料")
    identity = {"scope": scope, "event": event}
    if scope == "team":
        identity["team"] = team
    identity["scope_key"] = "scope:" + json.dumps(identity, ensure_ascii=False, sort_keys=True)
    identity["reference_date"] = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return identity


def get_scope_materials(values: dict, *, as_of: str = "") -> dict:
    task_id = repository.task_id_for(_scope_identity(values))
    return repository.read_at(task_id, as_of) if as_of else repository.read(task_id)


def prepare_scope(values: dict, *, refresh: bool = False, dispatch: bool = True) -> dict:
    data = repository.submit(_scope_identity(values), refresh=refresh)
    if dispatch and data["task"]["state"] == "queued":
        _executor.submit(run_collection_bounded, data["task"]["id"])
    return data


def prepare_scope_batch(*, refresh: bool = False, dispatch: bool = True) -> dict:
    config = get_current_event()
    event = str(config.get("event") or "").strip()
    tasks = [prepare_scope({"scope": "event", "event": event}, refresh=refresh, dispatch=dispatch)["task"]]
    skipped, seen = [], set()
    for raw in config.get("confirmed_teams", config.get("participants", [])):
        team = str(raw.get("team") or raw.get("code") or "") if isinstance(raw, dict) else str(raw)
        team = team.strip().upper()
        if team in seen:
            continue
        seen.add(team)
        try:
            tasks.append(prepare_scope({"scope": "team", "event": event, "team": team}, refresh=refresh, dispatch=dispatch)["task"])
        except ValueError as exc:
            skipped.append({"team": team, "reason": str(exc)})
    return {"event": event, "tasks": tasks, "skipped": skipped, "participants_verified": bool(config.get("participants_verified")), "coverage": get_scope_coverage()}


def get_scope_coverage(*, event: str = "") -> dict:
    """Read existing artifacts; roster/global background is not team coverage."""
    config = get_current_event()
    event = event.strip() or str(config.get("event") or "").strip()
    teams = []
    for raw in config.get("confirmed_teams", config.get("participants", [])):
        team = str(raw.get("team") or raw.get("code") or "") if isinstance(raw, dict) else str(raw)
        team = team.strip().upper()
        if team and team not in teams and team.casefold() not in {"tbd", "待定", "-", "unknown"}:
            teams.append(team)
    items = []
    for team in [None, *teams]:
        values = {"scope": "team" if team else "event", "event": event, **({"team": team} if team else {})}
        data = get_scope_materials(values)
        result, task = data.get("result") or {}, data.get("task") or {}
        digest = [item for section in result.get("sections", []) if section.get("id") == "digest" and section.get("selection_status") == "screened" for item in section.get("items", []) if item.get("text") and item.get("evidence_quote")]
        profile = [item for section in result.get("sections", []) if team and section.get("id") == f"team_{team}" for item in section.get("items", [])
                   if item.get("text") and (item.get("content_hash") or item.get("record_id")) and "登记选手" not in item.get("source", "")
                   and item.get("applicability") == "verified" and item.get("applicable_event") == event and item.get("applicability_evidence")]
        current_digest = []
        for item in digest:
            try:
                age = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - datetime.fromisoformat(str(item.get("published_at") or "")[:10]).date()).days
                recent = 0 <= age <= 90
            except ValueError:
                recent = False
            if not team or (team in item.get("related_teams", []) and recent):
                current_digest.append(item)
        authors = [item for item in digest if item.get("kind") == "author_analysis"]
        readable = bool(current_digest or profile)
        items.append({**values, "state": task.get("state", "not_prepared"), "revision": result.get("revision"),
                      "updated_at": result.get("updated_at"), "readable": readable,
                      "content_state": "available" if readable else "pending", "author_analysis_count": len(authors),
                      "team_content_count": len(current_digest) + len(profile) if team else 0,
                      "background_count": len(digest) - len(current_digest), "task_id": task.get("id")})
    readable_count = sum(item["readable"] for item in items[1:])
    return {"event": event, "participants_verified": bool(config.get("participants_verified")), "teams_total": len(teams),
            "teams_readable": readable_count, "all_teams_readable": bool(teams) and readable_count == len(teams), "items": items}


def _run_scope_collection(task: dict) -> None:
    """The same store/stages for preparation that does not require a matchup."""
    identity = task["subject"]
    stages = repository.read_checkpoint(task).get("stages", {})
    try:
        for name, collector in (("internal", repository.collect_scope_internal), ("external", repository.collect_external)):
            if name in stages:
                continue
            repository.check_budget()
            try:
                rows, limitations = _call_stage(collector, identity)
                sections = ([{"id": "news", "title": "相关原文", "items": rows}] if rows else []) if name == "external" else rows
            except Exception:
                sections, limitations = [], ["部分预备内容暂不可读，其他内容继续准备"]
            stages[name] = _stage_result(sections, limitations)
            if not repository.checkpoint(task, stages):
                return
        repository.reuse_unchanged_derived(task, stages)
        sections = [section for stage in stages.values() for section in stage["sections"]]
        if "digest" not in stages:
            repository.check_budget()
            digest, missing = _call_stage(repository.summarize_materials, identity, sections)
            stages["digest"] = _stage_result(digest, missing)
            if not repository.checkpoint(task, stages):
                return
            sections = digest + sections
        if "analysis" not in stages:
            repository.check_budget()
            from .analysis_repository import analyze_scope
            analysis, missing = _call_stage(analyze_scope, identity, sections)
            stages["analysis"] = _stage_result(analysis, missing)
            if not repository.checkpoint(task, stages):
                return
            sections.extend(analysis)
        limitations = [item for stage in stages.values() for item in stage["limitations"]]
        result = None
        if any(section.get("items") for section in sections):
            digest = next((section for section in sections if section.get("id") == "digest" and section.get("selection_status") == "screened"), None)
            authors = bool(digest and any(item.get("kind") == "author_analysis" for item in digest.get("items", [])))
            own = next((section for section in sections if section.get("id") == "analysis" and section.get("items")), None)
            label = identity.get("team") or identity["event"]
            result = {"subject": identity, "updated_at": repository.now(), "as_of": repository.now(), "status": "partial",
                      "summary": f"{label}：" + (digest.get("summary", "已有可读预备内容") if digest else "已有内容可读，公开分析仍在准备"),
                      "sections": sections, "limitations": list(dict.fromkeys(limitations)),
                      "delivery": {"public_analysis": "screened" if digest else "unavailable", "public_author_analysis": "available" if authors else "unavailable", "ready": False,
                                   "personal_analysis": "prepared" if own else "unavailable", "personal_analysis_scope": "conditional" if own else "unavailable"}}
        repository.finish(task, result)
    except repository.CollectionBudgetExpired:
        repository.finish_budget(task)
    except Exception:
        repository.finish(task, None, message="本次预备内容未完成，保留原有成果")
