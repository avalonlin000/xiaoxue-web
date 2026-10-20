from fastapi import APIRouter, HTTPException, Query

from . import service


router = APIRouter(tags=["fundamentals"])


@router.get("/api/fundamentals/teams")
def fundamentals_teams(scope: str = Query("all"), limit: int = Query(80), team: str = Query("")):
    return service.list_teams(scope, limit, team)


@router.get("/api/fundamentals/msi")
def fundamentals_msi():
    return service.get_msi()


@router.get("/api/fundamentals/msi-match-context")
def fundamentals_msi_match_context(team_a: str = Query(...), team_b: str = Query(...)):
    try:
        return service.get_match_context(team_a, team_b, event="MSI")
    except service.TeamsNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/fundamentals/match-context")
def fundamentals_match_context(
    team_a: str = Query(...), team_b: str = Query(...), event: str = Query(""),
):
    try:
        return service.get_match_context(team_a, team_b, event=event)
    except service.TeamsNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/ts-updates/{team}")
def ts_updates(
    team: str,
    limit: int = Query(20, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
):
    return service.get_ts_updates(team, limit, days)
