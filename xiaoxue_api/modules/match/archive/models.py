from pydantic import BaseModel, Field


class SubjectIn(BaseModel):
    domain: str = Field(min_length=1, max_length=80)
    subject_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)


class EventIn(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    occurred_at: str = Field(min_length=1, max_length=80)
    details: str = Field(default="", max_length=4000)


class MaterialIn(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=12000)
    captured_at: str = Field(min_length=1, max_length=80)
    source_name: str = Field(default="", max_length=300)
    source_url: str = Field(default="", max_length=2000)
    event_id: int | None = None


class UserNoteIn(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    kind: str = Field(default="user_note", min_length=1, max_length=80)
    event_id: int | None = None


class DigestIn(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    kind: str = Field(default="organized_fact", min_length=1, max_length=80)
    event_id: int | None = None
    source_material_ids: list[int] = Field(min_length=1, max_length=100)


class ReviewIn(BaseModel):
    outcome: str = Field(min_length=1, max_length=4000)
    review: str = Field(min_length=1, max_length=12000)
    event_id: int | None = None
