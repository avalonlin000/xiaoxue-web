from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from xiaoxue_api.modules.external.football import naming as naming_module
from xiaoxue_api.modules.external.football import service

NOW = datetime.now(timezone.utc)
_REAL_CACHED = naming_module.cached
_REAL_RESOLVE = naming_module.resolve


@pytest.fixture(autouse=True)
def _no_history_network(monkeypatch):
    """默认不联网：晚段资料一律按空样本处理，需要时由单个用例覆盖。"""
    empty = {"matches": 0, "with_late": 0, "samples": [], "with_first_half": 0, "first_half_samples": [], "version": 2}
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: dict(empty))
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    monkeypatch.setattr(service.history, "prefetch", lambda targets: None)
    monkeypatch.setattr(service.naming, "cached", lambda name: None)
    monkeypatch.setattr(service, "_translate_missing_names", lambda rows: None)
    monkeypatch.setattr(service, "_get_json", lambda url, timeout=8: {})


def _row(total=None, *, hours=2, status="pre", league="eng.1", home="Alpha", away="Beta", whitelisted=False):
    kickoff = (NOW + timedelta(hours=hours)).isoformat()
    return {
        "id": f"espn:{league}:{abs(hash((home, away, kickoff))) % 100000}",
        "league": league,
        "league_name": service._league_name(league),
        "name": f"{away} at {home}",
        "home": {"id": "1", "name": home, "short_name": home},
        "away": {"id": "2", "name": away, "short_name": away},
        "kickoff": kickoff,
        "status": status,
        "opening_total": total,
        "opening_market": None,
        "plays": {},
        "facts": [],
    }


def _snapshot(rows, saved_at=None, errors=None):
    return {
        "matches": rows,
        "saved_at": (saved_at or NOW).isoformat(),
        "errors": errors or [],
        "coverage": {"source": "ESPN", "leagues": ["eng.1"]},
    }


def _patch_snapshot(monkeypatch, rows, save=None, errors=None):
    snapshot = _snapshot(rows, errors=errors)
    monkeypatch.setattr(service, "_read_snapshot", lambda: dict(snapshot, matches=list(rows)))
    if save is None:
        monkeypatch.setattr(service, "_write_snapshot", lambda matches, errors, coverage: None)
    else:
        monkeypatch.setattr(service, "_write_snapshot", save)
    return snapshot


def _no_network(*_args, **_kwargs):
    raise AssertionError("读取时不应抓网络")


def test_match_detail_uses_competition_kickoff_not_season_year(monkeypatch):
    header = {"season": {"year": 2026}, "competitions": [{
        "date": "2026-10-25T17:30Z", "competitors": [], "status": {},
    }]}
    monkeypatch.setattr(service, "_get_json", lambda url: {"header": header})
    monkeypatch.setattr(service, "_read_snapshot", lambda: {"matches": [], "saved_at": None, "errors": [], "coverage": {}})
    assert service.get_match("espn:esp.1:401882829")["kickoff"] == "2026-10-25T17:30Z"
    header["competitions"][0].pop("date")
    assert service.get_match("espn:esp.1:401882829")["kickoff"] == ""


def test_league_names_are_readable():
    assert service._normalize_event({"id": "1", "date": "2026-10-25T17:30Z", "competitions": [{}]}, "eng.1")["league_name"] == "英超"


def test_team_names_map_to_chinese_and_fall_back_to_original():
    assert service._zh_team("Manchester United") == "曼联"
    assert service._zh_team("Atlético Madrid") == "马德里竞技"
    assert service._zh_team("Atletico Madrid") == "马德里竞技"
    assert service._zh_team("Some Unknown FC") == "Some Unknown FC"
    assert service._zh_team("") == "未知球队"


def test_reason_sentences_translate_team_names():
    assert "博洛尼亚" in service._zh_text("Bologna at AC Milan")
    assert "AC米兰" in service._zh_text("Bologna at AC Milan")


def test_reason_localization_swaps_to_home_first_and_is_idempotent():
    assert service._localize_reason("Bologna at AC Milan 86' 有球") == "AC米兰 vs 博洛尼亚 86' 有球"
    assert service._localize_reason("AC米兰近5场有4场上半场进球（Bologna at AC Milan 8' 有球）") == \
        "AC米兰近5场有4场上半场进球（AC米兰 vs 博洛尼亚 8' 有球）"
    once = service._localize_reason("Bologna at AC Milan 86' 有球")
    assert service._localize_reason(once) == once


