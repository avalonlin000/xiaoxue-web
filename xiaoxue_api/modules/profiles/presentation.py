from fastapi import APIRouter

from . import service


router = APIRouter(prefix="/api", tags=["profiles"])


@router.get("/wiki/team/{team}")
def get_wiki_team(team: str):
    return service.get_wiki_team(team)


@router.get("/wiki/concept/{concept}")
def get_wiki_concept(concept: str):
    return service.get_wiki_concept(concept)


@router.get("/profile-full/{team}")
def get_profile_full(team: str):
    return service.get_full_profile(team)
