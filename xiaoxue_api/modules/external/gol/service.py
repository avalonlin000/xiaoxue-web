from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE_URL = "https://gol.gg"
USER_AGENT = "Xiaoxue/1.0 (+https://gol.gg)"
# gol.gg 的大页面（赛事统计页可达 500KB+）在长连接下不会主动断开，读满即挂到超时。
# 用 Connection: close + 更大超时 + 读上限，保证能拿到正文而不是空响应。
TIMEOUT_SECONDS = 45
MAX_RESPONSE_BYTES = 4_000_000
MAX_SERIES_GAMES = 5


class GolUnavailable(RuntimeError):
    pass


class GolInputError(ValueError):
    pass


def _url(path: str) -> str:
    return urljoin(f"{BASE_URL}/", path.lstrip("/"))


def _fetch(path: str) -> tuple[str, str]:
    url = _url(path)
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Encoding": "identity", "Connection": "close"})
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.geturl().split("/", 3)[:3] != ["https:", "", "gol.gg"]:
                raise GolUnavailable("Gol.gg 请求发生非预期跳转")
            return response.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace"), response.geturl()
    except GolUnavailable:
        raise
    except Exception as exc:
        raise GolUnavailable("Gol.gg 暂时不可访问或响应过慢") from exc


def _soup(path: str) -> tuple[BeautifulSoup, str]:
    content, source_url = _fetch(path)
    return BeautifulSoup(content, "lxml"), source_url


