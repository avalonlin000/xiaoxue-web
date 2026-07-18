from __future__ import annotations

from .service import prepare


def prepare_lineup_workflow(payload: dict) -> dict:
    return prepare(payload)
