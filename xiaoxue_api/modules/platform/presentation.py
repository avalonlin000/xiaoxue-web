from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from . import service


router = APIRouter(tags=["platform"])


@router.get("/api/health")
def health_check():
    return service.health()


@router.get("/api/links")
def get_links(team: str = Query("")):
    return service.links(team)


@router.get("/")
def serve_index():
    return FileResponse(service.index_path())
