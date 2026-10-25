from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import service

router = APIRouter(prefix="/api/gol", tags=["gol-gg"])


class GolQueryIn(BaseModel):
    kind: str
    tournament: str = ""
    game_id: int | None = None


def _call(action):
    try:
        return action()
    except service.GolInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    except service.GolUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/series")
def get_series(game_id: int = Query(...)) -> dict:
    return _call(lambda: service.series_facts(game_id))


@router.get("/tournament")
def get_tournament(tournament: str = Query(...)) -> dict:
    return _call(lambda: service.tournament_facts(tournament))


@router.get("/entities")
def get_entities(tournament: str = Query(...), kind: str = Query("all"), query: str = Query(""), limit: int = Query(20)) -> dict:
    return _call(lambda: service.tournament_entities(tournament, kind=kind, query_text=query, limit=limit))


@router.get("/team")
def get_team(team_id: int = Query(...), tournament: str = Query(...)) -> dict:
    return _call(lambda: service.team_tournament_facts(team_id, tournament))


@router.get("/player")
def get_player(player_id: int = Query(...), tournament: str = Query(...)) -> dict:
    return _call(lambda: service.player_tournament_facts(player_id, tournament))


@router.post("/query")
def query_gol(data: GolQueryIn) -> dict:
    return _call(lambda: service.query(data.kind, tournament=data.tournament, game_id=data.game_id))
