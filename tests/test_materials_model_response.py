"""The formatter may unwrap a JSON fence, never repair or invent model content."""
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def adapter():
    path = Path(os.environ.get("XIAOXUE_MATERIALS_MODEL_SCRIPT", str(Path(__file__).parents[1] / "scripts/summarize_match_materials.py")))
    spec = importlib.util.spec_from_file_location("materials_model_response_candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("text", ['{"items":[]}', '\ufeff  {"items":[]}  ', '```json\n{"items":[]}\n```', '```\n{"items":[]}\n```'])
def test_only_complete_json_object_or_its_outer_fence_is_accepted(adapter, text):
    assert adapter.parse_model_json(text) == {"items": []}


@pytest.mark.parametrize("text", ['', '```json\n{"items":[', 'Explanation: {"items":[]}', '{"items":[]} extra', '[]', 'null'])
def test_empty_truncated_or_extra_model_output_is_not_fabricated(adapter, text):
    with pytest.raises(ValueError):
        adapter.parse_model_json(text)


def test_scope_screening_does_not_require_an_opponent_or_drop_counterevidence(adapter):
    prompt = adapter.select_prompt({"subject": {"scope": "team", "event": "S16", "team": "TLAW"}})
    assert "subject.scope" in prompt
    assert "不要求对手" in prompt
    assert "关键反证" in prompt
    assert "媒体列举" in prompt
