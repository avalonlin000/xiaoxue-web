from __future__ import annotations

from pydantic import BaseModel, Field


class LineupWorkflowIn(BaseModel):
    match_name: str = ""
    blue_team: str = ""
    red_team: str = ""
    blue_lineup: dict[str, str] = Field(default_factory=dict)
    red_lineup: dict[str, str] = Field(default_factory=dict)
    bans: str = ""
    starters: str = ""
    market_context: str = ""
    pre_match_judgment: str = ""
