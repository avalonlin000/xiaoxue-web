"""比赛能力的路由汇总：赛前工作区、范围覆盖、研究档案保持原路径。"""

from fastapi import APIRouter

from .archive.presentation import router as archive_router
from .event.presentation import router as event_router
from .scope.presentation import router as scope_router

router = APIRouter()
router.include_router(event_router)
router.include_router(scope_router)
router.include_router(archive_router)