def test_rows_expose_chinese_display_names(monkeypatch):
    row = _row(2.5, home="Manchester United", away="Chelsea")
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    service._apply_play_rules([row], {"whitelist": []})
    _patch_snapshot(monkeypatch, [row])
    payload = service.list_matches()
    assert payload["matches"][0]["display_name"] == "曼联 vs 切尔西"
    assert payload["matches"][0]["home"]["display_name"] == "曼联"


def test_keyword_matches_chinese_team_name(monkeypatch):
    rows = service._apply_play_rules([
        _row(2.5, home="Manchester United", away="Chelsea"),
        _row(2.5, home="Bologna", away="AC Milan"),
    ], {"whitelist": []})
    _patch_snapshot(monkeypatch, rows)
    payload = service.list_matches(keyword="曼联")
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["home"]["display_name"] == "曼联"


def test_half_break_pool_exclude_and_outside(monkeypatch):
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    rows = service._apply_play_rules([_row(3.5), _row(2.5), _row(2.25)], {"whitelist": []})
    assert rows[0]["plays"]["half_break"]["decision"] == "exclude"
    assert rows[1]["plays"]["half_break"]["decision"] == "keep"
    assert rows[2]["plays"]["half_break"]["decision"] is None
    assert rows[2]["plays"]["half_break"]["readiness"] == "outside_pool"


def test_whitelisted_team_enters_pool_below_line(monkeypatch):
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    rows = service._apply_play_rules([_row(2.0, home="Atalanta")], {"whitelist": ["Atalanta"]})
    assert rows[0]["plays"]["half_break"]["decision"] == "keep"


def test_late_over_needs_real_late_goal_support(monkeypatch):
    def profile(league, team_id):
        if team_id == "1":
            return {"matches": 5, "with_late": 2, "samples": [{"date": "2026-10-20", "name": "Alpha 2-1 Gamma", "clock": "83'"}],
                    "with_first_half": 3, "first_half_samples": [{"date": "2026-10-20", "name": "Alpha 2-1 Gamma", "clock": "22'"}], "version": 2}
        return {"matches": 5, "with_late": 0, "samples": [], "with_first_half": 1, "first_half_samples": [], "version": 2}

    monkeypatch.setattr(service.history, "profile", profile)
    monkeypatch.setattr(service.history, "cached", profile)
    rows = service._apply_play_rules([_row(2.5)], {"whitelist": []})
    late = rows[0]["plays"]["late_over"]
    assert late["decision"] == "keep"
    assert any("83'" in reason for reason in late["reasons"])
    assert "上半场" in " ".join(rows[0]["plays"]["half_break"]["reasons"])


def test_late_over_excludes_when_both_teams_have_no_late_goals(monkeypatch):
    empty = {"matches": 5, "with_late": 0, "samples": [], "with_first_half": 0, "first_half_samples": [], "version": 2}
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: empty)
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: empty)
    rows = service._apply_play_rules([_row(2.5)], {"whitelist": []})
    assert rows[0]["plays"]["late_over"]["decision"] == "exclude"


def test_late_over_stays_pending_without_history(monkeypatch):
    missing = {"matches": 0, "with_late": 0, "samples": [], "with_first_half": 0, "first_half_samples": [], "version": 2}
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: missing)
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: missing)
    rows = service._apply_play_rules([_row(2.5)], {"whitelist": []})
    assert rows[0]["plays"]["late_over"]["decision"] is None
    assert rows[0]["plays"]["late_over"]["readiness"] == "missing_late_history"


def test_list_matches_filters_each_play_and_counts(monkeypatch):
    rows = service._apply_play_rules([_row(3.5), _row(2.5), _row(2.25)], {"whitelist": []})
    _patch_snapshot(monkeypatch, rows)
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: {"matches": 0, "with_late": 0, "samples": [], "version": 2})

    payload = service.list_matches(play="all")
    assert payload["counts"]["all"] == 1
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["plays"]["half_break"]["decision"] == "keep"
    assert payload["counts"]["half_break"]["keep"] == 1

    half = service.list_matches(play="half_break")
    assert len(half["matches"]) == 1
    assert half["matches"][0]["plays"]["half_break"]["decision"] == "keep"

    late = service.list_matches(play="late_over")
    assert len(late["matches"]) == 0


