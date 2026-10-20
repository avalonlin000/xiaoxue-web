"""Stable product-facing operations for the generic subject dossier."""

from .service import create_event, create_material, create_review, create_user_note, get_dossier, get_match_research_brief, open_subject

__all__ = ["open_subject", "get_dossier", "get_match_research_brief", "create_event", "create_material", "create_user_note", "create_review"]
