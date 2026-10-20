from __future__ import annotations

from fastapi import APIRouter

from . import service


router = APIRouter(prefix="/api/version-understanding", tags=["version-understanding"])


@router.get("/global/current")
def get_global_current_version_understanding() -> dict:
    """Keep the global object distinct from the legacy /{team} compatibility route."""

    return service.get_global_version_understanding()
