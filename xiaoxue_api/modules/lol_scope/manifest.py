MODULE = {
    "id": "lol_scope",
    "name": "LOL 范围与覆盖面",
    "version": "1.0.0",
    "purpose": "按当前研究赛事派生范围（区间、参赛队伍、比赛清单），并计算每场在谁上场/价格/结果三项上的覆盖状态与缺口。",
    "examples": [
        "现在关注的范围里有哪些比赛和队伍",
        "明天这两场哪边资料有洞",
        "这场有没有首发和结果"
    ],
    "inputs": {"required": [], "optional": ["date", "days"]},
    "effect": "read",
    "reads": ["当前赛事范围配置", "英雄联盟数据库 schedules/matches/teams/rosters/team_profiles"],
    "writes": [],
    "output_schema": {
        "type": "object",
        "fields": ["event", "leagues", "window", "teams", "matches", "gaps", "sources", "settings"],
    },
    "source_policy": {
        "domain_allowlist": [],
        "official_api": True,
        "on_demand_only": True,
        "long_term_write": False,
        "stale_marking": "每条事实带回取得时间与陈旧天数；未知一律标 missing，不用旧值顶替",
    },
    "settings": {"lineup_stale_days": 45, "profile_stale_days": 45},
    "dependencies": ["database", "current_event_scope"],
    "health": {"checks": ["database"], "message": "读取赛程与队伍事实；只读，无写入", "reason_code": "lol_scope_unavailable"},
    "tests": ["tests/test_lol_scope_service.py"],
    "order": 120,
}
