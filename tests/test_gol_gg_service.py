from xiaoxue_api.modules.gol_gg import service


def test_query_requires_known_kind():
    try:
        service.query("player", tournament="LPL 2026 Split 3")
    except service.GolInputError as exc:
        assert "bp" in str(exc)
    else:
        raise AssertionError("unsupported query kind must fail")

def test_explicit_gol_page_marks_unmatched_current_event_as_conflict(monkeypatch):
    from xiaoxue_api.modules.match.event import service as current_event
    monkeypatch.setattr(current_event, "gol_series_facts", lambda _id: {"games": [{"teams": [{"team": "Other A"}, {"team": "Other B"}]}]})
    monkeypatch.setattr(current_event, "_resolve_run_identity", lambda values: {**values, "team_a": values["team_a"], "team_b": values["team_b"]})
    monkeypatch.setattr(current_event, "_identity_payload", lambda value: value)
    result = current_event.get_gol_series_evidence({"team_a": "EDG", "team_b": "NIP"}, 79966)
    assert result["status"] == "conflict"
    assert result["association"]["conflict"] is True

def test_series_facts_uses_only_discovered_game_pages(monkeypatch):
    pages = {
        11: {
            "game_id": 11, "title": "A vs B game 1", "duration": "30:00", "patch": "16.16",
            "teams": [], "series_games": [{"game_id": 11}, {"game_id": 12}], "source_url": "https://gol.gg/game/stats/11/page-game/", "retrieved_at": "now",
        },
        12: {
            "game_id": 12, "title": "A vs B game 2", "duration": "31:00", "patch": "16.16",
            "teams": [], "series_games": [{"game_id": 11}, {"game_id": 12}], "source_url": "https://gol.gg/game/stats/12/page-game/", "retrieved_at": "now",
        },
    }
    monkeypatch.setattr(service, "game_facts", lambda game_id: pages[int(game_id)])
    result = service.series_facts(11)
    assert [game["game_id"] for game in result["games"]] == [11, 12]
    assert result["series"]["game_count_available"] == 2
