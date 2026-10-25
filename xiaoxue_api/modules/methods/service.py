"""专业方法服务门面：实现分列在 lineup／hero_static 子包。"""

from .hero_static import service as hero_static
from .lineup import service as lineup

__all__ = ["hero_static", "lineup"]
