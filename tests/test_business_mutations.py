import sqlite3
from unittest.mock import patch

from xiaoxue_api.modules.business_mutations import service as mutation_service
from xiaoxue_api.modules.team_data import repository as team_repository


def _roster_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE rosters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, roster_id TEXT NOT NULL, team_id TEXT NOT NULL,
        player_id TEXT, player_name TEXT NOT NULL, role TEXT, position TEXT,
        is_starter INTEGER DEFAULT 1, join_date TEXT, leave_date TEXT,
        status TEXT DEFAULT 'active', transfer_notes TEXT
    )''')
    conn.executemany(
        'INSERT INTO rosters (roster_id,team_id,player_name,role,position,is_starter,status) VALUES (?,?,?,?,?,?,?)',
        [
            ('r-a', 'LPL-TST', 'OldTop', '上单', 'TOP', 1, 'active'),
            ('r-b', 'LPL-TST', 'OldJg', '打野', 'JUNGLE', 1, 'active'),
        ],
    )
    return conn


def test_roster_update_can_add_new_players_and_read_back_starters():
    conn = _roster_db()
    players = [
        {'name': 'NewTop', 'role': '上单', 'position': 'TOP'},
        {'name': 'NewJg', 'role': '打野', 'position': 'JUNGLE'},
        {'name': 'NewMid', 'role': '中单', 'position': 'MID'},
        {'name': 'NewAdc', 'role': 'ADC', 'position': 'ADC'},
        {'name': 'NewSup', 'role': '辅助', 'position': 'SUPPORT'},
    ]
    with patch.object(mutation_service, 'connect', return_value=conn), patch.object(
        mutation_service, 'get_team_id', return_value={'team_id': 'LPL-TST'}
    ):
        result = mutation_service._write_roster('TST', players)
    assert result['ok'] is True
    assert result['added_players'] == ['NewTop', 'NewJg', 'NewMid', 'NewAdc', 'NewSup']
    assert [row['name'] for row in result['starters']] == ['NewTop', 'NewJg', 'NewMid', 'NewAdc', 'NewSup']
    conn.close()


def test_roster_update_accepts_one_player_and_demotes_same_role_starter():
    conn = _roster_db()
    with patch.object(mutation_service, 'connect', return_value=conn), patch.object(
        mutation_service, 'get_team_id', return_value={'team_id': 'LPL-TST'}
    ):
        result = mutation_service.apply_business_mutation(
            target_type='首发', target='TST',
            changes={'name': 'NewJg', 'role': '打野', 'position': 'JUNGLE', 'is_starter': True},
        )
    assert result['ok'] is True
    assert [row['name'] for row in result['starters']] == ['OldTop', 'NewJg']
    assert conn.execute(
        "SELECT is_starter FROM rosters WHERE player_name='OldJg'"
    ).fetchone()[0] == 0
    conn.close()


def test_high_risk_is_reserved_for_large_destructive_operations():
    assert mutation_service.apply_business_mutation(
        target_type='team_roster', target='TST', changes={'operation': 'clear_all'}
    )['status'] == 'requires_intervention'
    assert 'update' not in mutation_service.HIGH_RISK
    assert 'delete' not in mutation_service.HIGH_RISK


def test_team_3d_update_can_insert_for_an_existing_team():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE teams (short_name TEXT, region TEXT)')
    conn.execute('CREATE TABLE team_3d_data (id INTEGER PRIMARY KEY AUTOINCREMENT, team_name TEXT, region TEXT, dim_1_name TEXT, dim_1_value TEXT, dim_2_name TEXT, dim_2_value TEXT, dim_3_name TEXT, dim_3_value TEXT, season TEXT, updated_at TEXT, notes TEXT, version_understanding TEXT)')
    conn.execute("INSERT INTO teams VALUES ('TST','LPL')")
    with patch.object(team_repository, 'connect', return_value=conn):
        assert team_repository.update_team_3d('TST', {'dim_1_value': 'A'}, 'now') is True
    row = conn.execute("SELECT team_name, region, dim_1_value FROM team_3d_data").fetchone()
    assert dict(row) == {'team_name': 'TST', 'region': 'LPL', 'dim_1_value': 'A'}
    conn.close()
