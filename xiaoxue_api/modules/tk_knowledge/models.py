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


class GeneralTradingTKIn(BaseModel):
    category: str = "general"
    statement: str
    context: str = ""
    scope: str = "global"
    region: str = ""
    subject: str = ""
    version_context: str = ""
    source_command: str


class GeneralTradingTKStatusIn(BaseModel):
    status: str
    review_note: str = ""
