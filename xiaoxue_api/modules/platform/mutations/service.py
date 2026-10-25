from __future__ import annotations

from datetime import datetime
import hashlib
import re

from xiaoxue_api.core.database import connect
from xiaoxue_api.modules.team.public import get_full_profile, wiki_team_path
from xiaoxue_api.modules.team.public import TeamNotFound, get_team_id, get_team_profile, update_team_profile


class MutationRejected(ValueError):
    pass


HIGH_RISK = {
    "clear_all", "clear_table", "delete_all", "bulk_delete", "bulk_overwrite",
    "merge", "migrate", "replace_source", "permission", "secret", "publish", "auto_trade",
}


def _target(value: str) -> str:
    value = str(value or '').strip()
    if not value or len(value) > 80:
        raise MutationRejected('业务变更目标不能为空或过长')
    return value


def _write_wiki_team(team: str, content: str) -> dict:
    # 已废弃（2026-09-03）：队伍画像唯一正源是 DB team_profiles；
    # Wiki 实体画像/队伍 已整体移除，禁止再往 Wiki 写第二套画像。
    raise MutationRejected('队伍画像正源是数据库 team_profiles，Wiki 队伍画像已废弃，不再支持写入')


ROLE_DEFAULTS = ('上单', '打野', '中单', 'ADC', '辅助')
POSITION_DEFAULTS = ('TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT')
POSITION_ALIASES = {'ADC': 'BOT', 'AD': 'BOT', 'SUP': 'SUPPORT'}


def _stamp_source(kind: str, ref: str, retrieved_at: str) -> tuple:
    """外部事实必须留痕：来源类型、来源地址、取得时间；未人工核实一律留空。"""
    return (kind, ref, retrieved_at, '')