def test_default_candidates_are_union_of_confirmed_plays(monkeypatch):
    both = _row(2.5, home="Both", away="Play")
    half = _row(2.5, home="Half", away="Only")
    late = _row(2.5, home="Late", away="Only")
    pending = _row(None, home="Pending", away="Only")
    excluded = _row(3.5, home="Excluded", away="Only")
    both["plays"] = {
        "half_break": {"decision": "keep", "readiness": "ready", "reasons": ["半破保留理由"]},
        "late_over": {"decision": "keep", "readiness": "ready", "reasons": ["晚段保留理由"]},
    }
    half["plays"] = {
        "half_break": {"decision": "keep", "readiness": "ready", "reasons": ["半破保留理由"]},
        "late_over": {"decision": "exclude", "readiness": "ready", "reasons": []},
    }
    late["plays"] = {
        "half_break": {"decision": None, "readiness": "outside_pool", "reasons": []},
        "late_over": {"decision": "keep", "readiness": "ready", "reasons": ["晚段保留理由"]},
    }
    pending["plays"] = {
        "half_break": {"decision": None, "readiness": "missing_opening_total", "reasons": []},
        "late_over": {"decision": None, "readiness": "missing_opening_total", "reasons": []},
    }
    excluded["plays"] = {
        "half_break": {"decision": "exclude", "readiness": "ready", "reasons": []},
        "late_over": {"decision": "exclude", "readiness": "ready", "reasons": []},
    }
    _patch_snapshot(monkeypatch, [both, half, late, pending, excluded])

    candidates = service.list_matches(view="candidates", play="all")
    assert {row["id"] for row in candidates["matches"]} == {both["id"], half["id"], late["id"]}
    assert candidates["counts"]["all"] == 3

    all_matches = service.list_matches(view="all", play="all")
    assert len(all_matches["matches"]) == 5

    # 核对页按玩法筛选时保留该玩法的全部结论，供定位待补、排除和圈池外原因。
    half_all = service.list_matches(view="all", play="half_break")
    assert {row["id"] for row in half_all["matches"]} == {
        both["id"], half["id"], late["id"], pending["id"], excluded["id"]
    }
    late_all = service.list_matches(view="all", play="late_over")
    assert {row["id"] for row in late_all["matches"]} == {
        both["id"], half["id"], late["id"], pending["id"], excluded["id"]
    }

    # 默认观察清单仍严格只留该玩法为 keep 的场次。
    assert {row["id"] for row in service.list_matches(view="candidates", play="half_break")["matches"]} == {
        both["id"], half["id"]
    }
    assert {row["id"] for row in service.list_matches(view="candidates", play="late_over")["matches"]} == {
        both["id"], late["id"]
    }


def test_list_matches_serves_snapshot_without_touching_network(monkeypatch):
    rows = service._apply_play_rules([_row(2.5)], {"whitelist": []})
    _patch_snapshot(monkeypatch, rows)
    monkeypatch.setattr(service, "_matches_for", _no_network)
    monkeypatch.setattr(service, "_refresh_in_background", _no_network)
    payload = service.list_matches()
    assert payload["matches"][0]["id"] == rows[0]["id"]


def test_list_matches_drops_stale_matches(monkeypatch):
    fresh = _row(2.5, hours=3)
    stale = _row(2.5, hours=-30)
    fresh["plays"] = {"half_break": {"decision": "keep", "readiness": "ready", "reasons": []}}
    stale["plays"] = {"half_break": {"decision": "keep", "readiness": "ready", "reasons": []}}
    _patch_snapshot(monkeypatch, [fresh, stale])
    payload = service.list_matches()
    assert [row["id"] for row in payload["matches"]] == [fresh["id"]]


def test_prune_keeps_recent_finished_and_drops_old(monkeypatch):
    recent = _row(2.5, hours=-6, status="post")
    old = _row(2.5, hours=-24 * 8, status="post")
    assert [row["id"] for row in service._prune([recent, old])] == [recent["id"]]


def test_keyword_matches_chinese_league_name(monkeypatch):
    rows = service._apply_play_rules([_row(2.5, league="eng.1"), _row(2.5, league="ita.1")], {"whitelist": []})
    _patch_snapshot(monkeypatch, rows)
    payload = service.list_matches(keyword="意甲")
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["league"] == "ita.1"


def test_refresh_writes_snapshot_and_preserves_source_errors(monkeypatch):
    saved = {}
    monkeypatch.setattr(service, "_config", lambda: {"leagues": ["eng.1", "ita.1"], "whitelist": []})
    monkeypatch.setattr(service, "_dates", lambda: ("20261031",))
    monkeypatch.setattr(service, "_matches_for", lambda league, date: (
        ([_row(2.5) if league == "eng.1" else []], None) if league == "eng.1" else ([], "ita.1: timeout")
    ))
    monkeypatch.setattr(service, "_enrich_opening_total", lambda rows: rows)
    monkeypatch.setattr(service, "_prefetch_late_history", lambda rows, config: None)
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: {"matches": 0, "with_late": 0, "samples": [], "version": 2})
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    monkeypatch.setattr(service, "_read_snapshot", lambda: {"matches": [], "saved_at": None, "errors": [], "coverage": {}})
    monkeypatch.setattr(service, "_write_snapshot", lambda matches, errors, coverage: saved.update(matches=matches, errors=errors))
    service.refresh()
    assert saved["errors"] == ["ita.1: timeout"]
    assert saved["matches"]


