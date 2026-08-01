from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from xiaoxue_api.modules.current_event.service import (
    get_current_event,
    get_current_event_dashboard,
    get_match_desk,
    get_match_run,
    get_match_run_review,
    get_match_workspace,
    get_score_match_evidence,
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
    create_knowledge_candidate,
    list_knowledge_candidates,
    update_knowledge_candidate_status,
)


router = APIRouter(prefix="/api", tags=["current-event"])


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


@router.get("/current-event/dashboard")
def current_event_dashboard(date: str = Query("today"), limit: int = Query(12)) -> dict:
    try:
        return get_current_event_dashboard(date, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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


@router.post("/current-event/match-run/candidates")
def create_current_event_knowledge_candidate(data: KnowledgeCandidateIn) -> dict:
    try:
        return create_knowledge_candidate(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/stage-review/candidates")
def stage_review_candidates(status: str = Query("pending"), limit: int = Query(100)) -> dict:
    try:
        return list_knowledge_candidates(status, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/stage-review/candidates/{candidate_id}")
def update_stage_review_candidate(candidate_id: int, data: KnowledgeCandidateStatusIn) -> dict:
    try:
        return update_knowledge_candidate_status(candidate_id, data.status)
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


@router.post("/current-event/match-workspace/changes")
def save_current_event_match_change(data: MatchChangeIn) -> dict:
    try:
        return record_match_change(data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
