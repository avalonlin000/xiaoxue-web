from __future__ import annotations

from workflow_contracts import prepare_lineup_workflow

from .repository import load_config


class ConfigurationUnavailable(RuntimeError):
    pass


def prepare(payload: dict) -> dict:
    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        raise ConfigurationUnavailable(f"阵容交接模块配置不可用：{exc}") from exc
    return prepare_lineup_workflow(payload, config)
