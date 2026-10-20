from __future__ import annotations

import datetime
import os
import re

from xiaoxue_api.modules.team_data.public import get_profile_bundle

from . import repository


def get_current_profile(team: str) -> dict:
    code = str(team or "").strip().upper()
    if not code or len(code) > 40:
        raise ValueError("无效的队伍")
    row = repository.read_current_profile(code)
    return {"found": bool(row), "team": code, "source": "team_profiles", "updated_at": (row or {}).get("updated_at"),
            "profile": {key: str((row or {}).get(key) or "") for key in ("positioning", "win_path", "lose_path", "key_points", "bp_tendency")}}

def _file_updated(path: str) -> str:
    """按文件修改时间给出画像更新时间（供引用时标注新旧）。"""
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
    except OSError:
        return ""


def get_wiki_team(team: str) -> dict:
    code = team.upper()
    path = repository.wiki_team_path(team)
    raw = repository.read_text(path)
    if raw is None:
        return {"found": False, "team": code, "path": path, "html": f"<p>暂无 {code} 的 Wiki 页面</p>"}
    markdown = strip_frontmatter(raw)
    return {"found": True, "team": code, "path": path, "markdown": markdown, "html": markdown_to_html(markdown)}


def get_wiki_concept(concept: str) -> dict:
    path = repository.wiki_concept_path(concept)
    raw = repository.read_text(path)
    if raw is None:
        return {"found": False, "concept": concept, "path": path, "html": f"<p>暂无 {concept} 的 Wiki 概念页</p>"}
    markdown = strip_frontmatter(raw)
    return {"found": True, "concept": concept, "path": path, "markdown": markdown, "html": markdown_to_html(markdown)}


def get_full_profile(team: str) -> dict:
    bundle = get_profile_bundle(team)
    canonical = (bundle or {}).get("team_profile")
    if canonical:
        markdown = team_profile_markdown(canonical)
        return {
            "found": True, "team": canonical["team_name"], "markdown": markdown,
            "html": markdown_to_html(markdown), "source": "team_profile",
            "updated_at": str(canonical.get("updated_at") or ""),
        }
    wiki = get_wiki_team(team)
    if wiki["found"]:
        markdown = humanize_legacy_wiki_markdown(wiki["markdown"])
        return {**wiki, "markdown": markdown, "html": markdown_to_html(markdown), "source": "wiki"}
    skill_path = repository.find_skill_path(team)
    if skill_path:
        raw = repository.read_text(skill_path) or ""
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            markdown = parts[2].strip() if len(parts) >= 3 else raw
        else:
            markdown = raw.strip()
        updated = _file_updated(skill_path)
        if updated:
            markdown = f"{markdown}\n\n> 更新时间：{updated}"
        return {
            "found": True, "team": team.upper(), "html": markdown_to_html(markdown),
            "path": skill_path, "source": "skill", "updated_at": updated,
        }
    generated = database_fallback_profile(team)
    if generated:
        return {**generated, "source": "database_fallback"}
    return {"found": False, "team": team.upper(), "html": f"<p>暂无 {team} 的画像</p>"}


def team_profile_markdown(profile: dict) -> str:
    lines = [
        f"# {profile['team_name']} 队伍画像", "",
        f"- **队伍定位：**{profile['positioning']}",
        f"- **怎么赢：**{profile['win_path']}",
        f"- **怎么输：**{profile['lose_path']}",
        f"- **关键点：**{profile['key_points']}",
        f"- **BP 倾向：**{profile['bp_tendency']}",
    ]
    updated = str(profile.get("updated_at") or "").strip()
    if updated:
        lines.extend(["", f"> 更新时间：{updated}"])
    return "\n".join(lines)


def humanize_legacy_wiki_markdown(markdown: str) -> str:
    """Keep legacy Wiki facts readable without exposing retired field names."""
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "## 三维数据":
            output.append("## 风格 / 版本理解")
            index += 1
            continue
        name_match = re.fullmatch(r"- \*\*dim_([123])_name\*\*: ?(.*)", line)
        if name_match and index + 1 < len(lines):
            value_match = re.fullmatch(rf"- \*\*dim_{name_match.group(1)}_value\*\*: ?(.*)", lines[index + 1])
            if value_match:
                output.append(f"- {name_match.group(2)}：{value_match.group(1)}")
                index += 2
                continue
        replacements = {
            "region": "赛区",
            "version_understanding": "版本理解",
            "notes": "战术笔记",
        }
        field_match = re.fullmatch(r"- \*\*([^*]+)\*\*: ?(.*)", line)
        if field_match:
            field, content = field_match.groups()
            if field == "updated_at":
                index += 1
                continue
            if field in replacements:
                output.append(f"- {replacements[field]}：{content}")
                index += 1
                continue
        output.append(line)
        index += 1
    return "\n".join(output)


