"""Project-owned model runtime configuration and OpenAI-compatible client factory."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "model-runtime.json"


class ModelRuntimeError(RuntimeError):
    """A safe configuration error that never contains credentials."""


def config_path() -> Path:
    return Path(os.environ.get("XIAOXUE_MODEL_RUNTIME", DEFAULT_CONFIG_PATH))


def load_config() -> dict[str, Any]:
    path = config_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelRuntimeError("项目模型配置不可用") from exc
    if not isinstance(value, dict) or value.get("api_mode") != "chat_completions":
        raise ModelRuntimeError("项目模型配置只支持 chat_completions")
    for key in ("provider", "model", "base_url", "api_key_env"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ModelRuntimeError(f"项目模型配置缺少 {key}")
    return value


def api_key(config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    key = str(config["api_key_env"])
    value = os.environ.get(key, "").strip()
    if not value and config.get("credential_env_file"):
        from dotenv import dotenv_values

        try:
            values = dotenv_values(
                Path(config["credential_env_file"]).expanduser(), interpolate=False
            )
            value = str(values.get(key) or "").strip()
        except (OSError, ValueError):
            raise ModelRuntimeError("项目模型凭据文件不可用") from None
    if not value:
        raise ModelRuntimeError("项目模型凭据未提供")
    return value


def client_options(config: dict[str, Any] | None = None) -> dict[str, Any]:
    value = config or load_config()
    headers = dict(value.get("headers") or {})
    # OpenCode Go rejects requests without this affinity header. Project tasks are
    # one-shot calls, so a process-local opaque value is sufficient and does not
    # couple them to a chat or Hermes conversation.
    headers.setdefault("x-opencode-session", f"xiaoxue-{uuid.uuid4().hex}")
    return {
        "api_key": api_key(value),
        "base_url": value["base_url"],
        "default_headers": headers,
        "timeout": float(value.get("timeout_seconds", 95)),
        "max_retries": 0,
    }


def request_options(config: dict[str, Any] | None = None) -> dict[str, Any]:
    value = config or load_config()
    effort = value.get("reasoning_wire_effort") or value.get("reasoning_effort")
    options: dict[str, Any] = {
        "model": value["model"],
        "max_tokens": int(value.get("max_tokens", 16384)),
        "stream": True,
    }
    if effort and str(effort).lower() not in {"none", "off", "disabled"}:
        options["reasoning_effort"] = str(effort)
    extra_body = value.get("extra_body")
    if isinstance(extra_body, dict) and extra_body:
        options["extra_body"] = dict(extra_body)
    return options


def public_identity() -> dict[str, Any]:
    value = load_config()
    return {key: value.get(key) for key in ("provider", "model", "api_mode", "base_url", "max_tokens")}
