from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import service
from .models import BasketCreateIn, BasketPatchIn, DeliveryCreateIn, DeliveryPatchIn, RequestCreateIn, RequestPatchIn


router = APIRouter(prefix="/api/project-center", tags=["project-center"])


def _call(callback):
    try:
        return callback()
    except service.ProjectCenterError as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": str(exc)}) from exc


@router.get("/overview")
def get_overview() -> dict:
    return _call(service.overview)


@router.get("/modules")
def get_modules() -> dict:
    return _call(service.list_modules)


@router.get("/modules/{module_id}")
def get_module(module_id: str) -> dict:
    return _call(lambda: service.get_module(module_id))


@router.get("/manual")
def get_manual() -> dict:
    return _call(service.get_manual)


@router.get("/change-basket")
def get_change_basket(status: str = Query("active"), limit: int = Query(50, ge=1, le=100)) -> dict:
    return _call(lambda: service.list_basket(status, limit))


@router.post("/change-basket")
def add_change_basket(data: BasketCreateIn) -> dict:
    return _call(lambda: service.create_basket_item(data.model_dump()))


@router.patch("/change-basket/{item_id}")
def patch_change_basket(item_id: str, data: BasketPatchIn) -> dict:
    return _call(lambda: service.update_basket_item(item_id, data.model_dump(exclude_none=True)))


@router.get("/requests")
def get_requests(status: str = Query("active"), limit: int = Query(50, ge=1, le=100)) -> dict:
    return _call(lambda: service.list_requests(status, limit))


@router.post("/requests")
def add_request(data: RequestCreateIn) -> dict:
    return _call(lambda: service.create_request(data.model_dump()))


@router.get("/requests/{request_id}")
def get_request(request_id: str) -> dict:
    return _call(lambda: service.get_request(request_id))


@router.patch("/requests/{request_id}")
def patch_request(request_id: str, data: RequestPatchIn) -> dict:
    return _call(lambda: service.update_request(request_id, data.model_dump(exclude_none=True)))


@router.get("/deliveries")
def get_deliveries(status: str = Query("active"), limit: int = Query(50, ge=1, le=100)) -> dict:
    return _call(lambda: service.list_deliveries(status, limit))


@router.post("/deliveries")
def add_delivery(data: DeliveryCreateIn) -> dict:
    return _call(lambda: service.create_delivery(data.model_dump()))


@router.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: str) -> dict:
    return _call(lambda: service.get_delivery(delivery_id))


@router.patch("/deliveries/{delivery_id}")
def patch_delivery(delivery_id: str, data: DeliveryPatchIn) -> dict:
    return _call(lambda: service.update_delivery(delivery_id, data.model_dump(exclude_none=True)))
