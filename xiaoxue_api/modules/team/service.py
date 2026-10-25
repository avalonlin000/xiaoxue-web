"""队伍能力的服务门面：三块实现分列在 facts／profile／ts 子包。"""

from .facts import service as facts
from .profile import service as profile
from .ts import service as ts

__all__ = ["facts", "profile", "ts"]