def _clean(value: Any, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _game_id(value: int | str) -> int:
    try:
        game_id = int(value)
    except (TypeError, ValueError) as exc:
        raise GolInputError("Gol.gg 对局编号必须是正整数") from exc
    if game_id < 1:
        raise GolInputError("Gol.gg 对局编号必须是正整数")
    return game_id


def _game_path(game_id: int) -> str:
    return f"/game/stats/{game_id}/page-game/"


def _link_game_id(href: str) -> int | None:
    match = re.search(r"/game/stats/(\d+)/page-game/", href or "")
    return int(match.group(1)) if match else None


def _champions(row) -> list[str]:
    ignored = {"First Pick"}
    return [
        image.get("alt", "").strip() for image in row.select("img[alt]")
        if image.get("alt", "").strip() and image.get("alt", "").strip() not in ignored
    ]


def _team_game_facts(card) -> dict[str, Any]:
    header = card.select_one(".blue-line-header, .red-line-header")
    heading = _clean(header.get_text(" ", strip=True) if header else "")
    match = re.match(r"(.+?)\s*-\s*(WIN|LOSS)\s*$", heading, re.I)
    team = _clean(match.group(1) if match else heading)
    result = (match.group(2).upper() if match else "")
    stats = {}
    for box in card.select(".score-box"):
        label = _clean(box.select_one("img").get("alt", "") if box.select_one("img") else "")
        value = _clean(box.get_text(" ", strip=True)).replace(label, "").strip()
        if label and value:
            stats[label.lower()] = value
    rows = card.select(".row")
    bans, picks = [], []
    for row in rows:
        label = _clean(row.select_one(".col-2").get_text(" ", strip=True) if row.select_one(".col-2") else "").lower()
        if label == "bans":
            bans = _champions(row)
        elif label == "picks":
            picks = _champions(row)
    return {
        "team": team,
        "result": result,
        "stats": stats,
        "bans": bans,
        "picks": picks,
    }


def game_facts(game_id: int | str) -> dict[str, Any]:
    game_id = _game_id(game_id)
    soup, source_url = _soup(_game_path(game_id))
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    time_node = soup.find(string=lambda text: _clean(text) == "Game Time")
    frame = time_node.find_parent("div", class_="col-cadre") if time_node else None
    if not frame:
        raise GolUnavailable("Gol.gg 页面缺少可识别的逐局事实")
    time_row = time_node.find_parent("div", class_="rowbreak")
    duration = _clean(time_row.select_one("h1").get_text(" ", strip=True) if time_row and time_row.select_one("h1") else "")
    patch_text = _clean(time_row.get_text(" ", strip=True) if time_row else "")
    patch = next(iter(re.findall(r"v?(\d+\.\d+(?:\.\d+)?)", patch_text)), "")
    cards = frame.select(":scope > .row.rowbreak > .col-12.col-sm-6")
    teams = [_team_game_facts(card) for card in cards[:2]]
    siblings: list[dict[str, Any]] = []
    seen: set[int] = set()
    for link in soup.select("a[href*='/game/stats/']"):
        sibling = _link_game_id(link.get("href", ""))
        label = _clean(link.get_text(" ", strip=True))
        if sibling and sibling not in seen and label.lower().startswith("game"):
            seen.add(sibling)
            siblings.append({"game_id": sibling, "label": label, "url": _url(link["href"])})
    return {
        "game_id": game_id,
        "title": title,
        "duration": duration,
        "patch": patch,
        "teams": teams,
        "series_games": siblings[:MAX_SERIES_GAMES],
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def series_facts(game_id: int | str) -> dict[str, Any]:
    first = game_facts(game_id)
    series_ids = [item["game_id"] for item in first["series_games"]] or [first["game_id"]]
    games = [first]
    for sibling in series_ids:
        if sibling == first["game_id"]:
            continue
        try:
            games.append(game_facts(sibling))
        except GolUnavailable:
            continue
    games.sort(key=lambda item: series_ids.index(item["game_id"]) if item["game_id"] in series_ids else 99)
    return {
        "series": {
            "title": re.sub(r"\s+game\s+\d+.*$", "", first["title"], flags=re.I),
            "game_count_available": len(games),
            "requested_game_id": first["game_id"],
        },
        "games": games,
        "source_url": first["source_url"],
        "retrieved_at": first["retrieved_at"],
        "boundary": "仅返回 Gol.gg 已展示的逐局事实；不推断队伍能力、调整能力或交易结论。",
    }


def tournament_facts(tournament: str) -> dict[str, Any]:
    name = _clean(tournament, 120)
    if not name:
        raise GolInputError("需要明确赛事名称")
    soup, source_url = _soup(f"/tournament/tournament-stats/{quote(name)}/")
    heading = _clean(soup.select_one("h1").get_text(" ", strip=True) if soup.select_one("h1") else "")
    page_text = _clean(soup.get_text(" ", strip=True), 16000)
    def after(label: str) -> str:
        match = re.search(rf"{re.escape(label)}\s*:\s*([^|]+?)(?=\s+[A-Z][A-Za-z /]+:|$)", page_text)
        return _clean(match.group(1) if match else "")
    games: list[dict[str, Any]] = []
    seen: set[int] = set()
    for link in soup.select("a[href*='/game/stats/']"):
        item_id = _link_game_id(link.get("href", ""))
        if item_id and item_id not in seen:
            seen.add(item_id)
            games.append({"game_id": item_id, "label": _clean(link.get_text(" ", strip=True)), "url": _url(link["href"])})
    return {
        "tournament": heading or name,
        "draft_mode": after("Draft mode"),
        "number_of_games": after("Number of games"),
        "average_game_duration": after("Average game duration"),
        "sample_games": games[:30],
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "boundary": "仅返回赛事页面可读事实；跨版本、跨赛事结论需另行限定范围。",
    }



def tournament_bp_facts(tournament: str, limit: int = 20) -> dict[str, Any]:
    name = _clean(tournament, 120)
    if not name:
        raise GolInputError("需要明确赛事名称")
    bounded = max(1, min(int(limit or 20), 50))
    soup, source_url = _soup(f"/tournament/tournament-picksandbans/{quote(name)}/")
    facts: dict[str, list[dict[str, Any]]] = {"bans": [], "picks": []}
    roles = {"top", "jungle", "mid", "bot", "support"}
    for row in soup.select("table tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label = _clean(cells[0].get_text(" ", strip=True)).lower()
        bucket = "bans" if label.startswith("bans") else "picks" if label in roles else ""
        if not bucket:
            continue
        entries = cells[1].select("span") if bucket == "bans" else cells[1].find_all("div", recursive=False)
        for entry in entries:
            image = entry.select_one("img[alt]")
            champion = _clean(image.get("alt", "") if image else "")
            count = next(iter(re.findall(r"\b\d+\b", _clean(entry.get_text(" ", strip=True)))), "")
            if champion and count:
                item = {"champion": champion, "count": int(count)}
                if bucket == "picks":
                    item["role"] = label.upper()
                facts[bucket].append(item)
    return {
        "tournament": name,
        "bans": facts["bans"][:bounded],
        "picks": facts["picks"][:bounded],
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "boundary": "仅返回该赛事页面展示的 BP 次数，不跨赛事聚合，也不自动形成英雄优先级结论。",
    }


def tournament_entities(tournament: str, kind: str = "all", query_text: str = "", limit: int = 20) -> dict[str, Any]:
    name = _clean(tournament, 120)
    target = _clean(query_text, 100).casefold()
    normalized_kind = _clean(kind, 20).lower() or "all"
    if normalized_kind not in {"all", "team", "player"}:
        raise GolInputError("对象类型只支持 team、player 或 all")
    if not name:
        raise GolInputError("需要明确赛事名称")
    soup, source_url = _soup(f"/tournament/tournament-stats/{quote(name)}/")
    patterns = {
        "player": r"/players/player-stats/(\d+)/",
        "team": r"/teams/team-stats/(\d+)/",
    }
    items = []
    seen: set[tuple[str, int]] = set()
    for item_kind, pattern in patterns.items():
        if normalized_kind not in {"all", item_kind}:
            continue
        for link in soup.select("a[href]"):
            match = re.search(pattern, str(link.get("href") or ""))
            label = _clean(link.get_text(" ", strip=True))
            alias = "".join(part[0] for part in re.findall(r"[A-Za-z]+", label)).casefold()
            aliases = {"bilibili gaming": "blg", "top esports": "tes", "jd gaming": "jdg", "weibo gaming": "wbg", "invictus gaming": "ig"}
            aliases_match = aliases.get(label.casefold(), "")
            if not match or not label or (target and target not in label.casefold() and target not in {alias, aliases_match}):
                continue
            key = (item_kind, int(match.group(1)))
            if key in seen:
                continue
            seen.add(key)
            items.append({"kind": item_kind, "id": key[1], "name": label, "url": _url(str(link["href"]))})
    return {"tournament": name, "kind": normalized_kind, "query": query_text, "items": items[:max(1, min(int(limit or 20), 50))], "source_url": source_url}


def team_tournament_facts(team_id: int | str, tournament: str) -> dict[str, Any]:
    try:
        team = int(team_id)
    except (TypeError, ValueError) as exc:
        raise GolInputError("Gol.gg 队伍编号必须是正整数") from exc
    if team < 1:
        raise GolInputError("Gol.gg 队伍编号必须是正整数")
    name = _clean(tournament, 120)
    if not name:
        raise GolInputError("需要明确赛事名称")
    soup, source_url = _soup(f"/teams/team-stats/{team}/split-ALL/tournament-{quote(name)}/")
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    general = next((table for table in soup.select("table") if "Win Rate" in table.get_text(" ", strip=True)), None)
    if not general:
        raise GolUnavailable("Gol.gg 页面缺少可识别的队伍赛事统计")
    text = _clean(general.get_text(" ", strip=True), 3000)
    record = re.search(r"Win Rate\s*:\s*(.+?)(?=\s+Average game duration\s*:|$)", text)
    duration = re.search(r"Average game duration\s*:\s*(.+)$", text)
    return {"team_id": team, "title": title, "tournament": name, "stats": {"win_rate_record": _clean(record.group(1) if record else ""), "average_game_duration": _clean(duration.group(1) if duration else "")}, "source_url": source_url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "boundary": "仅返回该队在指定赛事页面展示的事实，不自动更新队伍画像。"}


def player_tournament_facts(player_id: int | str, tournament: str) -> dict[str, Any]:
    try:
        player = int(player_id)
    except (TypeError, ValueError) as exc:
        raise GolInputError("Gol.gg 选手编号必须是正整数") from exc
    if player < 1:
        raise GolInputError("Gol.gg 选手编号必须是正整数")
    name = _clean(tournament, 120)
    if not name:
        raise GolInputError("需要明确赛事名称")
    path = f"/players/player-stats/{player}/season-ALL/split-ALL/tournament-{quote(name)}/champion-ALL/"
    soup, source_url = _soup(path)
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    general = next((table for table in soup.select("table") if "General stats" in table.get_text(" ", strip=True)), None)
    if not general:
        raise GolUnavailable("Gol.gg 页面缺少可识别的选手赛事统计")
    text = _clean(general.get_text(" ", strip=True), 3000)
    fields = {}
    for label in ("Record", "Win Rate", "KDA", "CS per Minute", "Gold Per Minute", "Gold%", "Kill Participation"):
        match = re.search(rf"{re.escape(label)}\s*:\s*([^:]+?)(?=\s+(?:Record|Win Rate|KDA|CS per Minute|Gold Per Minute|Gold%|Kill Participation)\s*:|$)", text)
        if match:
            fields[label] = _clean(match.group(1))
    return {
        "player_id": player, "title": title, "tournament": name, "stats": fields,
        "source_url": source_url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "boundary": "仅返回该选手在指定赛事页面展示的事实，不自动形成选手画像。",
    }


def query(kind: str, *, tournament: str = "", game_id: int | str | None = None) -> dict[str, Any]:
    normalized = _clean(kind, 32).lower()
    if normalized in {"series", "series_facts", "game"}:
        if game_id is None:
            raise GolInputError("查系列赛逐局事实需要 Gol.gg 对局编号")
        return series_facts(game_id)
    if normalized in {"tournament", "tournament_facts"}:
        return tournament_facts(tournament)
    if normalized in {"bp", "tournament_bp", "picks_bans"}:
        return tournament_bp_facts(tournament)
    raise GolInputError("查询类型仅支持 series、tournament 或 bp；选手事实需先由赛事页定位具体对象")
