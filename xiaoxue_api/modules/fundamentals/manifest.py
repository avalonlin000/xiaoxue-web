MODULE = {
    "id": "fundamentals",
    "name": "队伍基本面",
    "version": "1.1.0",
    "purpose": "读取队伍三维、活动阶段（国内/国际）TS 与单场基本面上下文。",
    "examples": ["对比两队基本面", "看看这场 TS 底表"],
    "inputs": {"optional": ["team_a", "team_b", "scope"]},
    "effect": "read",
    "reads": ["英雄联盟数据库.db"],
    "writes": [],
    "output_schema": {"type": "object"},
    "source_policy": {"source": "official_database"},
    "settings": {},
    "dependencies": ["database"],
    "health": {"checks": ["database"], "reason_code": "database_unavailable"},
    "tests": ["tests/test_fundamentals_contract.py", "tests/test_ts_stage_table.py", "tests/test_capability_delivery.py"],
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
        "acceptance": [
            "snapshot_readback",
            "api_projection",
            "agent_tool_readback",
            "automation_entry",
        ],
    },
    "order": 70,
}
