from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from . import collection

from xiaoxue_api.modules.match.event.service import (
    get_current_event,
    get_trading_methods,
    get_judgment_context,
    discuss_judgment,
    get_current_event_dashboard,
    get_match_desk,
    get_match_run,
    get_match_run_review,
    get_match_workspace,
    get_score_match_evidence,
    get_gol_series_evidence,
    get_score_match_result,
    list_score_match_results,
    advance_match_run,
    save_virtual_judgment,
    start_match_run,
    unlock_match_run_result,
    update_match_run_fact,
    record_match_change,
    save_match_workspace,
    get_active_match_run,
    list_recent_match_runs,
    focus_match_run,
    pause_match_run,
    save_match_trade_entry,
    save_trade_plan_manual,
    create_trade_plan_item,
    update_trade_plan_item,
    delete_trade_plan_item,
    restore_trade_plan_item,
    reorder_trade_plan_item,
    get_trade_plan_review,
)


router = APIRouter(prefix="/api", tags=["current-event"])


@router.get("/predictions")
def search_predictions_api(q: str = Query(..., min_length=2, max_length=60),
                           limit: int = Query(8, ge=3, le=12)) -> dict:
    """只读：赛前预测搜集（虎扑/B站/Tavily），供 Agent 与前端查询他人观点。"""
    from .collection_repository import search_predictions
    try:
        return search_predictions(q.strip(), limit)
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"预测采集暂不可用: {type(exc).__name__}") from None
router.add_event_handler("startup", collection.resume_pending_collections)


class MatchIdentityIn(BaseModel):
    game: str = "lol"
    team_a: str
    team_b: str
    event: str = ""
    match_date: str = "today"
    match_time: str = ""
    match_format: str = ""


class MatchWorkspaceIn(MatchIdentityIn):
    direction: str
    reasons: str
    handling: str
    change_conditions: str


class MatchCollectionIn(MatchIdentityIn):
    refresh: bool = False


@router.post("/current-event/collection")
def prepare_current_event_materials(data: MatchCollectionIn) -> dict:
    try:
        return collection.prepare_materials(data.model_dump(), refresh=data.refresh)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/collection")
def current_event_materials(
    team_a: str, team_b: str, event: str = "", match_date: str = "today",
    match_time: str = "", match_format: str = "", game: str = "lol", as_of: str = "",
) -> dict:
    try:
        return collection.get_prepared_materials(dict(team_a=team_a, team_b=team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format, game=game), as_of=as_of)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/collection/{task_id}")
