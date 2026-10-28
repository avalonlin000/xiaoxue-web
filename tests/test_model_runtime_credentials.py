"""Project tasks resolve their own credentials without a running chat host."""
import os
from unittest.mock import patch

import pytest

from xiaoxue_api.core import model_runtime


def test_project_credential_file_works_without_inherited_host_environment(tmp_path):
    credentials = tmp_path / "model.env"
    credentials.write_text(
        'TASK_KEY="private-file-value"\nUNRELATED_SECRET=keep-private\n', encoding="utf-8"
    )
    config = {"api_key_env": "TASK_KEY", "credential_env_file": str(credentials)}
    with patch.dict(os.environ, {}, clear=True):
        assert model_runtime.api_key(config) == "private-file-value"
        assert "TASK_KEY" not in os.environ
        assert "UNRELATED_SECRET" not in os.environ


def test_explicit_environment_overrides_project_credential_file(tmp_path):
    credentials = tmp_path / "model.env"
    credentials.write_text("TASK_KEY=file-value\n", encoding="utf-8")
    config = {"api_key_env": "TASK_KEY", "credential_env_file": str(credentials)}
    with patch.dict(os.environ, {"TASK_KEY": "explicit-value"}, clear=True):
        assert model_runtime.api_key(config) == "explicit-value"


def test_missing_project_credential_raises_safe_error_without_values(tmp_path):
    credentials = tmp_path / "model.env"
    credentials.write_text("UNRELATED_SECRET=never-expose-this\n", encoding="utf-8")
    config = {"api_key_env": "TASK_KEY", "credential_env_file": str(credentials)}
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(model_runtime.ModelRuntimeError, match="项目模型凭据未提供") as error:
            model_runtime.api_key(config)
    assert "never-expose-this" not in str(error.value)


def test_credential_values_are_not_interpolated_from_other_environment(tmp_path):
    credentials = tmp_path / "model.env"
    credentials.write_text("TASK_KEY='literal-${UNRELATED_SECRET}'\n", encoding="utf-8")
    config = {"api_key_env": "TASK_KEY", "credential_env_file": str(credentials)}
    with patch.dict(os.environ, {"UNRELATED_SECRET": "other-secret"}, clear=True):
        assert model_runtime.api_key(config) == "literal-${UNRELATED_SECRET}"
