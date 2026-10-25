"""队伍能力的路由汇总：事实、画像、TS 三组路由保持原路径。"""

from fastapi import APIRouter

from .facts.presentation import router as facts_router
from .profile.presentation import router as profile_router
from .ts.presentation import router as ts_router

router = APIRouter()
router.include_router(facts_router)
router.include_router(profile_router)
router.include_router(ts_router)
