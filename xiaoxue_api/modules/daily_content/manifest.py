MODULE = {
    "id": "daily_content",
    "name": "日报",
    "version": "1.0.0",
    "purpose": "读取已生成并通过数据就绪门禁的 LOL 日报内容。",
    "examples": ["看今天日报", "今天有哪些比赛"],
    "inputs": {"optional": ["date"]},
    "effect": "read",
    "reads": ["日报产物", "data_readiness manifest"],
    "writes": [],
    "output_schema": {"type": "object"},
    "source_policy": {"source": "frozen_daily_pipeline"},
    "settings": {},
    "dependencies": ["data_readiness"],
    "health": {
        "checks": ["data_readiness"],
        "reason_code": "readiness_missing",
        "pause_check": "daily_operation",
        "pause_state": "paused_by_user"
    },
    "tests": ["tests/test_daily_content_contract.py"],
    "order": 40,
}
