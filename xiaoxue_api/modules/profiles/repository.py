from __future__ import annotations

import os
import re

from xiaoxue_api.core.database import connect
from xiaoxue_api.core.project_identity import load_project_identity


WIKI_DIR = os.environ.get("XIAOXUE_WIKI_DIR", "/home/ubuntu/workspace/knowledge/wiki")
SKILL_DIRS = (
    os.environ.get("XIAOXUE_SKILL_DIR_XIAOBAI", "/home/ubuntu/.hermes/profiles/xiaobai/skills"),
    os.environ.get("XIAOXUE_SKILL_DIR_MAIN", "/home/ubuntu/.hermes/skills"),
    os.path.expanduser("~/.hermes/hermes-agent/skills"),
)


def read_current_profile(team: str) -> dict | None:
    """Read the existing canonical five-field table; never create/migrate it."""
    with connect() as conn:
        row = conn.execute(
            "SELECT team_name, positioning, win_path, lose_path, key_points, bp_tendency, updated_at "
            "FROM team_profiles WHERE UPPER(team_name)=? LIMIT 1", (team.upper(),),
        ).fetchone()
    return dict(row) if row else None


def wiki_team_path(team: str) -> str:
    return os.path.join(WIKI_DIR, load_project_identity().knowledge_namespace, "实体画像", "队伍", f"{safe_name(team)}.md")


def wiki_concept_path(concept: str) -> str:
    return os.path.join(WIKI_DIR, load_project_identity().knowledge_namespace, "战术概念", f"{safe_name(concept)}.md")


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as source:
            return source.read()
    except OSError:
        return None


TEAM_PROFILES_RELATIVE = os.path.join("esports", "teams", "team-profiles", "references")


def find_skill_path(team: str) -> str:
    for base in SKILL_DIRS:
        candidate = os.path.join(base, TEAM_PROFILES_RELATIVE, f"{team.lower()}.md")
        if os.path.exists(candidate):
            return candidate
    return ""


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "-", value.strip().lower()).strip("-")
