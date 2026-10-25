"""长期认识服务门面：实现分列在 tk／version 子包。"""

from .tk import service as tk
from .version import service as version

__all__ = ["tk", "version"]
