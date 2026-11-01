"""新球队自动中文化。

规则：队名先查人工对照表（config/football_teams_zh.json）；没有命中时，用配置的
翻译模型把英文队名翻成中文常用名，结果永久写入 data/football/team_names_auto.json。
翻译一次即长期生效，不需要人工补表；模型不可用时保留英文原名，下次刷新自动重试。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = ROOT / "config" / "football.json"
CACHE_PATH = ROOT / "data" / "football" / "team_names_auto.json"
RETRY_HOURS = 12
SUFFIXES = ("足球俱乐部", "足球会", "体育俱乐部", "俱乐部", "足球隊", "足球隊")
CJK = re.compile(r"[\u4e00-\u9fff]")

_lock = threading.Lock()
_memory: dict[str, dict] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict[str, dict]:
    global _memory
    if _memory is not None:
        return _memory
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        _memory = payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        _memory = {}
    return _memory


def _save() -> None:
    if _memory is None:
        return
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(_memory, ensure_ascii=False, indent=0), encoding="utf-8")
        temporary.replace(CACHE_PATH)
    except OSError:
        pass


def _translator_config() -> dict:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    translator = config.get("translator") or {}
    if not translator.get("enabled"):
        return {}
    return translator


def _api_key(translator: dict) -> str:
    env_name = translator.get("api_key_env") or ""
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    env_file = translator.get("env_file") or ""
    if env_name and env_file:
        try:
            for line in Path(env_file).read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{env_name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            return ""
    return ""


def _clean(value: str) -> str:
    text = str(value or "").strip().strip("。.")
    for suffix in SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    return text.strip()


def _valid(value: str) -> bool:
    text = str(value or "")
    return len(CJK.findall(text)) >= 2 and len(text) <= 16 and not re.search(r"[A-Za-z]{5,}", text)


def cached(name: str) -> str | None:
    entry = _load().get(name)
    if not entry:
        return None
    return entry.get("zh") if entry.get("zh") else None


def _should_try(name: str) -> bool:
    entry = _load().get(name)
    if not entry:
        return True
    if entry.get("zh"):
        return False
    attempted = entry.get("failed_at")
    if not attempted:
        return True
    try:
        return _now() - datetime.fromisoformat(attempted) > timedelta(hours=RETRY_HOURS)
    except ValueError:
        return True


def _ask_model(names: list[str], translator: dict) -> dict[str, str]:
    key = _api_key(translator)
    base = (translator.get("base_url") or "").rstrip("/")
    model = translator.get("model") or ""
    if not key or not base or not model or not names:
        return {}
    prompt = (
        "把下面这些足球俱乐部的英文队名翻译成中文常用队名。只输出 JSON 数组，"
        '每项形如 {"en": "原始英文名", "zh": "中文队名"}，en 必须与给定英文名完全一致；'
        "中文名不带“足球俱乐部”这类后缀；不要解释、不要 Markdown。\n"
        + "\n".join(f"- {name}" for name in names)
    )
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "xiaoxue-football/0.1",
            "x-opencode-session": "xiaoxue-football-names",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except Exception:
        return {}
    result: dict[str, str] = {}
    pairs = re.findall(r'\{[^{}]*\}', content)
    for chunk in pairs:
        try:
            item = json.loads(chunk)
        except ValueError:
            continue
        english = str(item.get("en") or item.get("name") or "").strip()
        chinese = item.get("zh") or item.get("chinese") or item.get("中文") or ""
        if english in names and isinstance(chinese, str):
            cleaned = _clean(chinese)
            if _valid(cleaned):
                result[english] = cleaned
    if not result:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                raw = json.loads(match.group(0))
            except ValueError:
                raw = {}
            if isinstance(raw, dict) and len(names) == 1:
                for value in raw.values():
                    if isinstance(value, str) and _valid(_clean(value)):
                        result[names[0]] = _clean(value)
                        break
    return result


def resolve(names: list[str]) -> dict[str, str]:
    """把还没中文名的球队补齐，返回本次新得到的映射。"""
    pending = sorted({name.strip() for name in names if name and name.strip() and _should_try(name.strip())})
    translator = _translator_config()
    if not pending or not translator:
        return {}
    batch = int(translator.get("batch") or 40)
    gained: dict[str, str] = {}
    for start in range(0, len(pending), batch):
        chunk = pending[start:start + batch]
        answered = _ask_model(chunk, translator)
        stamp = _now().isoformat()
        with _lock:
            cache = _load()
            for name in chunk:
                if name in answered:
                    cache[name] = {"zh": answered[name], "source": "model", "at": stamp}
                    gained[name] = answered[name]
                else:
                    cache[name] = {**cache.get(name, {}), "failed_at": stamp}
            _save()
    return gained
