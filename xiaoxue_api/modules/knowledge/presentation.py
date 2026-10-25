"""长期认识的路由汇总：TK 与版本理解保持原路径。"""

from fastapi import APIRouter

from .tk.presentation import router as tk_router
from .version.presentation import router as version_router

router = APIRouter()
router.include_router(tk_router)
router.include_router(version_router)
