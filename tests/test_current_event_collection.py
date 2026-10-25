import json
import sqlite3
from unittest.mock import patch

import pytest
import httpx

from xiaoxue_api.modules.current_event import collection, collection_repository as repo

real_read_article = repo.read_article


MATCH = {"team_a": "KC", "team_b": "MVK", "event": "Worlds", "match_date": "2026-10-19", "match_time": "02:00"}


@pytest.fixture(autouse=True)
def isolated_sources(tmp_path, monkeypatch):
    # Reader unit tests must not share production caches or configured seed URLs.
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "isolated-materials"))
    monkeypatch.setattr("xiaoxue_api.modules.current_event.service.get_current_event", lambda: {"event": "unit-test"})
    monkeypatch.setattr(repo, "dependency_manifest", lambda _: {"internal": "test", "library": "test", "external": "test", "analysis": "test"})
    for name in ("search", "read_article", "call_digest_model"):
        monkeypatch.setattr(repo, name, lambda *args, **kwargs: pytest.fail("单测禁止真实网络或模型请求"))


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    # Unit tests exercise storage/network failure, never spend a model request.
    monkeypatch.setattr(repo, "summarize_materials", lambda *_: ([], []))
    monkeypatch.setattr(repo, "collect_library", lambda *_: ([], []))
    monkeypatch.setattr(repo, "analyze_materials", lambda *_: ([], []))
    return tmp_path / "materials"


def test_read_is_side_effect_free_and_rejects_invalid_identity(store):
    assert collection.get_prepared_materials(MATCH) == {"task": None, "result": None}
    assert not store.exists()
    with pytest.raises(ValueError):
        collection.prepare_materials({**MATCH, "team_a": "TBD"}, dispatch=False)
    assert not store.exists()


