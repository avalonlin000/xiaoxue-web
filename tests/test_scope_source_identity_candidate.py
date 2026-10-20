"""Offline real-shape regressions for the staged reader, never production code."""
import importlib.util
import json
from pathlib import Path

import pytest

STAGED = Path('/home/ubuntu/.hermes/team/deliveries/verified-changes/xiaoxue-prematch-reader-20261020/staged')


def load_candidate(name, path):
    spec = importlib.util.spec_from_file_location('xiaoxue_api.modules.current_event.' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(monkeypatch, tmp_path):
    repo = load_candidate('_identity_candidate_repo', STAGED / 'content-repository/collection_repository.py')
    analysis = load_candidate('_identity_candidate_analysis', STAGED / 'scope-analysis/analysis_repository.py')
    analysis.repository = repo
    monkeypatch.setenv('XIAOXUE_COLLECTION_DIR', str(tmp_path / 'materials'))
    for name in ('search', 'read_article', 'call_digest_model'):
        monkeypatch.setattr(repo, name, lambda *_a, **_kw: pytest.fail('No live calls in candidate tests'))
    return repo, analysis


def test_media_roster_stays_media_and_retains_source_identity(candidate, monkeypatch):
    repo, _ = candidate
    identity = {'scope': 'team', 'event': 'S16 世界赛', 'team': 'T1', 'reference_date': '2026-10-20'}
    quote = '| **T1** | LCK 2026, 3rd | Doran | Oner | Faker | Peyz | Keria |'
    source = {'title': 'Tips：S16各队名单', 'url': 'https://tips.gg/article/teams', 'text': quote, 'verification': 'source_text', 'source_category': 'author_analysis'}
    row = {'text': 'T1本届S16首发为Doran、Oner、Faker、Peyz、Keria。', 'why_relevant': '核对本届队伍阵容', 'relevance': 'useful_background', 'event_key': 't1-roster', 'evidence_quote': quote, 'source_ids': ['S1'], 'kind': 'reported_information'}
    packets = []
    def model(packet):
        packets.append(packet)
        return json.dumps({'items': [row]}, ensure_ascii=False)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    result, missing = repo.summarize_materials(identity, [{'id': 'news', 'items': [source]}])
    saved = result[0]['items'][0]
    assert not missing
    assert '媒体列举' in saved['text'] and '未获官方首发确认' in saved['text']
    assert '首发为' not in saved['text']
    assert saved['source_title'] == source['title'] and saved['url'] == source['url']
    assert saved['roster_status'] == 'media_reported_unconfirmed'
    assert packets[0]['subject'] == identity and packets[0]['sources'][0]['url'] == source['url']


@pytest.mark.parametrize('text,accepted', [
    ('当前材料真正能确认的是T1的S16首发与LCK三号种子身份。', False),
    ('T1本届首发为Doran、Oner、Faker、Peyz、Keria。', False),
    ('当前名单尚未确认，不能确认T1首发。', True),
    ('若确认T1维持该首发，则再检验中野主动性。', True),
])
def test_scope_does_not_promote_media_roster_to_confirmed(candidate, monkeypatch, text, accepted):
    repo, analysis = candidate
    identity = {'scope': 'team', 'event': 'S16 世界赛', 'team': 'T1'}
    section = {'id': 'digest', 'items': [{'text': '作者认为T1稳定性是问题。', 'evidence_quote': 'The talent is not the question. Consistency is.', 'kind': 'author_analysis', 'source_category': 'author_analysis', 'source_title': 'S16作者分析', 'url': 'https://tips.gg/article/teams', 'roster_status': 'media_reported_unconfirmed'}]}
    packets = []
    def model(packet):
        packets.append(packet)
        return json.dumps({'items': [{'method_id': 'version', 'text': text, 'basis': '媒体说法与旧版认识待核对。', 'confirmation': '若取得实际版本及名单确认再使用。', 'invalidation': '当前表现不支持则失效。', 'source_ids': ['I1']}]}, ensure_ascii=False)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    result, _ = analysis.analyze_scope(identity, [section])
    assert bool(result) is accepted
    item = packets[0]['inputs'][0]
    assert item['title'] == 'S16作者分析' and item['url'] == 'https://tips.gg/article/teams'
    assert item['subject'] == identity and item['source_category'] == 'author_analysis'
    assert item['roster_status'] == 'media_reported_unconfirmed'


def test_tactical_lineup_opinion_is_not_relabelled_as_a_player_list(candidate, monkeypatch):
    repo, _ = candidate
    quote = 'The roster remains extremely solid regardless.'
    source = {'title': 'S16作者判断', 'text': quote, 'verification': 'source_text', 'source_category': 'author_analysis'}
    item = {'text': '作者认为阵容依然扎实。', 'why_relevant': '说明本队上限', 'relevance': 'useful_background', 'event_key': 'strength', 'source_ids': ['S1'], 'evidence_quote': quote}
    monkeypatch.setattr(repo, 'call_digest_model', lambda _: json.dumps({'items': [item]}, ensure_ascii=False))
    result, _ = repo.summarize_materials({'scope': 'team', 'event': 'S16', 'team': 'BLG'}, [{'id': 'news', 'items': [source]}])
    assert result[0]['items'][0]['text'] == item['text']
