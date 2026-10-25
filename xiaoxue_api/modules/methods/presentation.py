"""LOL 专业方法的路由汇总：阵容分析与英雄静态资料保持原路径。"""

from fastapi import APIRouter

from .hero_static.presentation import router as hero_router
from .lineup.presentation import router as lineup_router

router = APIRouter()
router.include_router(hero_router)
router.include_router(lineup_router)
