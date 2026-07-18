from pydantic import BaseModel


class TradingNoteIn(BaseModel):
    team: str
    note: str
    title: str = ""
    market: str = ""
    scenario: str = ""
    status: str = "active"


class TradingNoteTextIn(BaseModel):
    text: str
