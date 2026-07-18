from __future__ import annotations

import os

import httpx
import yaml


SKILL_DIRS = (
    os.environ.get("XIAOXUE_SKILL_DIR_XIAOBAI", "/home/ubuntu/.hermes/profiles/xiaobai/skills"),
    os.environ.get("XIAOXUE_SKILL_DIR_MAIN", "/home/ubuntu/.hermes/skills"),
)


def load_runtime_config() -> dict:
    for path in (
        os.path.expanduser("~/.hermes/config.yaml"),
        "/home/ubuntu/.hermes/config.yaml",
        "/home/ubuntu/.hermes/profiles/xiaobai/config.yaml",
    ):
        try:
            with open(path, encoding="utf-8") as source:
                return yaml.safe_load(source) or {}
        except OSError:
            continue
    return {}


def read_skill(name: str) -> str:
    for base in SKILL_DIRS:
        try:
            with open(os.path.join(base, name, "SKILL.md"), encoding="utf-8") as source:
                return source.read()
        except OSError:
            continue
    return ""


def read_team_profile(team: str, limit: int = 3000) -> str:
    for base in SKILL_DIRS:
        try:
            with open(os.path.join(base, f"{team.lower()}-team-profile", "SKILL.md"), encoding="utf-8") as source:
                return source.read(limit)
        except OSError:
            continue
    return ""


async def call_llm(system_prompt: str, user_prompt: str) -> str:
    config = load_runtime_config()
    key = config.get("providers", {}).get("deepseek", {}).get("api_key", "")
    model = config.get("model", {}).get("default", "deepseek-v4-pro")
    if not key:
        return "LLM 配置不可用"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.7,
                "max_tokens": 1200,
            },
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
    if response.status_code != 200:
        return f"LLM 调用失败 (HTTP {response.status_code})"
    return response.json()["choices"][0]["message"]["content"]
