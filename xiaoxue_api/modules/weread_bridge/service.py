from __future__ import annotations

import hmac
import time

from . import repository


class BridgeNotFound(Exception):
    """Hide this private bridge when its token is absent or invalid."""


def authorize(token: str) -> None:
    expected = repository.read_secret()
    if not (expected and token and hmac.compare_digest(token, expected)):
        raise BridgeNotFound


def current_confirm_url(*, now: float | None = None) -> str | None:
    state = repository.read_state()
    if state is None:
        return None
    try:
        uid = str(state.get("uid") or "")
        confirm_url = str(state.get("confirm_url") or "")
        valid_until = float(state.get("valid_until") or 0)
    except (TypeError, ValueError):
        return None

    expected_url = f"https://weread.qq.com/web/confirm?uid={uid}"
    current_time = time.time() if now is None else now
    if not uid or confirm_url != expected_url or valid_until <= current_time + 2:
        return None
    return confirm_url


def resolve(token: str) -> str | None:
    authorize(token)
    return current_confirm_url()
