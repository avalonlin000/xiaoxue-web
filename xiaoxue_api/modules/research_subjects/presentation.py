from fastapi import APIRouter, HTTPException

from . import service
from .models import DigestIn, EventIn, MaterialIn, ReviewIn, SubjectIn, UserNoteIn


router = APIRouter(prefix="/api/research", tags=["research-subjects"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


@router.post("/subjects")
def open_subject(data: SubjectIn):
    try:
        return service.open_subject(data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.get("/subjects")
def list_subjects(query: str = "", limit: int = 20):
    try:
        return {"subjects": service.list_subjects(query, limit)}
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.get("/subjects/{subject_id}")
def get_subject_dossier(subject_id: int):
    try:
        return service.get_dossier(subject_id)
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.get("/match-brief")
def get_match_research_brief(
    team_a: str, team_b: str, event: str = "", match_date: str = "today", match_time: str = "", match_format: str = "", game: str = "lol",
):
    try:
        return service.get_match_research_brief({
            "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
            "match_time": match_time, "match_format": match_format, "game": game,
        })
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.post("/subjects/{subject_id}/events")
def add_event(subject_id: int, data: EventIn):
    try:
        return service.create_event(subject_id, data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.post("/subjects/{subject_id}/materials")
def add_material(subject_id: int, data: MaterialIn):
    try:
        return service.create_material(subject_id, data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.post("/subjects/{subject_id}/notes")
def add_user_note(subject_id: int, data: UserNoteIn):
    try:
        return service.create_user_note(subject_id, data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.post("/subjects/{subject_id}/digests")
def add_digest(subject_id: int, data: DigestIn):
    try:
        return service.create_digest(subject_id, data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)


@router.post("/subjects/{subject_id}/reviews")
def add_review(subject_id: int, data: ReviewIn):
    try:
        return service.create_review(subject_id, data.model_dump())
    except (ValueError, LookupError) as exc:
        _raise_http(exc)
