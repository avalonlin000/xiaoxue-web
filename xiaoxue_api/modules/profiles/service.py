from __future__ import annotations

from xiaoxue_api.modules.team_data.public import get_profile_bundle

from . import repository


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
    wiki = get_wiki_team(team)
    if wiki["found"]:
        return {**wiki, "source": "wiki"}
    skill_path = repository.find_skill_path(team)
    if skill_path:
        raw = repository.read_text(skill_path) or ""
        markdown = raw.split("---", 2)[2].strip() if len(raw.split("---", 2)) >= 3 else raw
        return {
            "found": True, "team": team.upper(), "html": markdown_to_html(markdown),
            "path": skill_path, "source": "skill",
        }
    generated = database_fallback_profile(team)
    if generated:
        return {**generated, "source": "database_fallback"}
    return {"found": False, "team": team.upper(), "html": f"<p>暂无 {team} 的完整画像（Wiki / SKILL.md / 数据库底表均未找到）</p>"}


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
        f"# {row['short_name']} 数据库只读画像", "",
        "> 这是一份从结构化数据自动拼出的兜底画像；它不是手工 SKILL.md，不会补写没有来源的判断。", "",
        "## 基础信息", f"- 队伍：{value(row['name'], row['short_name'])}",
        f"- 简称：{row['short_name']}", f"- 赛区：{value(row['region'])}", f"- 联赛：{value(row['league_id'])}", "",
        "## TS / 稳定性底表",
        f"- mu：{number(row['final_seed_mu'] if row['final_seed_mu'] is not None else row['mu'])}",
        f"- sigma：{number(row['seed_sigma'] if row['seed_sigma'] is not None else row['sigma'])}",
        f"- TS：{number(row['seed_ts'])}", f"- 赔率：{number(row['outright_odds_decimal'])}",
    ]
    if row.get("note"):
        lines.append(f"- 备注：{row['note']}")
    lines.extend(["", "## 首发 / 关键选手"])
    lines.extend(f"- {player['role']}：{player['name']}（{player['status']}）" for player in players)
    if not players:
        lines.append("- 暂无 rosters 可用记录；不推断选手。")
    lines.extend(["", "## 三维数据"])
    if d3:
        lines.extend([
            f"- {value(d3['dim_1_name'], '维度一')}：{value(d3['dim_1_value'])}",
            f"- {value(d3['dim_2_name'], '维度二')}：{value(d3['dim_2_value'])}",
            f"- {value(d3['dim_3_name'], '维度三')}：{value(d3['dim_3_value'])}",
            f"- 战术笔记：{value(d3['notes'], '暂无')}", f"- 版本理解：{value(d3['version_understanding'], '暂无')}",
            f"- 更新时间：{value(d3['updated_at'])}",
        ])
    else:
        lines.append("- 暂无 team_3d_data 记录。")
    lines.extend(["", "## 资料覆盖", f"- TK 命中数量：{tk_count}",
                  "- 画像来源：teams / rosters / team_3d_data / msi_ts_seed",
                  "- 边界：只读展示，不自动生成交易方向，不替代人工画像。"])
    markdown = "\n".join(lines)
    return {"found": True, "team": row["short_name"], "markdown": markdown, "html": markdown_to_html(markdown)}


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