def _write_team_intake(team: str, changes: dict) -> dict:
    """外部事实入库：补队伍身份与首发，只在缺失处写入，不覆盖已有事实。

    适用 PRD 的补缺口要求：库外队伍（如世界赛的 C9、FUR、MVKE）先有身份和首发，
    覆盖面才会从"库内没有这支队"变成可判断的状态。写入必须带来源，绝不凭空造。
    """
    source = dict(changes.get('source') or {})
    kind = str(source.get('kind') or '').strip() or 'unspecified'
    ref = str(source.get('ref') or '').strip()
    if not ref:
        raise MutationRejected('外部事实入库必须带来源（source.ref），不允许无来源写入')
    retrieved_at = str(source.get('retrieved_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')).strip()
    players = changes.get('players') or []
    if not isinstance(players, list):
        raise MutationRejected('players 必须是名单数组')

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM teams WHERE UPPER(short_name)=? OR UPPER(name)=? OR UPPER(team_id)=?",
            (team.upper(), team.upper(), team.upper()),
        ).fetchone()
        filled: list[str] = []
        if existing is None:
            region = str(changes.get('region') or 'INTL').strip() or 'INTL'
            name = str(changes.get('name') or team).strip() or team
            league_id = str(changes.get('league_id') or '').strip()
            new_id = f"{region}-{re.sub(r'[^A-Za-z0-9]+', '', team.upper())}"
            clash = conn.execute("SELECT team_id FROM teams WHERE team_id=?", (new_id,)).fetchone()
            if clash:
                region = f"{region}-{datetime.now().strftime('%Y%m%d')}"
                new_id = f"{region}-{re.sub(r'[^A-Za-z0-9]+', '', team.upper())}"
            stamp = _stamp_source(kind, ref, retrieved_at)
            conn.execute(
                """INSERT INTO teams
                   (team_id, name, short_name, region, league_id, status,
                    source_kind, source_ref, source_updated_at, verified_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)""",
                (new_id, name, team.upper(), region, league_id, *stamp,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            )
            created = True
        else:
            new_id = existing['team_id']
            updates = {}
            for field in ('name', 'region', 'league_id'):
                value = str(changes.get(field) or '').strip()
                if value and not str(existing[field] or '').strip():
                    updates[field] = value
                    filled.append(field)
            base = (
                "UPDATE teams SET source_kind=?, source_ref=?, source_updated_at=?, verified_at=? "
                "WHERE team_id=?"
            )
            conn.execute(base, (*_stamp_source(kind, ref, retrieved_at), new_id))
            if updates:
                sets = ', '.join(f"{field}=?" for field in updates)
                conn.execute(f"UPDATE teams SET {sets} WHERE team_id=?", (*updates.values(), new_id))
            created = False

        readback = dict(conn.execute("SELECT * FROM teams WHERE team_id=?", (new_id,)).fetchone())

    written_players: list[dict] = []
    if players:
        # 首发沿用既有正源写入路径，再单独盖来源章，避免与既有写入逻辑分叉。
        written_players = _write_roster(team, players)['starters']
        with connect() as conn:
            conn.execute(
                """UPDATE rosters SET source_kind=?, source_ref=?, source_updated_at=?, verified_at=?
                   WHERE team_id=? AND status='active'""",
                (*_stamp_source(kind, ref, retrieved_at), new_id),
            )
    return {
        'ok': True,
        'team': team.upper(),
        'team_id': new_id,
        'created': created,
        'filled_fields': filled,
        'starters': written_players,
        'source': {'kind': kind, 'ref': ref, 'retrieved_at': retrieved_at, 'verified_at': ''},
        'readback': {key: readback.get(key) for key in ('team_id', 'name', 'short_name', 'region', 'league_id', 'source_kind', 'source_ref', 'source_updated_at', 'verified_at')},
    }


def _roster_spec(item, index: int) -> dict:
    if isinstance(item, dict):
        name = str(item.get('name') or item.get('player_name') or '').strip()
        spec = dict(item)
    else:
        name = str(item or '').strip()
        spec = {}
    if not name:
        raise MutationRejected('首发/人员名单中存在空名字')
    spec['name'] = name
    spec['role'] = str(spec.get('role') or (ROLE_DEFAULTS[index] if index < 5 else '')).strip()
    position = str(spec.get('position') or (POSITION_DEFAULTS[index] if index < 5 else '')).strip().upper()
    spec['position'] = POSITION_ALIASES.get(position, position)
    if spec['position'] not in POSITION_DEFAULTS:
        raise MutationRejected('首发位置只允许 TOP/JUNGLE/MID/BOT/SUPPORT')
    return spec


PRICE_COLUMNS = """
CREATE TABLE IF NOT EXISTS lol_price_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_key TEXT NOT NULL DEFAULT '',
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'win',
    price_a TEXT NOT NULL DEFAULT '',
    price_b TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT '',
    source_ref TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    verified_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_lol_price_facts_pair ON lol_price_facts(team_a, team_b, recorded_at);
"""


def _write_price_fact(changes: dict) -> dict:
    """外部价格留存：只记录带来源的报价事实，不产生方向判断。

    价格是事实，判断仍以 category=market 的交易 TK 为正源；本表只回答"谁在什么时候报了多少钱"。
    """
    team_a = str(changes.get('team_a') or '').strip()
    team_b = str(changes.get('team_b') or '').strip()
    if not team_a or not team_b:
        raise MutationRejected('价格入库需要明确双方队伍')
    price_a = str(changes.get('price_a') or '').strip()
    price_b = str(changes.get('price_b') or '').strip()
    if not price_a and not price_b:
        raise MutationRejected('价格入库至少需要一个报价')
    source = dict(changes.get('source') or {})
    ref = str(source.get('ref') or '').strip()
    if not ref:
        raise MutationRejected('外部价格必须带来源（source.ref），不允许无来源写入')
    recorded_at = str(source.get('recorded_at') or source.get('retrieved_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')).strip()
    with connect() as conn:
        conn.executescript(PRICE_COLUMNS)
        conn.execute(
            """INSERT INTO lol_price_facts
               (match_key, team_a, team_b, market, price_a, price_b, source_kind, source_ref, recorded_at, verified_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '')""",
            (str(changes.get('match_key') or '').strip(), team_a.upper(), team_b.upper(),
             str(changes.get('market') or 'win').strip() or 'win', price_a, price_b,
             str(source.get('kind') or 'unspecified').strip() or 'unspecified', ref, recorded_at),
        )
        row = dict(conn.execute(
            "SELECT * FROM lol_price_facts WHERE team_a=? AND team_b=? ORDER BY id DESC LIMIT 1",
            (team_a.upper(), team_b.upper()),
        ).fetchone())
    return {'ok': True, 'target_type': 'lol_price', 'price': row,
            'source': {'kind': row['source_kind'], 'ref': row['source_ref'], 'recorded_at': row['recorded_at'], 'verified_at': ''}}


def _roster_id(team: str, name: str) -> str:
    digest = hashlib.sha1(name.encode('utf-8')).hexdigest()[:10]
    safe_team = re.sub(r'[^A-Za-z0-9_-]+', '-', team.upper()).strip('-') or 'TEAM'
    return f'roster-{safe_team}-{digest}'


def _write_roster(team: str, players: list) -> dict:
    if not isinstance(players, list) or not players:
        raise MutationRejected('人员/首发名单不能为空')
    specs = [_roster_spec(item, index) for index, item in enumerate(players)]
    names = [item['name'] for item in specs]
    if len(names) != len(set(names)):
        raise MutationRejected('人员名单不能有重复选手')
    if len(names) > 5:
        raise MutationRejected('一次最多更新五名选手')
    if len(names) < 5:
        with connect() as conn:
            team_row = get_team_id(team)
            if not team_row:
                raise MutationRejected('队伍不存在')
            active = conn.execute(
                "SELECT player_name, role, position, is_starter, status FROM rosters WHERE team_id=? AND status='active'",
                (team_row['team_id'],),
            ).fetchall()
            by_name = {row['player_name']: row for row in active}
            added = []
            for spec in specs:
                current = by_name.get(spec['name'])
                is_starter = spec.get('is_starter')
                if current is None:
                    conn.execute(
                        """INSERT INTO rosters
                           (roster_id, team_id, player_id, player_name, role, position,
                            is_starter, join_date, status, transfer_notes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                        (_roster_id(team, spec['name']), team_row['team_id'], spec.get('player_id'),
                         spec['name'], spec['role'], spec['position'],
                         1 if is_starter is True else 0, spec.get('join_date'), spec.get('transfer_notes')),
                    )
                    added.append(spec['name'])
                else:
                    conn.execute(
                        """UPDATE rosters SET role=?, position=?,
                           join_date=COALESCE(?, join_date), transfer_notes=COALESCE(?, transfer_notes),
                           is_starter=COALESCE(?, is_starter)
                           WHERE team_id=? AND player_name=? AND status='active'""",
                        (spec['role'], spec['position'], spec.get('join_date'), spec.get('transfer_notes'),
                         None if is_starter is None else int(bool(is_starter)), team_row['team_id'], spec['name']),
                    )
                if is_starter is True:
                    conn.execute(
                        "UPDATE rosters SET is_starter=0 WHERE team_id=? AND status='active' AND role=? AND player_name<>?",
                        (team_row['team_id'], spec['role'], spec['name']),
                    )
            starters = [dict(row) for row in conn.execute(
                """SELECT player_name AS name, role, position FROM rosters
                   WHERE team_id=? AND status='active' AND is_starter=1
                   ORDER BY CASE role WHEN '上单' THEN 1 WHEN '打野' THEN 2 WHEN '中单' THEN 3
                                      WHEN 'ADC' THEN 4 WHEN '辅助' THEN 5 ELSE 9 END""",
                (team_row['team_id'],),
            ).fetchall()]
        return {'ok': True, 'team': team.upper(), 'starters': starters, 'added_players': added}
    with connect() as conn:
        team_row = get_team_id(team)
        if not team_row:
            raise MutationRejected('队伍不存在')
        active = conn.execute(
            "SELECT id, player_name FROM rosters WHERE team_id=? AND status='active'",
            (team_row['team_id'],),
        ).fetchall()
        by_name = {row['player_name']: row for row in active}
        added = []
        for spec in specs:
            if spec['name'] not in by_name:
                conn.execute(
                    """INSERT INTO rosters
                       (roster_id, team_id, player_id, player_name, role, position,
                        is_starter, join_date, status, transfer_notes)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'active', ?)""",
                    (_roster_id(team, spec['name']), team_row['team_id'], spec.get('player_id'),
                     spec['name'], spec['role'], spec['position'], spec.get('join_date'),
                     spec.get('transfer_notes')),
                )
                added.append(spec['name'])
        conn.execute("UPDATE rosters SET is_starter=0 WHERE team_id=? AND status='active'", (team_row['team_id'],))
        for spec in specs:
            conn.execute(
                """UPDATE rosters SET is_starter=1, role=?, position=?,
                   join_date=COALESCE(?, join_date), transfer_notes=COALESCE(?, transfer_notes)
                   WHERE team_id=? AND player_name=? AND status='active'""",
                (spec['role'], spec['position'], spec.get('join_date'), spec.get('transfer_notes'),
                 team_row['team_id'], spec['name']),
            )
        starters = [dict(row) for row in conn.execute(
            """SELECT player_name AS name, role, position FROM rosters
               WHERE team_id=? AND status='active' AND is_starter=1
               ORDER BY CASE role WHEN '上单' THEN 1 WHEN '打野' THEN 2 WHEN '中单' THEN 3
                                  WHEN 'ADC' THEN 4 WHEN '辅助' THEN 5 ELSE 9 END""",
            (team_row['team_id'],),
        ).fetchall()]
    return {'ok': True, 'team': team.upper(), 'starters': starters, 'added_players': added}


def apply_business_mutation(*, target_type: str, target: str, changes: dict, reason: str = '') -> dict:
    target_type = str(target_type or '').strip().lower()
    target_type = {
        'roster': 'team_roster', 'team-roster': 'team_roster', '首发': 'team_roster', '阵容': 'team_roster',
        'profile': 'team_profile', '画像': 'team_profile', '队伍画像': 'team_profile',
        'team-intake': 'team_intake', 'team_identity': 'team_intake', '队伍入库': 'team_intake', '队伍身份': 'team_intake',
        'lol-price': 'lol_price', 'price': 'lol_price', '价格': 'lol_price', '赔率': 'lol_price',
    }.get(target_type, target_type)
    target = _target(target)
    changes = dict(changes or {})
    if target_type == 'team_roster' and 'players' not in changes:
        candidate = changes.get('player')
        if candidate is None and changes.get('name'):
            candidate = {key: changes[key] for key in ('name', 'player_name', 'role', 'position', 'is_starter', 'join_date', 'transfer_notes') if key in changes}
        if candidate is not None:
            changes['players'] = candidate if isinstance(candidate, list) else [candidate]
    operation = str(changes.get('operation', 'update')).strip().lower()
    if operation in HIGH_RISK:
        return {'ok': False, 'status': 'requires_intervention', 'target_type': target_type, 'target': target, 'reason': '结构级或不可逆动作需要钧钧介入'}
    if target_type == 'team_3d':
        raise MutationRejected('三维已合并进队伍画像，直接更新队伍画像的怎么赢、怎么输或关键点')
    if target_type == 'team_roster':
        return {**_write_roster(target, changes.get('players', [])), 'target_type': target_type, 'reason': reason}
    if target_type == 'team_intake':
        return {**_write_team_intake(target, changes), 'target_type': target_type, 'reason': reason}
    if target_type == 'lol_price':
        return {**_write_price_fact({**changes, 'match_key': changes.get('match_key') or target}), 'reason': reason}
    if target_type == 'team_profile':
        fields = ('positioning', 'win_path', 'lose_path', 'key_points', 'bp_tendency', 'evidence')
        values = {field: changes[field] for field in fields if field in changes}
        if not values:
            raise MutationRejected('统一队伍画像没有有效变化')
        try:
            readback = update_team_profile(target, values)
        except (TeamNotFound, ValueError) as exc:
            raise MutationRejected(str(exc)) from exc
        return {'ok': True, 'target_type': target_type, 'target': target.upper(), 'readback': readback, 'reason': reason}
    raise MutationRejected('当前没有接入该对象的正源适配；不自动创建新入口或第二套数据')
