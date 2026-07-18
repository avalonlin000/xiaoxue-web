from __future__ import annotations

import asyncio

from xiaoxue_api.modules.team_data.public import get_profile_bundle
from xiaoxue_api.modules.tk_knowledge.public import search_team_entries

from . import repository


async def analyze(team: str, analyst: str = "") -> dict:
    snapshot = build_snapshot(team)

    async def zhongnian():
        if analyst and analyst != "中年电竞人":
            return None
        framework = repository.read_skill("zhongnian-esports-coach")
        system = f"""你是「中年电竞人」——一位资深LOL教练，擅长BP评估、选手状态判断、体系有效性检验。
你的分析框架如下（必须严格遵循每一条）：
{framework}
输出要求：用「控制层级」「预制大脑」「选手评估二元法」「体系锚点理论」四个维度逐一分析。给出具体打分和判断，用生活化比喻。200-400字。"""
        return "中年电竞人", await repository.call_llm(system, snapshot)

    async def xinyu():
        if analyst and analyst != "心语悦无言":
            return None
        framework = repository.read_skill("xinyu-tactical-analyst")
        system = f"""你是「心语悦无言」——一位LOL战术分析师，擅长体系框架拆解、阵容构建分析、回合概念建模。
你的分析框架如下（必须严格遵循每一条）：
{framework}
输出要求：用「阵容构建核心链」「决策/操作分离」「回合概念」「三大体系定位」四个维度逐一分析。指出结构性缺陷和战术优势。200-400字。"""
        return "心语悦无言", await repository.call_llm(system, snapshot)

    results = await asyncio.gather(zhongnian(), xinyu())
    content = {name: text for item in results if item for name, text in [item]}
    if not content:
        return {"found": False, "content": "", "msg": f"暂无 {team} 的分析数据"}
    if analyst and analyst in content:
        return {"found": True, "analyst": analyst, "content": content[analyst]}
    return {"found": True, "content": content}


def build_snapshot(team: str) -> str:
    bundle = get_profile_bundle(team) or {"team": {"short_name": team, "name": team, "region": ""}, "three_dimensional": None}
    info = bundle["team"]
    d3 = bundle.get("three_dimensional") or {}
    tk_items = search_team_entries("", team, 5)
    tk_samples = "\n".join(f"{item.get('filename', '')}: {(item.get('content') or '')[:400]}" for item in tk_items) or "（无相关TK）"
    return f"""队伍：{info.get('name') or team} ({info.get('region') or ''}-{info.get('short_name') or team})
三维数据：{d3.get('dim_1_name', 'N/A')}: {d3.get('dim_1_value', 'N/A')} | {d3.get('dim_2_name', 'N/A')}: {d3.get('dim_2_value', 'N/A')} | {d3.get('dim_3_name', 'N/A')}: {d3.get('dim_3_value', 'N/A')}
战术笔记：{d3.get('notes') or '无'}
版本理解：{d3.get('version_understanding') or '无'}
近期TK：
{tk_samples}
画像摘要：{repository.read_team_profile(team) or '无'}"""