def current_event_collection_task(task_id: str) -> dict:
    try:
        return collection.get_collection_task(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/collection/{task_id}/resume")
def resume_current_event_collection(task_id: str) -> dict:
    try:
        return collection.resume_collection(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/materials")
def prepared_current_event_matches(date: str = "today", limit: int = Query(30, ge=1, le=200)) -> dict:
    try:
        return collection.list_prepared_materials(date, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class MatchChangeIn(MatchIdentityIn):
    source: str
    impact: str
    detail: str


class MatchRunStartIn(MatchIdentityIn):
    mode: str = "live"
    focus: str = ""


class MatchRunFocusIn(MatchIdentityIn):
    focus: str


class MatchRunFactUpdateIn(MatchIdentityIn):
    fact_id: int
    status: str
    value: str
    reason: str


class MatchRunAdvanceIn(MatchIdentityIn):
    phase: str


class MatchRunJudgmentIn(MatchIdentityIn):
    direction: str
    reasons: str
    handling: str
    change_conditions: str


class MatchTradeEntryIn(MatchIdentityIn):
    section: str
    content: str
    confirmed_by_user: bool = False


class MatchTradePlanManualIn(MatchIdentityIn):
    content: str


class TradePlanItemIn(MatchIdentityIn):
    market: str
    direction: str
    team: str = ""
    statement: str = ""


class TradePlanReorderIn(MatchIdentityIn):
    item_id: str
    movement: str


class KnowledgeCandidateIn(MatchIdentityIn):
    target_type: str
    target_name: str = ""
    topic: str
    observation: str
    reason: str


class KnowledgeCandidateStatusIn(BaseModel):
    status: str


@router.get("/current-event")
def current_event() -> dict:
    return get_current_event()


@router.get("/trading-methods")
def trading_methods() -> dict:
    return get_trading_methods()


class JudgmentContextIn(BaseModel):
    method_id: str = Field(min_length=1, max_length=64)
    event: str = Field(default="", max_length=120)
    team: str = Field(default="", max_length=40)
    team_a: str = Field(default="", max_length=40)
    team_b: str = Field(default="", max_length=40)
    match_date: str = "today"
    match_time: str = ""
    match_format: str = ""
    as_of: str = ""


class JudgmentDiscussionIn(JudgmentContextIn):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=8)


@router.get("/current-event/judgment-context")
def current_event_judgment_context(
    method_id: str, event: str = "", team: str = "", team_a: str = "", team_b: str = "",
    match_date: str = "today", match_time: str = "", match_format: str = "", as_of: str = "",
) -> dict:
    try:
        return get_judgment_context(**JudgmentContextIn(**locals()).model_dump())
    except ValueError as exc:
        raise HTTPException(400, "判断对象或入口不正确，请重新选择。") from exc


@router.post("/current-event/judgment-discussion")
def current_event_judgment_discussion(data: JudgmentDiscussionIn) -> dict:
    try:
        return discuss_judgment(**data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


class ScopeCollectionIn(BaseModel):
    scope: str
    event: str = ""
    team: str = ""
    refresh: bool = False


@router.get("/current-event/scope-materials")
def current_event_scope_materials(scope: str = "event", event: str = "", team: str = "", as_of: str = "") -> dict:
    try:
        return collection.get_scope_materials({"scope": scope, "event": event, "team": team}, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/scope-materials")
def prepare_current_event_scope_materials(data: ScopeCollectionIn) -> dict:
    try:
        return collection.prepare_scope(data.model_dump(), refresh=data.refresh)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/scope-coverage")
def current_event_scope_coverage() -> dict:
    return collection.get_scope_coverage()


@router.get("/current-event/dashboard")
def current_event_dashboard(date: str = Query("today"), limit: int = Query(12)) -> dict:
    try:
        dashboard = get_current_event_dashboard(date, limit)
        if date == "upcoming":
            dashboard["preparation"] = collection.summarize_window_materials(dashboard["matches"])
            dashboard["preparation"]["truncated"] = dashboard["truncated"]
        return dashboard
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/preparation-coverage")
def current_event_preparation_coverage(offset: int = Query(0, ge=0, le=200), limit: int = Query(4, ge=1, le=100)) -> dict:
    """Small read-only page for the existing product tool; counts cover the whole window."""
    dashboard = get_current_event_dashboard("upcoming", 200)
    coverage = collection.summarize_window_materials(dashboard["matches"])
    items = coverage.pop("items")
    return {**coverage, "event": dashboard["context"].get("event"),
            "window_start": dashboard["date"], "window_end": dashboard["date_to"],
            "truncated": dashboard["truncated"], "items": items[offset:offset + limit],
            "next_offset": offset + limit if offset + limit < len(items) else None}


@router.get("/current-event/match-desk")
def current_event_match_desk(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    try:
        return get_match_desk(team_a, team_b, event, match_date, match_time, match_format, game)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/gol-series-evidence")
def current_event_gol_series_evidence(
    team_a: str = Query(...), team_b: str = Query(...), game_id: int = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""), game: str = Query("lol"),
) -> dict:
    try:
        return get_gol_series_evidence({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        }, game_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/current-event/match-workspace")
def current_event_match_workspace(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    try:
        return get_match_workspace({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/current-event/match-workspace")
def save_current_event_match_workspace(data: MatchWorkspaceIn) -> dict:
    try:
        return save_match_workspace(data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/match-run")
def current_event_match_run(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    try:
        return get_match_run({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/match-run/active")
def active_current_event_match_run() -> dict:
    return get_active_match_run()


@router.get("/current-event/match-runs")
def recent_current_event_match_runs(limit: int = Query(12)) -> dict:
    try:
        return list_recent_match_runs(limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-run/start")
def start_current_event_match_run(data: MatchRunStartIn) -> dict:
    try:
        return start_match_run(data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-run/focus")
def focus_current_event_match_run(data: MatchRunFocusIn) -> dict:
    try:
        return focus_match_run(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-run/pause")
def pause_current_event_match_run(data: MatchIdentityIn) -> dict:
    try:
        return pause_match_run(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/current-event/match-run/entry")
def save_current_event_match_trade_entry(data: MatchTradeEntryIn) -> dict:
    try:
        return save_match_trade_entry(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/current-event/match-run/facts/{fact_id}")
def update_current_event_match_run_fact(fact_id: int, data: MatchRunFactUpdateIn) -> dict:
    try:
        return update_match_run_fact({**data.model_dump(), "fact_id": fact_id})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-run/advance")
def advance_current_event_match_run(data: MatchRunAdvanceIn) -> dict:
    try:
        return advance_match_run(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/current-event/match-run/judgment")
def save_current_event_match_run_judgment(data: MatchRunJudgmentIn) -> dict:
    try:
        return save_virtual_judgment(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-run/unlock-result")
def unlock_current_event_match_run_result(data: MatchIdentityIn) -> dict:
    try:
        return unlock_match_run_result(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/score-evidence")
def current_event_score_evidence(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"), view: str = Query("pre"),
) -> dict:
    try:
        return get_score_match_evidence({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game, "view": view,
        })
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/scoregg/result")
def scoregg_result(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    """Public read-only ScoreGG result lookup; it never requires a trade run."""
    try:
        return get_score_match_result({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/scoregg/results")
def scoregg_results(
    team: str = Query(""), date_from: str = Query(""), date_to: str = Query(""), limit: int = Query(20),
) -> dict:
    """List completed imported results by optional team and date window."""
    try:
        return list_score_match_results(team=team, date_from=date_from, date_to=date_to, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/match-run/review")
def current_event_match_run_review(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    try:
        return get_match_run_review({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/trade-plan/manual")
def save_current_event_trade_plan_manual(data: MatchTradePlanManualIn) -> dict:
    try:
        return save_trade_plan_manual(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/trade-plan/items")
def create_current_event_trade_plan_item(data: TradePlanItemIn) -> dict:
    try:
        return create_trade_plan_item(data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/current-event/trade-plan/items/{item_id}")
def update_current_event_trade_plan_item(item_id: str, data: TradePlanItemIn) -> dict:
    try:
        return update_trade_plan_item({**data.model_dump(), "item_id": item_id})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/current-event/trade-plan/items/{item_id}")
def delete_current_event_trade_plan_item(item_id: str, data: MatchIdentityIn) -> dict:
    try:
        return delete_trade_plan_item({**data.model_dump(), "item_id": item_id})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/trade-plan/items/{item_id}/restore")
def restore_current_event_trade_plan_item(item_id: str, data: MatchIdentityIn) -> dict:
    try:
        return restore_trade_plan_item({**data.model_dump(), "item_id": item_id})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/trade-plan/items/reorder")
def reorder_current_event_trade_plan_item(data: TradePlanReorderIn) -> dict:
    try:
        return reorder_trade_plan_item(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/current-event/trade-plan/review")
def current_event_trade_plan_review(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
    match_date: str = Query("today"), match_time: str = Query(""), match_format: str = Query(""),
    game: str = Query("lol"),
) -> dict:
    try:
        return get_trade_plan_review({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/current-event/match-workspace/changes")
def save_current_event_match_change(data: MatchChangeIn) -> dict:
    try:
        return record_match_change(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
