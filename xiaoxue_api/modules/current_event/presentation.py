from fastapi import APIRouter

from xiaoxue_api.modules.current_event.service import get_current_event


router = APIRouter(prefix="/api", tags=["current-event"])


@router.get("/current-event")
def current_event() -> dict:
    return get_current_event()
