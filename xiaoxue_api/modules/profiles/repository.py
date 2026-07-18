from __future__ import annotations

import os
import re


WIKI_DIR = os.environ.get("XIAOXUE_WIKI_DIR", "/home/ubuntu/workspace/knowledge/wiki")
SKILL_DIRS = (
    os.environ.get("XIAOXUE_SKILL_DIR_XIAOBAI", "/home/ubuntu/.hermes/profiles/xiaobai/skills"),
    os.environ.get("XIAOXUE_SKILL_DIR_MAIN", "/home/ubuntu/.hermes/skills"),
    os.path.expanduser("~/.hermes/hermes-agent/skills"),
)


def wiki_team_path(team: str) -> str:
    return os.path.join(WIKI_DIR, "小雪电竞", "实体画像", "队伍", f"{safe_name(team)}.md")


def wiki_concept_path(concept: str) -> str:
    return os.path.join(WIKI_DIR, "小雪电竞", "战术概念", f"{safe_name(concept)}.md")


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as source:
            return source.read()
    except OSError:
        return None


def find_skill_path(team: str) -> str:
    for base in SKILL_DIRS:
        candidate = os.path.join(base, f"{team.lower()}-team-profile", "SKILL.md")
        if os.path.exists(candidate):
            return candidate
    return ""


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "-", value.strip().lower()).strip("-")
