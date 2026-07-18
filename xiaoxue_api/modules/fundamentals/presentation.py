from fastapi import APIRouter, HTTPException, Query

from . import service


router = APIRouter(prefix="/api/fundamentals", tags=["fundamentals"])


@router.get("/teams")
def fundamentals_teams(scope: str = Query("all"), limit: int = Query(80)):
    return service.list_teams(scope, limit)


@router.get("/msi")
def fundamentals_msi():
    return service.get_msi()


@router.get("/msi-match-context")
def fundamentals_msi_match_context(team_a: str = Query(...), team_b: str = Query(...)):
    try:
        return service.get_match_context(team_a, team_b)
    except service.TeamsNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
