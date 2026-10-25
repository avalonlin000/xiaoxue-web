import json
from unittest.mock import patch

import pytest

from xiaoxue_api.modules.match.event import analysis_repository as analysis
from xiaoxue_api.modules.match.event import collection, collection_repository as repo


def test_limitations_split_structural_from_transient():
    rows = collection.classify_limitations([
        "部分网页未取得与双方相关的有效正文，未把标题或导航算作材料",
        "本轮先整理已取得原文，其余来源等待自动恢复",
        "本轮先整理已取得原文，其余来源等待自动恢复",
    ])
    assert [row["kind"] for row in rows] == ["structural", "transient"]
    assert len(rows) == 2


def test_digest_items_keep_updates_first_and_cap_market_and_background():
    items = [
        {"text": "GEN 上单换人", "relevance": "match_update", "event_key": "a"},
        {"text": "HLE 训练赛状态", "relevance": "match_update", "event_key": "b"},
        {"text": "赛前预测市场 GEN 78%", "relevance": "useful_background", "event_key": "c"},
        {"text": "博彩赔率 GEN 1.24", "relevance": "useful_background", "event_key": "d"},
        {"text": "赛事阶段说明", "relevance": "useful_background", "event_key": "e"},
        {"text": "版本改动背景", "relevance": "useful_background", "event_key": "f"},
        {"text": "第三条背景", "relevance": "useful_background", "event_key": "g"},
    ]
    selected = repo.select_digest_items(items)
    texts = [row["text"] for row in selected]
    assert texts[0] == "GEN 上单换人" and texts[1] == "HLE 训练赛状态"
    assert sum(1 for text in texts if "赔率" in text or "预测市场" in text) == 1
    assert "第三条背景" not in texts
    assert len(selected) <= 8


def test_relevant_leads_drop_unrelated_and_encyclopedia_results():
    leads = [
        {"title": "学习通怎么发起签到", "url": "https://jingyan.baidu.com/article/1", "snippet": ""},
        {"title": "OpenAI 官网", "url": "https://openai.com/", "snippet": ""},
        {"title": "S16瑞士轮战报：CFO战胜TLAW", "url": "https://news.qq.com/rain/a/1", "snippet": ""},
    ]
    kept = repo.relevant_leads("S16 瑞士轮 战报", leads)
    assert [row["title"] for row in kept] == ["S16瑞士轮战报：CFO战胜TLAW"]


def test_compact_query_keeps_event_and_team_tokens():
    compact = repo.compact_query("League of Legends S16全球总决赛 GEN vs HLE match preview analysis 2026 -site:youtube.com")
    assert compact == "全球总决赛 S16 GEN HLE 赛前分析"


def test_one_slow_method_does_not_drop_the_others(monkeypatch):
    inputs = [
        {"id": "I1", "kind": "cycle", "comparable": True, "text": "GEN 100 / HLE 90", "display_text": "GEN 100 / HLE 90"},
        {"id": "I2", "kind": "author_analysis", "text": "作者认为 GEN 更强", "evidence_quote": "GEN stronger"},
    ]
    monkeypatch.setattr(analysis, "collect_inputs", lambda identity, sections: inputs)
    monkeypatch.setattr(analysis, "public_inputs", lambda sections: [])

    def model(packet):
        method = packet["methods"][0]["id"]
        if method == "trading":
            raise TimeoutError("slow")
        return json.dumps({"items": [{"method_id": method, "text": "判断", "basis": "依据", "confirmation": "确认", "invalidation": "失效",
                                      "source_ids": ["I1" if method == "cycle" else "I2"]}], "comparison": []})

    monkeypatch.setattr(analysis.repository, "call_digest_model", model)
    sections, missing = analysis.analyze({"team_a": "GEN", "team_b": "HLE", "event": "S16", "match_date": "2999-01-01"}, [])
    titles = [row["title"] for section in sections for row in section["items"]]
    assert any("周期" in title for title in titles)
    assert any("版本" in title for title in titles)
    assert all("主要矛盾" not in title for title in titles)
    assert missing and "主要矛盾" in missing[0]
