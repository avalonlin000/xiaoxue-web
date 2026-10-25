from fastapi import APIRouter, HTTPException, Query

from .service import get_match, list_matches


router = APIRouter(prefix="/api/football", tags=["football"])


@router.get("/matches")
def football_matches(
    view: str = Query("candidates", pattern="^(candidates|all)$"),
    play: str = Query("all", pattern="^(all|half_break|late_over)$"),
    keyword: str = Query("", max_length=100),
) -> dict:
    return list_matches(view=view, play=play, keyword=keyword)


@router.get("/matches/{match_id:path}")
def football_match(match_id: str) -> dict:
    try:
        return {"match": get_match(match_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"比赛资料暂时无法读取：{exc}") from exc