def test_two_analysis_lines_can_be_ready_without_claiming_realtime_bp_or_quotes(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    digest = [{"id": "digest", "title": "公开分析", "selection_status": "screened", "summary": "已有作者分析", "items": [{"text": "作者有依据的本场分析", "kind": "author_analysis"}]}]
    own = [{"id": "analysis", "title": "个人方法", "items": [{"text": "根据本场事实推导", "verification": "system_inference", "inference_scope": "supported"}]}]
    facts = [{"id": "facts", "title": "本场事实", "items": [{"text": "赛程与本届战绩", "verification": "official_api"}]}]
    with patch.object(repo, "collect_internal", return_value=(facts, [])), patch.object(repo, "collect_external", return_value=([], [])), patch.object(repo, "summarize_materials", return_value=(digest, [])), patch.object(repo, "analyze_materials", return_value=(own, [])):
        collection.run_collection(task["id"])
    data = collection.get_collection_task(task["id"])
    assert data["task"]["state"] == "completed"
    assert data["result"]["delivery"]["ready"] is True
    assert data["result"]["conditional_capabilities"] == {"live_bp": "unverified", "market_quotes": "unverified"}
    checkpoint = repo.read_checkpoint(task)["stages"]
    assert checkpoint["analysis"]["sections"] == own


def test_background_and_conditional_analysis_are_readable_but_not_full_readiness(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    digest = [{"id": "digest", "selection_status": "screened", "summary": "仅取得背景报道", "items": [{"text": "本场赛制报道", "kind": "reported_information"}]}]
    own = [{"id": "analysis", "items": [{"text": "没有当前事实，只给规律检验条件", "inference_scope": "conditional"}]}]
    with patch.object(repo, "collect_internal", return_value=([], [])), patch.object(repo, "collect_external", return_value=([], [])), patch.object(repo, "summarize_materials", return_value=(digest, [])), patch.object(repo, "analyze_materials", return_value=(own, [])):
        collection.run_collection(task["id"])
    result = collection.get_collection_task(task["id"])["result"]
    assert result["delivery"]["ready"] is False
    assert result["delivery"]["public_author_analysis"] == "unavailable"
    assert result["delivery"]["personal_analysis_scope"] == "conditional"
    assert result["status"] == "partial"


def test_failed_screening_is_not_announced_as_screened_or_fully_prepared(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    observed = []
    def analyze(*_):
        observed.extend(repo.read(task["id"])["task"].get("progress", []))
        return [], []
    internal = [{"id": "team_KC", "items": [{"text": "已有队伍资料"}]}]
    with patch.object(repo, "collect_internal", return_value=(internal, [])), \
         patch.object(repo, "collect_external", return_value=([], [])), \
         patch.object(repo, "summarize_materials", return_value=([], ["本次信息粗筛未完成"])), \
         patch.object(repo, "analyze_materials", side_effect=analyze):
        collection.run_collection(task["id"])
    saved = collection.get_collection_task(task["id"])
    assert "公开内容已筛选" not in observed
    assert any("未完成" in item for item in observed)
    assert saved["task"]["state"] == "partial"
    assert "待补" in saved["task"]["message"]


def test_lol_sources_are_not_silently_applied_to_other_games(store):
    with pytest.raises(ValueError, match="只适用于 LOL"):
        collection.prepare_materials({**MATCH, "game": "valorant"}, dispatch=False)
    assert not store.exists()


def test_repeated_request_reuses_same_task_and_readback(store):
    first = collection.prepare_materials(MATCH, dispatch=False)
    second = collection.prepare_materials(MATCH, dispatch=False)
    assert first["task"]["id"] == second["task"]["id"]
    assert first["task"]["state"] == "queued"
    assert collection.get_collection_task(first["task"]["id"])["task"]["match"]["team_a"] == "KC"


def test_collected_article_is_readable_and_source_failure_does_not_erase_it(store):
    article = {"title": "KC公告", "url": "https://lolesports.com/news/announcement", "text": "KC 与 MVK 将进行系列赛。KC 教练说明训练安排。", "source": "lolesports.com", "published_at": "2026-10-18T12:00:00+08:00", "verification": "source_text"}
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    with patch.object(repo, "collect_internal", return_value=([{"id": "teams", "title": "双方资料", "items": [{"text": "KC / MVK", "source": "正式资料"}]}], [])), patch.object(repo, "collect_external", return_value=([article], ["部分新闻来源暂不可读"])):
        collection.run_collection(task["id"])
    result = collection.get_collection_task(task["id"])
    assert result["task"]["state"] == "partial"
    assert "训练安排" in json.dumps(result["result"], ensure_ascii=False)
    assert result["result"]["revision"]
    assert result["result"]["limitations"]
    # A subsequent failed refresh preserves the last readable snapshot.
    refresh = collection.prepare_materials(MATCH, refresh=True, dispatch=False)["task"]
    with patch.object(repo, "collect_internal", side_effect=RuntimeError("内部源失败")), patch.object(repo, "collect_external", side_effect=RuntimeError("外部源失败")):
        collection.run_collection(refresh["id"])
    assert collection.get_prepared_materials(MATCH)["result"]["revision"] == result["result"]["revision"]


def test_time_and_game_identity_do_not_cross_contaminate(store):
    one = collection.prepare_materials(MATCH, dispatch=False)["task"]
    two = collection.prepare_materials({**MATCH, "match_time": "16:00"}, dispatch=False)["task"]
    assert one["id"] != two["id"]
    with pytest.raises(ValueError):
        collection.get_collection_task("../../elsewhere")


def test_missing_time_is_resolved_only_from_an_unambiguous_schedule(store):
    rows = [{"team_a": "KC", "team_b": "MVK", "time": "02:00", "stage": "Worlds", "format": "BO3"}]
    with patch.object(collection, "list_schedules", return_value=rows):
        resolved = collection.prepare_materials({**MATCH, "match_time": ""}, dispatch=False)
    assert resolved["task"]["match"]["match_time"] == "02:00"
    with patch.object(collection, "list_schedules", return_value=rows + [{**rows[0], "time": "16:00"}]):
        with pytest.raises(ValueError, match="多场"):
            collection.prepare_materials({**MATCH, "match_time": ""}, dispatch=False)


def test_only_one_worker_can_claim_a_task_and_interrupted_task_can_resume(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    claim = repo.claim(task["id"])
    assert claim
    assert repo.claim(task["id"]) is None
    repo.update_task(task["id"], {"lease_until": "2000-01-01T00:00:00+00:00"})
    recovered = collection.resume_collection(task["id"], dispatch=False)
    assert recovered["task"]["state"] == "running"
    assert repo.claim(task["id"])["attempts"] == 2


def test_source_urls_block_private_and_active_content():
    for url in ["file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1:8880/api/teams", "http://169.254.169.254/", "http://user:pass@example.com", "https://localhost/a"]:
        assert not repo.is_public_url(url)
    assert repo.is_public_url("https://lolesports.com/news/test")


def test_search_lines_are_not_mistaken_for_read_articles():
    assert repo.parse_search_results({"results": [{"title": "test", "url": "https://lolesports.com/news/test", "snippet": "KC新闻"}]})[0]["verification"] == "search_lead"


def test_existing_hermes_search_shape_and_private_text_leads():
    payload = {"success": True, "data": {"web": [{"title": "官方消息", "url": "https://lolesports.com/news/test"}]}}
    assert repo.parse_search_results(payload)[0]["title"] == "官方消息"
    assert repo.parse_search_results("Title: secret\nURL: http://127.0.0.1/private") == []


def test_exa_text_keeps_publication_dates_and_all_requested_candidates():
    text = "\n---\n".join(
        f"Title: Report {index}\nURL: https://example.com/report-{index}\n"
        f"Published: {'N/A' if index == 7 else '2026-10-21T08:30:00.000Z'}\n"
        "Author: Reporter\nHighlights:\nA reported change."
        for index in range(8)
    )
    rows = repo.parse_search_results({"content": [{"type": "text", "text": text}]})
    assert len(rows) == 8
    assert rows[0]["published_at"] == "2026-10-21T08:30:00.000Z"
    assert rows[-1]["published_at"] == ""
    assert all(row["verification"] == "search_lead" for row in rows)


def test_collector_reads_relevant_results_after_failed_top_hits(store):
    leads = [{"url": f"https://example.com/report-{index}", "title": f"Report {index}",
              "published_at": "2026-10-18T12:00:00Z"} for index in range(8)]
    def read(url):
        if int(url.rsplit("-", 1)[1]) < 6:
            raise ValueError("unreadable candidate")
        return "KC and MVK coaches explained their recent preparation and objective control. " * 6 + url
    with patch.object(repo, "search", return_value=(leads, "")), patch.object(repo, "read_article", side_effect=read):
        rows, _ = repo.collect_external(MATCH)
    assert {row["url"] for row in rows} == {leads[6]["url"], leads[7]["url"]}


def test_collection_time_reserves_processing_and_keeps_articles_recoverable(store):
    elapsed = [0.0]
    leads = [{"url": f"https://example.com/time-{index}", "title": f"Report {index}"}
             for index in range(8)]
    def read(url):
        elapsed[0] += 100
        return "KC and MVK coaches explained preparation and objective control. " * 8 + url
    with patch.object(repo, "monotonic", side_effect=lambda: elapsed[0]), \
         patch.object(repo, "search", return_value=(leads, "")), \
         patch.object(repo, "read_article", side_effect=read), repo.collection_budget(720):
        rows, missing = repo.collect_external(MATCH)
        assert repo.remaining_timeout(720) >= 200
    assert len(rows) >= 2
    stage = collection._stage_result([{"id": "news", "items": rows}], missing)
    assert stage["sections"][0]["items"] == rows
    assert stage["failed"] is True


def test_body_count_budget_keeps_partial_articles_recoverable(store, monkeypatch):
    monkeypatch.setattr(repo, "MATCH_READ_ATTEMPTS", 2)
    leads = [{"url": f"https://example.com/count-{index}", "title": f"Report {index}"}
             for index in range(4)]
    with patch.object(repo, "search", return_value=(leads, "")), \
         patch.object(repo, "read_article", side_effect=lambda url: "KC and MVK explained their recent training and preparation. " * 8 + url):
        rows, missing = repo.collect_external(MATCH)
    assert len(rows) == 2
    assert collection._stage_result([{"id": "news", "items": rows}], missing)["failed"] is True


def test_existing_exa_reader_is_used_when_primary_extraction_fails(monkeypatch):
    monkeypatch.setattr(repo, "read_article", real_read_article)
    content = "KC and MVK published their preparation and coaching interview. " * 8
    with patch.object(repo, "_public_dns", return_value=True), \
         patch.object(repo, "_read_with_extract_backend", side_effect=ValueError("primary unavailable")), \
         patch.object(repo, "_read_with_exa", return_value=content) as exa, \
         patch.object(repo, "_read_with_mirror", side_effect=AssertionError("working reader must avoid dead mirror")):
        assert repo.read_article("https://example.com/interview") == content
    exa.assert_called_once_with("https://example.com/interview")


def test_stale_worker_cannot_finish_after_another_worker_recovers(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    old = repo.claim(task["id"])
    repo.update_task(task["id"], {"lease_until": "2000-01-01T00:00:00+00:00"})
    replacement = repo.claim(task["id"])
    assert replacement["attempts"] == 2
    repo.finish(old, None, message="旧任务不得覆盖")
    assert repo.read(task["id"])["task"]["state"] == "running"


def test_content_revision_does_not_change_only_because_capture_time_changes(store):
    def complete(captured_at):
        task = collection.prepare_materials(MATCH, refresh=True, dispatch=False)["task"]
        claimed = repo.claim(task["id"])
        result = {"match": claimed["match"], "updated_at": repo.now(), "status": "partial", "sections": [{"id": "news", "items": [{"text": "同一内容", "captured_at": captured_at}]}], "limitations": []}
        repo.finish(claimed, result)
        return repo.read(task["id"])["result"]["revision"]
    assert complete("2026-10-19T01:00:00Z") == complete("2026-10-19T01:10:00Z")


def test_internal_adapter_uses_real_public_contracts():
    with patch("xiaoxue_api.modules.team.public.get_match_context", return_value={"team_a": {"team": "KC", "ts": 20}, "team_b": {"team": "MVK", "ts": 19}}), patch("xiaoxue_api.modules.team.public.get_profile_bundle", return_value={"team": {"region": "LEC"}, "players": [{"name": "Player", "role": "中单"}], "three_dimensional": {"notes": "旧笔记不可冒充画像", "updated_at": "2026-10-18"}}), patch("xiaoxue_api.modules.team.public.get_current_profile", return_value={"found": True, "profile": {"positioning": "中期资源团"}, "updated_at": "2026-10-18"}), patch("xiaoxue_api.modules.knowledge.tk.public.list_match_trading_tk", return_value={"items": [{"statement": "先看版本", "status": "confirmed"}]}) as tk:
        sections, limitations = repo.collect_internal(MATCH)
    tk.assert_called_once_with(region="LEC", teams=["KC", "MVK"], players=["Player"], limit=12)
    text = json.dumps(sections, ensure_ascii=False)
    assert "中期资源团" in text and "先看版本" in text
    assert "mu " not in text and "σ " not in text
    assert "旧笔记" not in text
    assert not limitations


def test_current_profile_reads_existing_canonical_fields_without_migration(tmp_path, monkeypatch):
    from xiaoxue_api.core import database
    from xiaoxue_api.modules.team.public import get_current_profile
    path = tmp_path / "profiles.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE team_profiles(team_name TEXT, positioning TEXT, win_path TEXT, lose_path TEXT, key_points TEXT, bp_tendency TEXT, updated_at TEXT)")
        db.execute("INSERT INTO team_profiles VALUES(?,?,?,?,?,?,?)", ("KC", "已确认的定位", "赢法", "输法", "关键点", "BP", "2026-10-19"))
    monkeypatch.setattr(database, "DB_PATH", str(path))
    profile = get_current_profile("kc")
    assert profile["profile"]["positioning"] == "已确认的定位"
    assert get_current_profile("MVK")["found"] is False
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM team_profiles").fetchone()[0] == 1


def test_reader_reuses_existing_extract_backend_when_jina_is_unreachable(monkeypatch):
    # Exercise the reader itself, while both transport backends remain mocked.
    monkeypatch.setattr(repo, "read_article", real_read_article)
    content = "KC 与 MVK 的官方消息。" * 30
    response = type("Completed", (), {"returncode": 0, "stdout": json.dumps({"results": [{"url": "https://lolesports.com/news/test", "content": content, "error": ""}]})})()
    with patch.object(repo, "_public_dns", return_value=True), patch.object(repo.httpx, "stream", side_effect=httpx.ConnectError("offline")), patch.object(repo.subprocess, "run", return_value=response):
        assert repo.read_article("https://lolesports.com/news/test") == content


def test_page_heading_or_video_metadata_is_not_a_readable_match_article():
    with patch.object(repo, "search", return_value=([{"title": "KC vs MVK", "url": "https://example.org/news", "verification": "search_lead", "published_at": ""}], "")), patch.object(repo, "read_article", return_value="# KC vs MVK\n" + "与本场无关的页面导航内容。" * 30):
        articles, limitations = repo.collect_external(MATCH)
    assert not articles
    assert any("正文" in notice for notice in limitations)
    with patch.object(repo, "search", return_value=([{"title": "KC vs MVK", "url": "https://example.org/news", "verification": "search_lead"}], "")), patch.object(repo, "read_article", return_value='![Image: KC team logo](https://example.org/KC "KC") ' * 20):
        articles, _ = repo.collect_external(MATCH)
    assert not articles
    # Real wiki extracts prefix linked logo rows with an invisible word joiner.
    with patch.object(repo, "search", return_value=([{"title": "KC vs MVK", "url": "https://example.org/news", "verification": "search_lead"}], "")), patch.object(repo, "read_article", return_value='\u2060[![Image: KC logo](https://example.org/KC.png)](https://example.org/KC) vs MVK ' * 8):
        articles, _ = repo.collect_external(MATCH)
    assert not articles


def test_news_directory_is_not_counted_as_a_read_article():
    with patch.object(repo, "search", return_value=([{"title": "Latest esports news", "url": "https://example.org/de/all", "verification": "search_lead"}], "")), patch.object(repo, "read_article") as reader:
        articles, limitations = repo.collect_external(MATCH)
    reader.assert_not_called()
    assert not articles
    assert any("目录" in text for text in limitations)


@pytest.mark.parametrize("url", [
    "https://www.sheepesports.com/en/lol/teams/Anyone%27s%20Legend",
    "https://liquipedia.net/leagueoflegends/Anyone%27s_Legend/Played_Matches",
])
def test_team_news_index_and_score_archive_do_not_fill_article_target(url):
    with patch.object(repo, "search", return_value=([{"title": "KC team stats", "url": url}], "")), \
         patch.object(repo, "read_article") as reader:
        articles, _ = repo.collect_external(MATCH)
    reader.assert_not_called()
    assert not articles


def test_recovery_resumes_completed_internal_stage_instead_of_recollecting(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    old = repo.claim(task["id"])
    assert repo.checkpoint(old, {"internal": {"sections": [
        {"id": "facts", "title": "本场事实", "items": [{"text": "赛程与战绩"}]},
        {"id": "strength", "title": "实力资料", "items": [{"text": "已取得的资料"}]}], "limitations": []}})
    repo.update_task(task["id"], {"lease_until": "2000-01-01T00:00:00+00:00"})
    with patch.object(repo, "collect_internal", side_effect=AssertionError("不应重复采集已完成步骤")) as internal, patch.object(repo, "collect_external", return_value=([], ["外部来源不可用"])):
        collection.run_collection(task["id"])
    internal.assert_not_called()
    assert "已取得的资料" in json.dumps(repo.read(task["id"])["result"], ensure_ascii=False)


def test_restart_schedules_recovery_for_a_still_leased_interrupted_task(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    repo.claim(task["id"])
    with patch.object(collection, "Timer") as timer:
        assert collection.resume_pending_collections() == 1
    timer.assert_called_once()
    timer.return_value.start.assert_called_once()


def test_internal_checkpoint_is_readable_while_external_work_is_running(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    claimed = repo.claim(task["id"])
    repo.checkpoint(claimed, {"internal": {"sections": [{"id": "strength", "title": "实力资料", "items": [{"text": "可先阅读的已有资料"}]}], "limitations": []}})
    packet = collection.get_collection_task(task["id"])
    assert packet["task"]["state"] == "running"
    assert packet["result"]["status"] == "partial"
    assert "可先阅读" in json.dumps(packet["result"], ensure_ascii=False)


def test_collected_content_does_not_become_user_judgment_or_prices(store):
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    with patch.object(repo, "collect_internal", return_value=([], [])), patch.object(repo, "collect_external", return_value=([{ "title": "预测", "url": "https://example.com/a", "text": "KC MVK 胜率预测", "source": "example.com", "verification": "source_text"}], [])):
        collection.run_collection(task["id"])
    result = collection.get_prepared_materials(MATCH)["result"]
    assert result["status"] == "partial"
    assert "direction" not in result
    assert not any(item.get("id") in {"bp", "market"} and item.get("items") for item in result["sections"])


def test_prepared_list_reads_only_selected_date(store):
    collection.prepare_materials(MATCH, dispatch=False)
    assert collection.list_prepared_materials("2026-10-20")["items"] == []


def test_batch_reuses_configured_schedule_scope_and_does_not_fabricate_opponents(store):
    rows = [{"team_a": "KC", "team_b": "MVK", "date": "2026-10-19", "time": "02:00", "stage": "Worlds", "format": "BO3"}, {"team_a": "TBD", "team_b": "MVK", "date": "2026-10-19", "time": "04:00", "stage": "Worlds"}]
    with patch("xiaoxue_api.modules.current_event.collection.get_current_event", return_value={"event": "Worlds"}), patch("xiaoxue_api.modules.current_event.collection.list_schedules", return_value=rows) as schedules:
        report = collection.prepare_date("2026-10-19", dispatch=False)
    # Read one extra row so a full batch can honestly report truncation.
    schedules.assert_called_once_with({"date_from": "2026-10-19", "date_to": "2026-10-19", "event": "Worlds"}, 201)
    assert len(report["tasks"]) == 1
    assert len(report["skipped"]) == 1
    assert report["tasks"][0]["match"]["team_a"] == "KC"


def test_reader_tries_the_configured_extractor_before_the_mirror(monkeypatch):
    # The mirror is a fallback: a dead mirror must not be paid for on every article.
    monkeypatch.setattr(repo, "read_article", real_read_article)
    content = "GEN 与 IG 在世界赛的公开资料。" * 30
    response = type("Completed", (), {"returncode": 0, "stdout": json.dumps({"results": [{"url": "https://lolesports.com/news/test", "content": content, "error": ""}]})})()
    mirror = type("Stream", (), {"__call__": lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应先调用镜像"))})()
    with patch.object(repo, "_public_dns", return_value=True), patch.object(repo.httpx, "stream", mirror), patch.object(repo.subprocess, "run", return_value=response):
        assert repo.read_article("https://lolesports.com/news/test") == content
