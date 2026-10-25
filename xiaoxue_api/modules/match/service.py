"""比赛服务门面：实现分列在 event／scope／archive 子包。"""

from .event import service as event
from .scope import service as scope

__all__ = ["event", "scope"]
