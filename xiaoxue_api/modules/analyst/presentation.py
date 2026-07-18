from fastapi import APIRouter, Query

from .service import analyze


router = APIRouter(prefix="/api", tags=["analyst"])


@router.get("/analyst/{team}")
async def get_analyst(team: str, analyst: str = Query("")):
    return await analyze(team, analyst)
