from pydantic import BaseModel, Field


class Team3DUpdate(BaseModel):
    dim_1_value: str = ""
    dim_2_value: str = ""
    dim_3_value: str = ""
    notes: str = ""
    version_understanding: str = ""


class TeamProfileUpdate(BaseModel):
    positioning: str = ""
    win_path: str = ""
    lose_path: str = ""
    key_points: str = ""
    bp_tendency: str = ""
    evidence: list = Field(default_factory=list)
