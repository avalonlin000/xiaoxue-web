from fastapi import APIRouter, Query

from .service import get_champion_context

router = APIRouter(prefix='/api/champions', tags=['champions'])


@router.get('/context')
def champion_context(champion: str = Query(...), version: str = Query('')) -> dict:
    return get_champion_context(champion, version)
