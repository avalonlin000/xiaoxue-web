from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BasketCreateIn(BaseModel):
    module_id: str = Field(default="", max_length=80)
    optional_note: str = Field(default="", max_length=600)
    owner: str = Field(default="钧钧", max_length=80)
    idempotency_key: str = Field(default="", max_length=128)


class BasketPatchIn(BaseModel):
    revision: int = Field(ge=1)
    status: Literal["pending", "paused", "transferred", "removed"] | None = None
    is_focus: bool | None = None
    owner: str = Field(default="钧钧", max_length=80)


class RequestCreateIn(BaseModel):
    basket_item_ids: list[str] = Field(min_length=1, max_length=20)
    user_problem: str = Field(min_length=1, max_length=1200)
    desired_experience: str = Field(min_length=1, max_length=1200)
    desired_result: str = Field(min_length=1, max_length=1200)
    notes: str = Field(default="", max_length=2400)
    triage_summary: str = Field(default="", max_length=2400)
    impact_summary: str = Field(default="", max_length=2400)
    locked_decisions: str = Field(default="", max_length=2400)
    discussion_confirmed: Literal[True]
    owner: str = Field(default="小白", max_length=80)
    idempotency_key: str = Field(default="", max_length=128)


class RequestPatchIn(BaseModel):
    revision: int = Field(ge=1)
    status: Literal["Planned", "In Progress", "Implemented", "Verified", "Released", "Blocked", "Abandoned"] | None = None
    triage_summary: str | None = Field(default=None, max_length=2400)
    impact_summary: str | None = Field(default=None, max_length=2400)
    locked_decisions: str | None = Field(default=None, max_length=2400)
    delivery_summary: str | None = Field(default=None, max_length=2400)
    verification_summary: str | None = Field(default=None, max_length=2400)
    user_validation_path: str | None = Field(default=None, max_length=800)
    blockers: str | None = Field(default=None, max_length=1600)
    archived_reason: str | None = Field(default=None, max_length=1600)
    notes: str | None = Field(default=None, max_length=2400)
    owner: str = Field(default="小白", max_length=80)


class EvidenceIn(BaseModel):
    observed_at: str = Field(min_length=1, max_length=80)
    environment: str = Field(min_length=1, max_length=120)
    entry: str = Field(min_length=1, max_length=300)
    result: str = Field(min_length=1, max_length=1200)
    risk: str = Field(default="无", max_length=600)


class DeliveryCreateIn(BaseModel):
    request_id: str = Field(default="", max_length=80)
    title: str = Field(min_length=1, max_length=200)
    status: Literal["Planned", "In Progress", "Implemented", "Verified", "Released", "Blocked", "Abandoned"] = "Implemented"
    user_visible_change: str = Field(min_length=1, max_length=2400)
    verification_evidence: list[EvidenceIn] = Field(default_factory=list, max_length=20)
    known_risks: str = Field(default="", max_length=1600)
    user_validation_path: str = Field(default="", max_length=800)
    owner: str = Field(default="小白", max_length=80)
    idempotency_key: str = Field(default="", max_length=128)


class DeliveryPatchIn(BaseModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)
    status: Literal["Planned", "In Progress", "Implemented", "Verified", "Released", "Blocked", "Abandoned"] | None = None
    user_visible_change: str | None = Field(default=None, max_length=2400)
    verification_evidence: list[EvidenceIn] | None = Field(default=None, max_length=20)
    known_risks: str | None = Field(default=None, max_length=1600)
    user_validation_path: str | None = Field(default=None, max_length=800)
    feedback_action: Literal["archive", "return_to_basket"] | None = None
    feedback_note: str | None = Field(default=None, max_length=1200)
    owner: str = Field(default="钧钧", max_length=80)
