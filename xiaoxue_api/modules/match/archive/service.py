from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from xiaoxue_api.research_core import repository, service as core
from xiaoxue_api.modules.match.event.public import get_match_desk


DEFAULT_DB_PATH = "/home/ubuntu/xiaoxue-web/data/research_core.sqlite3"
LOL_DOMAIN = "lol"


def open_subject(values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.open_subject(connection, _lol_domain(values.get("domain")), values["subject_key"], values["name"])


def get_dossier(subject_id: int) -> dict:
    with _connection() as connection:
        if connection is None:
            raise LookupError("主体不存在")
        return core.get_subject_dossier(connection, subject_id)


def list_subjects(query: str = "", limit: int = 20) -> list[dict]:
    with _connection() as connection:
        if connection is None:
            return []
        return core.list_subjects(connection, query, limit)


def get_match_research_brief(values: dict) -> dict:
    desk = get_match_desk(**values)
    archives = []
    with _connection() as connection:
        if connection is None:
            return _match_brief_payload(desk, archives)
        for team in (desk["match"]["team_a"], desk["match"]["team_b"]):
            candidates = core.list_subjects(connection, team, 20)
            subject = next((item for item in candidates if item["subject_key"].upper() == team.upper() and item["domain"] == LOL_DOMAIN), None)
            archives.append({"team": team, "dossier": core.get_subject_dossier(connection, subject["id"]) if subject else None})
    return _match_brief_payload(desk, archives)


def create_event(subject_id: int, values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.record_event(connection, subject_id, **values)


def create_material(subject_id: int, values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.record_material(connection, subject_id, **values)


def create_user_note(subject_id: int, values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.record_user_note(connection, subject_id, **values)


def create_digest(subject_id: int, values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.record_digest(connection, subject_id, **values)


def create_review(subject_id: int, values: dict) -> dict:
    with _connection(writable=True) as connection:
        return core.record_review(connection, subject_id, **values)


def _match_brief_payload(desk: dict, archives: list[dict]) -> dict:
    """Keep the old LOL sources visible without making a second copy of them."""
    match = desk["match"]
    return {
        "match": match,
        "match_facts": desk,
        "team_archives": archives,
        "market_records": _matching_market_records(match["team_a"], match["team_b"]),
        "sources": {
            "match_facts": "现有 current-event / 队伍 / TK / 单场工作区正源（只读）",
            "market_records": "交易 TK 中 category=market 的兼容只读投影（唯一正源）",
            "team_archives": "交易信息档案库；只保存明确留存的原始资料、整理、个人笔记和复盘",
        },
        "boundary": "只读并列现有单场事实、TK、盘口记录和长期档案；不自动建档、不写交易、不生成交易结论，也不更新 TK、画像或三维。",
    }


def _matching_market_records(team_a: str, team_b: str) -> list[dict]:
    """盘口记录已于 2026-10-25 退役；交易 TK 是唯一正源。"""
    return []



def _lol_domain(value: object) -> str:
    domain = str(value or "").strip().lower()
    if domain != LOL_DOMAIN:
        raise ValueError("当前主体档案只支持 LOL；其他分类以后通过各自适配器接入")
    return LOL_DOMAIN


@contextmanager
def _connection(*, writable: bool = False):
    path = Path(os.environ.get("XIAOXUE_RESEARCH_CORE_DB_PATH", DEFAULT_DB_PATH))
    if not writable and not path.exists():
        yield None
        return
    if writable:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        if writable:
            repository.initialize(connection)
        yield connection
        if writable:
            connection.commit()
    finally:
        connection.close()
