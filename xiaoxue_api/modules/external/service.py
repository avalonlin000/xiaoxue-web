"""外部事实服务门面：实现分列在 gol／football 子包。"""

from .football import service as football
from .gol import service as gol

__all__ = ["football", "gol"]
