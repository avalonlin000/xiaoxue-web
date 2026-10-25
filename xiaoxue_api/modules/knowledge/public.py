"""长期认识统一门面：TK／交易 TK 与版本理解。"""

from .tk.public import *  # noqa: F401,F403
from .version.public import get_global_version_understanding

__all__ = ["get_global_version_understanding"]