def test_opening_total_uses_only_the_open_market_line():
    payload = {
        "odds": [{
            "provider": {"name": "Example"},
            "total": {"over": {"open": {"line": "o2.75", "odds": "-105"}, "close": {"line": "o3", "odds": "-110"}}},
        }]
    }
    assert service._opening_total(payload) == (2.75, {"provider": "Example", "line": "2.75", "odds": "-105"})


def test_unknown_team_falls_back_to_auto_translation_cache(monkeypatch):
    monkeypatch.setattr(service.naming, "cached", lambda name: "桑德豪森" if name == "SV Sandhausen" else None)
    assert service._zh_team("SV Sandhausen") == "桑德豪森"


def test_unknown_team_stays_english_without_translation(monkeypatch):
    monkeypatch.setattr(service.naming, "cached", lambda name: None)
    assert service._zh_team("Nowhere United") == "Nowhere United"


def test_refresh_translates_missing_team_names(monkeypatch):
    seen = {}
    row = _row(2.5, home="SV Sandhausen", away="AFC Wimbledon")
    monkeypatch.setattr(service, "_config", lambda: {"leagues": ["ger.1"], "whitelist": []})
    monkeypatch.setattr(service, "_dates", lambda: ("20261031",))
    monkeypatch.setattr(service, "_matches_for", lambda league, date: ([row], None))
    monkeypatch.setattr(service, "_enrich_opening_total", lambda rows: rows)
    monkeypatch.setattr(service, "_prefetch_late_history", lambda rows, config: None)
    monkeypatch.setattr(service.history, "profile", lambda league, team_id: {"matches": 0, "with_late": 0, "samples": [], "version": 2})
    monkeypatch.setattr(service.history, "cached", lambda league, team_id: None)
    monkeypatch.setattr(service, "_read_snapshot", lambda: {"matches": [], "saved_at": None, "errors": [], "coverage": {}})
    called = {}
    monkeypatch.setattr(service, "_write_snapshot", lambda matches, errors, coverage: seen.update(matches=matches))
    monkeypatch.setattr(service, "_translate_missing_names", lambda rows: called.update(rows=rows))

    service.refresh()

    assert called["rows"], "刷新时应把新球队交给自动翻译"


def test_naming_resolves_and_caches_model_answer(tmp_path, monkeypatch):
    from xiaoxue_api.modules.external.football import naming

    monkeypatch.setattr(naming, "CACHE_PATH", tmp_path / "team_names_auto.json")
    monkeypatch.setattr(naming, "_memory", None)
    monkeypatch.setattr(naming, "cached", _REAL_CACHED)
    monkeypatch.setattr(naming, "resolve", _REAL_RESOLVE)
    monkeypatch.setattr(naming, "_translator_config", lambda: {"enabled": True, "batch": 40})
    monkeypatch.setattr(naming, "_ask_model", lambda names, translator: {"SV Sandhausen": "桑德豪森"})

    assert naming.resolve(["SV Sandhausen"]) == {"SV Sandhausen": "桑德豪森"}
    assert naming.cached("SV Sandhausen") == "桑德豪森"

    monkeypatch.setattr(naming, "_ask_model", lambda names, translator: {})
    assert naming.resolve(["SV Sandhausen"]) == {}
    assert naming.cached("SV Sandhausen") == "桑德豪森"


def test_naming_skips_when_translator_disabled(tmp_path, monkeypatch):
    from xiaoxue_api.modules.external.football import naming

    monkeypatch.setattr(naming, "CACHE_PATH", tmp_path / "team_names_auto.json")
    monkeypatch.setattr(naming, "_memory", None)
    monkeypatch.setattr(naming, "cached", _REAL_CACHED)
    monkeypatch.setattr(naming, "resolve", _REAL_RESOLVE)
    monkeypatch.setattr(naming, "_translator_config", lambda: {})
    monkeypatch.setattr(naming, "_ask_model", lambda names, translator: (_ for _ in ()).throw(AssertionError("不应调用模型")))

    assert naming.resolve(["SV Sandhausen"]) == {}
