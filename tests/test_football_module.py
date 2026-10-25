from __future__ import annotations

from xiaoxue_api.modules.external.football import service


def test_list_matches_keeps_missing_opening_total_as_pending(monkeypatch):
    monkeypatch.setattr(service, "_read_cache", lambda: [])
    monkeypatch.setattr(service, "_write_cache", lambda matches: None)
    monkeypatch.setattr(service, "_enrich_opening_total", lambda matches: matches)
    row = service._normalize_event(
        {
            "id": "100",
            "date": "2026-10-22T12:00:00Z",
            "status": {"type": {"state": "pre", "detail": "Scheduled"}},
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"id": "1", "displayName": "Home"}},
                    {"homeAway": "away", "team": {"id": "2", "displayName": "Away"}},
                ],
            }],
        },
        "eng.1",
    )
    monkeypatch.setattr(service, "_config", lambda: {"leagues": ["eng.1"]})
    monkeypatch.setattr(service, "_dates", lambda: ("20261022", "20261023"))
    monkeypatch.setattr(service, "_matches_for", lambda league, date: ([row], None) if date == "20261022" else ([], None))

    payload = service.list_matches()

    assert payload["matches"]
    assert payload["matches"][0]["opening_total"] is None
    assert payload["matches"][0]["plays"]["half_break"]["decision"] is None
    assert payload["matches"][0]["plays"]["half_break"]["readiness"] == "missing_opening_total"


def test_list_matches_preserves_source_error_with_partial_rows(monkeypatch):
    monkeypatch.setattr(service, "_read_cache", lambda: [])
    monkeypatch.setattr(service, "_write_cache", lambda matches: None)
    monkeypatch.setattr(service, "_enrich_opening_total", lambda matches: matches)
    monkeypatch.setattr(service, "_config", lambda: {"leagues": ["eng.1", "ita.1"]})
    monkeypatch.setattr(service, "_dates", lambda: ("20261022",))
    monkeypatch.setattr(service, "_matches_for", lambda league, date: (
        ([], "ita.1: timeout") if league == "ita.1" else ([{"id": "one", "name": "A vs B", "league": league, "home": {"name": "A"}, "away": {"name": "B"}, "status": "pre", "kickoff": ""}], None)
    ))

    payload = service.list_matches()

    assert payload["readiness"] == "partial"
    assert payload["errors"] == ["ita.1: timeout"]
    assert payload["matches"][0]["id"] == "one"


def test_opening_total_uses_only_the_open_market_line(monkeypatch):
    payload = {
        "odds": [{
            "provider": {"name": "Example"},
            "total": {"over": {"open": {"line": "o2.75", "odds": "-105"}, "close": {"line": "o3", "odds": "-110"}}},
        }]
    }
    assert service._opening_total(payload) == (2.75, {"provider": "Example", "line": "2.75", "odds": "-105"})
