MODULE = {
    "id": "profiles",
    "name": "画像",
    "version": "1.0.0",
    "purpose": "读取统一五项队伍画像与选手长期画像；队伍画像写回由统一业务变更能力承接。",
    "examples": ["HLE 怎么赢怎么输", "看 GEN 队伍画像"],
    "inputs": {"required": ["subject"]},
    "effect": "read",
    "reads": ["team_profile", "队伍画像 Skill（兼容）", "英雄联盟数据库.db"],
    "writes": [],
    "output_schema": {"type": "object"},
    "source_policy": {
        "mode": "team_profiles_primary",
        "team_profile_format": "fixed_five_sections",
        "compatibility_mirror": "Wiki/队伍 Skill",
        "mirror_missing_is_empty": False,
    },
    "settings": {},
    "dependencies": ["skill_dirs", "database"],
    "health": {
        "checks": ["skill_dirs", "database"],
        "check_mode": "any",
        "reason_code": "profile_sources_unavailable",
        "message": "画像正源或数据库兜底可用"
    },
    "tests": ["tests/test_profiles_contract.py"],
    "order": 50,
}
