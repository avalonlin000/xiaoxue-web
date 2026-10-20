import sqlite3
from unittest.mock import patch

from xiaoxue_api.modules.profiles.service import team_profile_markdown
from xiaoxue_api.modules.team_data import repository, service


def _db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE teams (
        short_name TEXT, name TEXT, team_id TEXT, region TEXT, league_id TEXT,
        mu REAL, sigma REAL
    )''')
    conn.execute('''CREATE TABLE msi_ts_seed (
        team TEXT, final_seed_mu REAL, seed_sigma REAL, seed_ts REAL,
        note TEXT, display_name TEXT
    )''')
    conn.execute('''CREATE TABLE team_3d_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT, team_name TEXT, region TEXT,
        dim_1_name TEXT, dim_1_value TEXT, dim_2_name TEXT, dim_2_value TEXT,
        dim_3_name TEXT, dim_3_value TEXT, season TEXT, updated_at TEXT,
        notes TEXT, version_understanding TEXT
    )''')
    conn.execute('''CREATE TABLE rosters (
        player_name TEXT, role TEXT, position TEXT, is_starter INTEGER,
        status TEXT, team_id TEXT
    )''')
    conn.execute("INSERT INTO teams VALUES ('TST','Test Team','LPL-TST','LPL','LPL-2026',25,8)")
    return conn


def _profile():
    return {
        'positioning': '中野带节奏、双C兑现的进攻队。',
        'win_path': '中路先动，打野打开野区和资源团。',
        'lose_path': '中野被限制后，资源团决策容易失效。',
        'key_points': '看中野能否先动并把线权变成地图优势。',
        'bp_tendency': '偏好中野主动和中期团战阵容。',
        'evidence': [{'source': 'tk', 'ref': 'test'}],
    }


def test_unified_profile_is_complete_and_projects_to_legacy_3d():
    conn = _db()
    with patch.object(repository, 'connect', return_value=conn):
        result = service.update_team_profile('TST', _profile())
        projection = service.get_team_3d('TST')
    assert result['team_name'] == 'TST'
    assert result['evidence'] == [{'source': 'tk', 'ref': 'test'}]
    assert projection['dim_1_name'] == '怎么赢'
    assert projection['dim_1_value'] == _profile()['win_path']
    assert projection['dim_2_name'] == '怎么输'
    assert projection['dim_3_name'] == '关键点'
    conn.close()


def test_unified_profile_allows_partial_first_write():
    conn = _db()
    incomplete = _profile()
    incomplete.pop('bp_tendency')
    with patch.object(repository, 'connect', return_value=conn):
        result = service.update_team_profile('TST', incomplete)
    assert result['positioning'] == incomplete['positioning']
    assert result['bp_tendency'] == ''
    conn.close()


def test_unified_profile_allows_one_section_update_after_first_write():
    conn = _db()
    with patch.object(repository, 'connect', return_value=conn):
        service.update_team_profile('TST', _profile())
        result = service.update_team_profile('TST', {'bp_tendency': '改成更偏前期主动的 BP。'})
    assert result['bp_tendency'] == '改成更偏前期主动的 BP。'
    assert result['positioning'] == _profile()['positioning']
    conn.close()


def test_profile_markdown_has_only_the_fixed_five_sections():
    profile = {'team_name': 'TST', **_profile()}
    markdown = team_profile_markdown(profile)
    assert markdown.splitlines()[0] == '# TST 队伍画像'
    assert [line.split('：', 1)[0] for line in markdown.splitlines() if line.startswith('- ')] == [
        '- **队伍定位', '- **怎么赢', '- **怎么输', '- **关键点', '- **BP 倾向',
    ]
    assert '本期变化' not in markdown


def test_profile_markdown_shows_updated_time_footer():
    """新增(2026-10-01): 画像带更新时间（引用时可标新旧），五个区块保持固定五个。"""
    profile = {'team_name': 'TST', **_profile(), 'updated_at': '2026-10-01 12:00:00'}
    markdown = team_profile_markdown(profile)
    assert '> 更新时间：2026-10-01 12:00:00' in markdown
    assert [line.split('：', 1)[0] for line in markdown.splitlines() if line.startswith('- ')] == [
        '- **队伍定位', '- **怎么赢', '- **怎么输', '- **关键点', '- **BP 倾向',
    ]
