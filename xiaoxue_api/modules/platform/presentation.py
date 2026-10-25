from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from . import service
from xiaoxue_api.core.product_modules import public_module_catalog


from .mutations.presentation import router as mutations_router
from .center.presentation import router as center_router
router = APIRouter(tags=["platform"])


@router.get("/api/health")
def health_check():
    return service.health()


@router.get("/api/modules")
def module_contract():
    return public_module_catalog()


@router.get("/api/links")
def get_links(team: str = Query("")):
    return service.links(team)


@router.post("/api/data-refresh")
def refresh_data():
    result = service.refresh_data()
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/")
def serve_index():
    return FileResponse(service.index_path())

router.include_router(mutations_router)
router.include_router(center_router)
