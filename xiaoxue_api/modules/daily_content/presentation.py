from fastapi import APIRouter, HTTPException, Query

from . import service


router = APIRouter(prefix="/api", tags=["daily-content"])


@router.get("/daily-content")
def get_daily_content(date: str = Query("today")):
    try:
        return service.get_daily_content(date)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except service.ConfigurationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
