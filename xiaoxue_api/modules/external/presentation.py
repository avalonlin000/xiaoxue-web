"""外部事实源的路由汇总：Gol.gg 逐局事实与足球观察台。"""

from fastapi import APIRouter

from .football.presentation import router as football_router
from .gol.presentation import router as gol_router

router = APIRouter()
router.include_router(gol_router)
router.include_router(football_router)
