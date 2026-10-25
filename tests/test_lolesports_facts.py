import json

import pytest

from xiaoxue_api.modules.current_event import lolesports_facts as facts


def _fixture(path: str):
    if path.startswith("getLeagues"):
        return {"data": {"leagues": [{"id": "L1", "slug": "worlds"}]}}
    if path.startswith("getTournamentsForLeague"):
        return {"data": {"leagues": [{"tournaments": [
            {"id": "T1", "slug": "worlds_2026", "startDate": "2026-10-15", "endDate": "2026-11-15"}]}]}}
    if path.startswith("getTeams"):
        return {"data": {"teams": [
            {"code": "GEN", "name": "Gen.G Esports", "players": [
                {"summonerName": "Chovy", "role": "mid"}, {"summonerName": "Kiin", "role": "top"},
                {"summonerName": "AcademyGuy", "role": "top"}]},
            {"code": "HLE", "name": "HLE Academy", "players": [{"summonerName": "Kid", "role": "mid"}]},
        ]}}
    if path.startswith("getSchedule"):
        return {"data": {"schedule": {"events": [
            {"startTime": "2026-10-23T17:00:00Z", "state": "completed", "blockName": "瑞士轮",
             "match": {"teams": [
                 {"code": "GEN", "result": {"gameWins": 1}, "record": {"wins": 1, "losses": 0}},
                 {"code": "IG", "result": {"gameWins": 0}, "record": {"wins": 0, "losses": 1}}],
                 "strategy": {"count": 1}}},
            {"startTime": "2026-10-24T22:00:00Z", "state": "unstarted", "blockName": "瑞士轮",
             "match": {"teams": [
                 {"code": "GEN", "result": None, "record": {"wins": 1, "losses": 0}},
                 {"code": "HLE", "result": None, "record": {"wins": 1, "losses": 0}}],
                 "strategy": {"count": 1}}},
        ]}}}
    raise AssertionError(path)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path))
    monkeypatch.setattr(facts, "_get", _fixture)


def test_builds_official_facts_for_confirmed_match():
    sections, limits = facts.facts({"team_a": "GEN", "team_b": "HLE", "event": "S16全球总决赛",
                                    "match_date": "2026-10-25", "match_time": "06:00"})
    assert limits == []
    assert sections[0]["id"] == "facts"
    text = "\n".join(item["text"] for item in sections[0]["items"])
    assert "10-25 06:00（北京时间）" in text
    assert "BO1" in text
    assert "GEN 本届 1-0" in text and "HLE 本届 1-0" in text
    assert "10-24 01:00 瑞士轮 1:0 IG" in text
    assert "中单 Chovy" in text and "上单 Kiin" in text
    assert all(item["verification"] == "official_api" for item in sections[0]["items"])


def test_tbd_match_is_skipped_without_guessing():
    sections, limits = facts.facts({"team_a": "TBD", "team_b": "TBD", "event": "S16全球总决赛",
                                    "match_date": "2026-10-26"})
    assert sections == [] and limits == []


def test_unmapped_event_reports_gap_instead_of_fabricating():
    sections, limits = facts.facts({"team_a": "GEN", "team_b": "HLE", "event": "LPL 第三赛段",
                                    "match_date": "2026-08-01"})
    assert sections == []
    assert limits and "未生成" in limits[0]


def test_api_failure_does_not_raise():
    original = facts._get
    facts._get = lambda path, timeout=12: (_ for _ in ()).throw(OSError("down"))
    try:
        sections, limits = facts.facts({"team_a": "GEN", "team_b": "HLE", "event": "S16全球总决赛",
                                        "match_date": "2026-10-25"})
    finally:
        facts._get = original
    assert sections == []
    assert limits and "暂不可读" in limits[0]