def database_fallback_profile(team: str) -> dict | None:
    bundle = get_profile_bundle(team)
    if not bundle:
        return None
    row = bundle["team"]
    d3 = bundle["three_dimensional"]
    players = bundle["players"]
    try:
        from xiaoxue_api.modules.tk_knowledge.public import count_team_entries
        tk_count = count_team_entries(row["short_name"])
    except (ImportError, OSError):
        tk_count = 0
    lines = [
        f"# {row['short_name']} 资料总览", "",
        "> 现有资料自动汇总，只展示已录入的信息。", "",
        "## 基础信息", f"- 队伍：{value(row['name'], row['short_name'])}",
        f"- 简称：{row['short_name']}", f"- 赛区：{value(row['region'])}", f"- 联赛：{value(row['league_id'])}", "",
    ]
    # 只出展示层（综合实力/稳定性/趋势/势头/状态），不下发 mu/sigma/ts 原始值。
    try:
        from xiaoxue_api.modules.fundamentals.public import get_stage_display_map
        display = get_stage_display_map().get(str(row["short_name"]).upper(), {})
    except Exception:
        display = {}
    lines.append("## 综合实力与稳定性")
    if display:
        lines.extend([
            f"- 综合实力：{number(display.get('power_score'))}",
            f"- 稳定性：{number(display.get('volatility_score'))}",
            f"- 趋势：{number(display.get('trend'))}",
            f"- 势头：{number(display.get('momentum'))}",
            f"- 状态：{value(display.get('status'))}",
        ])
    else:
        lines.append("- 暂无展示层评分。")
    if row.get("note"):
        lines.append(f"- 备注：{row['note']}")
    lines.extend(["", "## 首发与关键选手"])
    lines.extend(f"- {player['role']}：{player['name']}（{player['status']}）" for player in players)
    if not players:
        lines.append("- 暂无首发资料。")
    lines.extend(["", "## 风格 / 版本理解"])
    if d3:
        lines.extend([
            f"- {value(d3['dim_1_name'], '维度一')}：{value(d3['dim_1_value'])}",
            f"- {value(d3['dim_2_name'], '维度二')}：{value(d3['dim_2_value'])}",
            f"- {value(d3['dim_3_name'], '维度三')}：{value(d3['dim_3_value'])}",
            f"- 战术笔记：{value(d3['notes'], '暂无')}",
            f"- 更新时间：{value(d3['updated_at'])}",
        ])
    else:
        lines.append("- 暂无风格 / 版本理解资料。")
    lines.extend(["", "## 资料覆盖", f"- 队伍 TK 共 {tk_count} 条"])
    markdown = "\n".join(lines)
    return {"found": True, "team": row["short_name"], "markdown": markdown, "html": markdown_to_html(markdown),
            "updated_at": value(d3['updated_at']) if d3 else ""}


def strip_frontmatter(markdown: str) -> str:
    if markdown.startswith("---"):
        parts = markdown.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return markdown.strip()


def markdown_to_html(markdown: str) -> str:
    output, in_list, in_code, in_table = [], False, False, False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            output.append('<pre class="code-block">' if in_code else '</pre>')
        elif in_code:
            output.append(f"{raw}\n")
        elif line.startswith("# "):
            output.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            output.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            output.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("#### "):
            output.append(f"<h4>{line[5:]}</h4>")
        elif "|" in line and "---" in line.replace(" ", ""):
            continue
        elif line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            row = "".join(f"<{tag}>{cell}</{tag}>" for cell in cells)
            if not in_table:
                output.append(f"<table><thead><tr>{row}</tr></thead><tbody>")
                in_table = True
            else:
                output.append(f"<tr>{row}</tr>")
        elif line == "---":
            if in_list:
                output.append("</ul>")
                in_list = False
            if in_table:
                output.append("</tbody></table>")
                in_table = False
            output.append("<hr>")
        elif line.startswith("- "):
            if in_table:
                output.append("</tbody></table>")
                in_table = False
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{line[2:]}</li>")
        elif line.startswith("> "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line:
            if in_table:
                output.append("</tbody></table>")
                in_table = False
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<p>{line}</p>")
    if in_list:
        output.append("</ul>")
    if in_table:
        output.append("</tbody></table>")
    if in_code:
        output.append("</pre>")
    return "\n".join(output)


def value(item, fallback="-"):
    return fallback if item in (None, "") else str(item)


def number(item):
    try:
        return f"{float(item):.1f}"
    except (TypeError, ValueError):
        return "-"
