#!/usr/bin/env python3
"""小雪每日巡检（no-agent 版）。

目标：不用 LLM 生成巡检，避免 DeepSeek 流式 stale / Broken pipe 导致 cron 失败。
stdout 会由 Hermes cron 直接投递；输出 [SILENT] 表示不发群消息。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path("/home/ubuntu/lol_data")
# 统一配置：DB 路径/服务 URL 从 system_config.json 读取，禁止硬编码
sys.path.insert(0, str(ROOT / "libs"))
from config import DB_PATH, get_health_endpoint  # noqa: E402

JOBS_PATH = Path.home() / ".hermes/cron/jobs.json"
SELF_JOB_ID = "355886f0ca6b"
IMPORT_JOB_ID = "1903d8eb610e"
IMPORT_OUTPUT_DIR = Path.home() / ".hermes/cron/output" / IMPORT_JOB_ID
PROJECT_TASKS = Path("/home/ubuntu/xiaoxue-web/scripts/tasks")
UPLOAD_SCRIPT = PROJECT_TASKS / "upload_import_log.py"
WECHAT_SEARCH_SCRIPT = PROJECT_TASKS / "knowledge/wechat_scripts/search_xuanchuang.js"
WECHAT_SEARCH_MODULES = WECHAT_SEARCH_SCRIPT.parent / "node_modules"
IMPORT_MANIFEST_DIR = ROOT / "scripts"


def run(cmd: list[str], timeout: int = 10, cwd: str | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, repr(e)


def http_status(url: str, timeout: int = 3) -> str:
    try:
        with urlopen(url, timeout=timeout) as r:
            return str(r.status)
    except Exception:
        return "DOWN"


def db_report() -> tuple[list[str], list[str]]:
    lines: list[str] = []
    issues: list[str] = []
    if not DB_PATH.exists():
        return lines, [f"🔴 数据库不存在：{DB_PATH}"]
    try:
        db = sqlite3.connect(DB_PATH)
        for table, col in [("matches", "match_time"), ("schedules", "updated_at"), ("team_3d_data", "updated_at")]:
            cnt = db.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            ua = db.execute(f"SELECT MAX({col}) FROM [{table}]").fetchone()[0]
            lines.append(f"{table}: {cnt} 行 | 最后更新: {ua or '无数据'}")
            if cnt == 0:
                issues.append(f"⚠️ {table} 为空")
        roster_cnt = db.execute("SELECT COUNT(*) FROM rosters").fetchone()[0]
        roster_ua = db.execute("SELECT MAX(created_at) FROM rosters").fetchone()[0]
        team_cnt = db.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        lines.append(f"rosters: {roster_cnt} 行 | created_at: {roster_ua or '无数据'} ℹ️")
        lines.append(f"teams: {team_cnt} 行")
        if roster_cnt == 0:
            issues.append("⚠️ rosters 为空")
        if team_cnt == 0:
            issues.append("⚠️ teams 为空")
        db.close()
    except Exception as e:
        issues.append(f"🔴 数据库检查失败：{e}")
    return lines, issues


def schedule_today() -> tuple[list[str], list[str]]:
    lines: list[str] = []
    issues: list[str] = []
    if not DB_PATH.exists():
        return lines, issues
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute(
            """
            SELECT time_bjt, team_a, team_b, region
            FROM schedules
            WHERE date=date('now','localtime') AND region IN ('LPL','LCK','国际','INTL')
            ORDER BY time_bjt
            """
        ).fetchall()
        db.close()
        if rows:
            lines = [f"{r[0]} | {r[1]} vs {r[2]} | {r[3]}" for r in rows]
        else:
            lines = ["今日无赛程"]
    except Exception as e:
        issues.append(f"⚠️ 今日赛程查询失败：{e}")
    return lines, issues


def cron_issues() -> list[str]:
    issues: list[str] = []
    if not JOBS_PATH.exists():
        return [f"⚠️ cron jobs.json 不存在：{JOBS_PATH}"]
    try:
        data = json.loads(JOBS_PATH.read_text())
    except Exception as e:
        return [f"⚠️ cron jobs.json 读取失败：{e}"]
    for job in data.get("jobs", []):
        if not job.get("enabled", True):
            continue
        jid = job.get("id", "")
        # 正在执行的巡检不使用自己的上次状态判断本次健康度，避免旧错误自锁。
        if jid == SELF_JOB_ID:
            continue
        # Import cron writes the receipt as the durable source of truth. A
        # successful manual/recovered run must clear an old scheduler error;
        # do not keep alarming from stale jobs.json metadata.
        if jid == IMPORT_JOB_ID:
            receipts = sorted(
                ROOT.joinpath("scripts").glob("knowledge_import_manifest_*-receipt.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if receipts:
                try:
                    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
                    if receipt.get("status") == "complete":
                        continue
                except (OSError, json.JSONDecodeError):
                    pass
        if job.get("last_status") == "error":
            issues.append(f"⚠️ cron {job.get('name', jid)} 上次失败：{job.get('last_error') or 'unknown'}")
    return issues


def system_report() -> tuple[list[str], list[str]]:
    lines: list[str] = []
    issues: list[str] = []

    usage = shutil.disk_usage("/")
    pct = usage.used / usage.total * 100
    lines.append(f"磁盘 /: {pct:.1f}% used")
    if pct > 85:
        issues.append(f"🔴 磁盘 / 使用率 {pct:.1f}% > 85%")

    code, mem = run(["free", "-h"], timeout=5)
    if code == 0:
        for line in mem.splitlines():
            if line.startswith("Mem:"):
                lines.append("内存: " + " ".join(line.split()[1:4]))
                break

    ollama = http_status(get_health_endpoint("ollama"))
    rag = http_status(get_health_endpoint("mempalace"))
    obscura = http_status(get_health_endpoint("obscura"))
    lines.append(f"Ollama: {ollama}")
    lines.append(f"RAG API: {rag}")
    lines.append(f"Obscura: {obscura}")
    if rag != "200":
        issues.append(f"⚠️ RAG API 状态：{rag}")
    if obscura != "200":
        issues.append(f"⚠️ Obscura 状态：{obscura}")

    return lines, issues


def knowledge_import_issues() -> list[str]:
    issues: list[str] = []

    # 1) 公众号主链路不依赖登录。这里只检查本地依赖和最近一次 manifest，
    # 不在每日巡检里额外请求搜狗，避免巡检本身触发限流。
    if not WECHAT_SEARCH_SCRIPT.exists():
        issues.append(f"⚠️ 免登录公众号搜索脚本不存在：{WECHAT_SEARCH_SCRIPT}")
    elif not WECHAT_SEARCH_MODULES.exists():
        issues.append("⚠️ 免登录公众号搜索依赖缺失：在 wechat-article-search/scripts 运行 npm install")
    else:
        manifests = sorted(
            (
                path for path in IMPORT_MANIFEST_DIR.glob("knowledge_import_manifest_*.json")
                if not path.name.endswith("-receipt.json")
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if manifests:
            try:
                manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
                # discovery manifest stores per-source state under sources.
                wechat = manifest.get("sources", {}).get("wechat", {})
                status = wechat.get("status", "UNKNOWN")
                if status not in {"OK", "ready"}:
                    issues.append(
                        f"⚠️ 免登录公众号搜索最近状态：{status}（微信读书登录不再是前置条件）"
                    )
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f"⚠️ 知识导入 manifest 无法读取：{exc}")

    # 2) Import cron output exists and has recent enough logs.
    logs = sorted(IMPORT_OUTPUT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if IMPORT_OUTPUT_DIR.exists() else []
    if not logs:
        return issues + ["⚠️ 知识导入没有 cron 输出日志"]
    recent = logs[:2]

    zero_bili_tk = 0
    for path in recent:
        text = path.read_text(errors="ignore")
        m = re.search(r"TK提取入库\**[：:]\**\s*(?:\*\*)?(\d+)", text)
        if m and int(m.group(1)) <= 0:
            zero_bili_tk += 1
    if zero_bili_tk >= 2:
        issues.append("⚠️ 知识导入：B站 TK 入库连续两次为 0")

    # 3) Upload script must be the canonical real uploader, not old placeholder
    # or markdown +create flow.
    if UPLOAD_SCRIPT.exists():
        upload_text = UPLOAD_SCRIPT.read_text(errors="ignore")
        if "placeholder" in upload_text or "no data to upload" in upload_text:
            issues.append("⚠️ 知识导入日志上传脚本仍是 placeholder")
        if "drive" not in upload_text or "+upload" not in upload_text or "import_log_uploads.json" not in upload_text:
            issues.append("⚠️ 知识导入日志上传脚本不是当前 drive +upload 去重实现")
    else:
        issues.append(f"⚠️ 知识导入日志上传脚本不存在：{UPLOAD_SCRIPT}")

    return issues


def main() -> int:
    now = datetime.now()
    weekday = now.isoweekday()  # Monday=1

    db_lines, db_issues = db_report()
    schedule_lines, schedule_issues = schedule_today()
    sys_lines, sys_issues = system_report()
    c_issues = cron_issues()
    k_issues = knowledge_import_issues()

    issues = db_issues + schedule_issues + sys_issues + c_issues + k_issues
    rest_day = weekday == 1 and schedule_lines == ["今日无赛程"]

    if rest_day and not issues:
        print("[SILENT]")
        return 0

    title = f"小雪每日巡检 — {now:%Y-%m-%d %H:%M}"
    if issues:
        print(f"## {title}\n")
        print("### 异常项")
        for item in issues[:20]:
            print(f"- {item}")
        print("\n### 系统健康")
        for line in sys_lines:
            print(f"- {line}")
        print("\n### 数据库摘要")
        for line in db_lines[:8]:
            print(f"- {line}")
        if not rest_day:
            print("\n### 今日赛程")
            for line in schedule_lines[:20]:
                print(f"- {line}")
        return 0

    # 赛季日正常报告：精简版。
    print(f"## {title}\n")
    print("### 数据库摘要")
    for line in db_lines[:8]:
        print(f"- {line}")
    print("\n### 今日赛程")
    for line in schedule_lines[:20]:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_daily_inspection.py（无参数；只读巡检）")
        raise SystemExit(0)
    sys.exit(main())
