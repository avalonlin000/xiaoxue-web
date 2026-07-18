from fastapi import APIRouter, HTTPException, Query

from .models import Team3DUpdate
from . import service


router = APIRouter(prefix="/api", tags=["team-data"])


@router.get("/teams")
def list_teams():
    return service.list_teams()


@router.get("/schedules")
def list_schedules(
    event: str = Query(None), region: str = Query(None), team: str = Query(None),
    date_from: str = Query(None), date_to: str = Query(None), limit: int = Query(50),
    upcoming: bool = Query(False),
):
    return service.list_schedules(locals(), limit)


@router.get("/players")
def list_players(team: str = Query(...)):
    try:
        return service.list_players(team)
    except service.TeamNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/team-3d/{team}")
def get_team_3d(team: str):
    try:
        return service.get_team_3d(team)
    except service.TeamNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/team-3d/{team}")
def update_team_3d(team: str, data: Team3DUpdate):
    try:
        return service.update_team_3d(team, data.model_dump())
    except service.TeamNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
