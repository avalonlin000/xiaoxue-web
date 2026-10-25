MODULE = {
    "id": "team",
    "name": "队伍",
    "version": "1.0.0",
    "purpose": "一支队伍的全部事实：基础资料与赛程、五项画像、国内/国际阶段 TS 与单场基本面。",
    "examples": ["查 BLG 现在的画像", "看看 LCK 这阶段谁强", "这场两队的实力差多少"],
    "inputs": {"optional": ["team", "scope", "team_a", "team_b"]},
    "effect": "read",
    "reads": ["队伍与选手基础事实", "队伍画像", "TS 阶段展示", "赛程"],
    "writes": [],
    "output_schema": {"type": "object"},
    "source_policy": {
        "long_term_write": False,
        "mode": "team_profiles_primary",
        "team_profile_format": "fixed_five_sections",
        "compatibility_mirror": "Wiki/队伍 Skill",
        "mirror_missing_is_empty": False,
    },
    "settings": {},
    "dependencies": ["database"],
    "health": {"checks": ["database"], "reason_code": "team_data_unavailable"},
    "tests": ["tests/test_team_profile_contract.py", "tests/test_fundamentals_active_stage.py"],
    "delivery": {
        "mode": "full",
        "configuration": {
            "owner": "lol_data/scripts/ts_stage_table.py",
            "keys": ["stage_token", "MU_INIT", "SIGMA_INIT", "SIGMA_MIN", "TIER_BREAKS"],
            "rule": "活动阶段快照为唯一样本；国内分池、国际赛跨赛区单池；TS=mu-3sigma。",
        },
        "refresh": {
            "entry": "/home/ubuntu/lol_data/scripts/_ts_update.py::run_ts_update",
            "automation": "/home/ubuntu/lol_data/scripts/data_readiness_pipeline.py",
        },
        "source": {
            "database": "/home/ubuntu/lol_data/英雄联盟数据库.db",
            "snapshot": "ts_stage_snapshots",
            "stage": "活动阶段（第三赛段/国际赛，自动切换）",
        },
        "projections": [
            {
                "endpoint": "/api/fundamentals/teams",
                "fields": ["ts_display.power_score", "ts_display.volatility_score", "ts_display.trend", "ts_display.momentum", "ts_display.status"],
            }
        ],
        "agent_entry": {
            "tool": "xiaoxue_get_team",
            "fields": ["ts.power_score", "ts.volatility_score", "ts.trend", "ts.momentum", "ts.status"],
            "behavior": "小雪自主决定何时读取和如何解释；合同不规定对话步骤。",
        },
        "acceptance": ["snapshot_readback", "api_projection", "agent_tool_readback", "automation_entry"],
    },
    "order": 40,
}
