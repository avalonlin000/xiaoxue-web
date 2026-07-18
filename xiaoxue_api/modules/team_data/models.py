from pydantic import BaseModel


class Team3DUpdate(BaseModel):
    dim_1_value: str = ""
    dim_2_value: str = ""
    dim_3_value: str = ""
    notes: str = ""
    version_understanding: str = ""
