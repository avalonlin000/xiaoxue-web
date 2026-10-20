"""The event reader retains full source evidence and resumes failed batches only."""
import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def candidate(monkeypatch, tmp_path):
    base = Path(os.environ.get('XIAOXUE_EVENT_CANDIDATE_DIR', Path(__file__).parents[1]))
    paths = ((base / 'content-repository/collection_repository.py',
              base / 'collection/collection.py' if (base / 'collection/collection.py').is_file() else
              Path(__file__).parents[1] / 'xiaoxue_api/modules/current_event/collection.py')
             if (base / 'content-repository').is_dir() else
             (base / 'xiaoxue_api/modules/current_event/collection_repository.py', base / 'xiaoxue_api/modules/current_event/collection.py'))
    modules = []
    for name, path in zip(('_event_batch_repo', '_event_batch_collection'), paths):
        spec = importlib.util.spec_from_file_location('xiaoxue_api.modules.current_event.' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    repo, collector = modules
    collector.repository = repo
    monkeypatch.setenv('XIAOXUE_COLLECTION_DIR', str(tmp_path / 'materials'))
    for name in ('search', 'read_article', 'call_digest_model'):
        monkeypatch.setattr(repo, name, lambda *_a, **_kw: pytest.fail('No network or model calls in unit tests'))
    return repo, collector


SUBJECT = {'scope': 'event', 'event': 'S16 世界赛', 'reference_date': '2026-10-20'}


def sources(count=6, length=1000):
    return [{'id': 'news', 'items': [
        {'title': f'Article {n}', 'url': f'https://example.org/article-{n}', 'source_id': f'body-{n}',
         'verification': 'source_text', 'source_category': 'author_analysis',
         'text': f'Article {n} has real tactical evidence and its limiting conditions. ' + 'a' * length}
        for n in range(count)]}]


def selected(packet, *, key=None):
    return json.dumps({'items': [
        {'text': row['title'] + '：作者认为打法的成立取决于执行条件。', 'why_relevant': '说明本届赛事的分析条件',
         'relevance': 'useful_background', 'event_key': key or row['title'], 'source_ids': [row['id']],
         'evidence_quote': row['text'][:65], 'kind': 'author_analysis'} for row in packet['sources']
    ]}, ensure_ascii=False)


def test_event_screens_at_most_two_full_sources_per_call(candidate, monkeypatch):
    repo, _ = candidate
    packets = []
    def model(packet):
        packets.append(packet)
        assert len(packet['sources']) <= 2
        assert all(len(row['text']) <= 1600 for row in packet['sources'])
        return selected(packet)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    original = sources(length=7500)
    sections, missing = repo.summarize_materials(SUBJECT, original)
    assert not missing and len(packets) == 15
    for source in original[0]['items']:
        spans = [row['text'] for packet in packets for row in packet['sources'] if row['title'] == source['title']]
        assert ''.join(spans) == source['text']
    assert len(sections[0]['items']) == 6
    assert {row['source_id'] for row in sections[0]['items']} == {f'body-{n}' for n in range(6)}


def test_partial_batches_are_readable_but_retryable_and_successes_are_reused(candidate, monkeypatch):
    repo, collector = candidate
    calls = []
    fail = True
    def model(packet):
        nonlocal fail
        title = packet['sources'][0]['title']
        calls.append(title)
        if fail and title == 'Article 2':
            raise ValueError('empty_response')
        return selected(packet)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert len(sections[0]['items']) == 4 and missing
    assert sections[0]['incomplete'] is True
    assert collector._stage_result(sections, missing)['failed'] is True
    fail = False
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert not missing and not sections[0].get('incomplete')
    assert len(sections[0]['items']) == 6
    assert calls == ['Article 0', 'Article 2', 'Article 4', 'Article 2']


def test_changed_source_only_recomputes_its_batch(candidate, monkeypatch):
    repo, _ = candidate
    calls = []
    def model(packet):
        calls.append(packet['sources'][0]['title'])
        return selected(packet)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    rows = sources()
    repo.summarize_materials(SUBJECT, rows)
    rows[0]['items'][2]['text'] += ' Changed condition.'
    repo.summarize_materials(SUBJECT, rows)
    assert calls == ['Article 0', 'Article 2', 'Article 4', 'Article 2']


def test_same_event_is_merged_across_batches(candidate, monkeypatch):
    repo, _ = candidate
    monkeypatch.setattr(repo, 'call_digest_model', lambda packet: selected(packet, key='same-event'))
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert not missing and len(sections[0]['items']) == 1


def test_all_failed_batches_do_not_claim_screened_empty(candidate, monkeypatch):
    repo, _ = candidate
    monkeypatch.setattr(repo, 'call_digest_model', lambda _: (_ for _ in ()).throw(ValueError('empty_response')))
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert sections == [] and missing


def test_legitimate_empty_batches_are_cached_without_retry(candidate, monkeypatch):
    repo, collector = candidate
    calls = []
    def model(packet):
        calls.append(packet)
        return '{"items":[]}'
    monkeypatch.setattr(repo, 'call_digest_model', model)
    repo.summarize_materials(SUBJECT, sources())
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert len(calls) == 3 and not missing
    assert sections[0]['selection_status'] == 'screened' and not sections[0]['items']
    assert collector._stage_result(sections, missing)['failed'] is False


def test_team_reading_keeps_existing_single_call(candidate, monkeypatch):
    repo, _ = candidate
    calls = []
    monkeypatch.setattr(repo, 'call_digest_model', lambda packet: (calls.append(packet) or selected(packet)))
    repo.summarize_materials({**SUBJECT, 'scope': 'team', 'team': 'BLG'}, sources())
    assert len(calls) == 1


def test_low_remaining_budget_returns_cached_evidence_without_another_model(candidate, monkeypatch):
    repo, collector = candidate
    def model(packet):
        if packet['sources'][0]['title'] == 'Article 2':
            raise ValueError('empty response')
        return selected(packet)
    monkeypatch.setattr(repo, 'call_digest_model', model)
    repo.summarize_materials(SUBJECT, sources())
    monkeypatch.setattr(repo, 'remaining_timeout', lambda _: 100)
    monkeypatch.setattr(repo, 'call_digest_model', lambda _: pytest.fail('Reserve budget for publishing and interpretation'))
    sections, missing = repo.summarize_materials(SUBJECT, sources())
    assert len(sections[0]['items']) == 4 and missing
    assert sections[0]['incomplete'] is True
    assert collector._stage_result(sections, missing)['failed'] is True
