#!/usr/bin/env python3
"""小雪项目 · 开发同步（自动把真实改动回流到开发视图）

目的：让"改动后开发视图自动更新、不用人手工登记"成立。
机制：只读 git 历史，把最近真实 commit（时间/标题/改动文件）自动追加到
      memory-bank/changelog.md，并更新 progress.md 顶部的"最后更新"时间戳。
      由 cron 每天定时跑一次（no_agent），保证开发视图始终反映最新真实状态。

安全性：只读 git，绝不修改代码/数据/历史；只向 changelog.md 追加、只改
       progress.md 顶部时间戳行。可随时停用或回退（被改动文件是纯文本，git 可恢复）。
用法：python3 scripts/sync_development_view.py
"""
from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path

PROJECT = Path("/home/ubuntu/xiaoxue-web")
CHANGELOG = PROJECT / "memory-bank" / "changelog.md"
PROGRESS = PROJECT / "memory-bank" / "progress.md"
GIT_BIN = "git"
# 每次同步最多纳入这个数量的 commit（防一次同步撑爆）
MAX_COMMITS = 20


def run_git(*args: str) -> str:
    return subprocess.run(
        [GIT_BIN, "-C", str(PROJECT), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    ).stdout.strip()


def git_commit_counts() -> int:
    out = run_git("rev-list", "--count", "HEAD")
    try:
        return int(out)
    except ValueError:
        return 0


def last_synced_count(changelog: Path) -> int:
    """读 changelog 里最新一段的同步游标（多段追加结构，必须取最后一个匹配）。"""
    if not changelog.exists():
        return 0
    found: int | None = None
    for line in changelog.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("> 上游 commit 数（同步游标）:"):
            try:
                found = int(s.split(":")[-1].strip())
            except ValueError:
                continue
    return found if found is not None else 0


def compute_window(synced: int, total: int, max_commits: int = MAX_COMMITS) -> tuple[int, int]:
    """本次该写入多少条、跳过多少条：先补最旧的未同步 commit。"""
    new_count = max(0, total - synced)
    take = min(new_count, max_commits)
    skip = new_count - take
    return take, skip


def fetch_recent_commits(limit: int, skip: int = 0) -> list[dict]:
    """取最近 limit 个 commit（可跳过最新 skip 个）：hash/短hash/时间/作者/标题/改动文件."""
    raw = run_git(
        "-c", "core.quotepath=false",
        "log", f"-{limit}", f"--skip={skip}", "--date=format:%Y-%m-%d %H:%M",
        "--pretty=format:%H|%h|%ad|%an|%s", "--name-only",
    )
    commits: list[dict] = []
    cur: dict | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "|" in line and not line.startswith(("  ", "\t")):
            parts = line.split("|", 4)
            if len(parts) == 5:
                cur = {
                    "hash": parts[0], "short": parts[1], "when": parts[2],
                    "author": parts[3], "subject": parts[4], "files": [],
                }
                commits.append(cur)
                continue
        if cur is not None and line.strip():
            cur["files"].append(line.strip())
    return commits


def markdown_escape(text: str) -> str:
    return text.replace("|", "\\|")


def build_changelog_entries(commits: list[dict]) -> list[str]:
    out: list[str] = []
    for c in commits:
        out.append(f"- **{esc(c['short'])}** · {c['when']} · {esc(c['subject'])}")
        if c["files"]:
            files = ", ".join(c["files"][:6])
            if len(c["files"]) > 6:
                files += f" (+{len(c['files'])-6})"
            out.append(f"  - 改动：`{files}`")
    return out


def esc(t: str) -> str:
    return markdown_escape(t)


def main() -> int:
    total = git_commit_counts()
    if total == 0:
        print("no git history")
        return 1

    synced = last_synced_count(CHANGELOG)
    new_count = total - synced

    if new_count <= 0:
        # 没有新 commit，但仍刷新时间戳（保证"最后更新"时间准确）
        _touch_progress_timestamp(datetime.datetime.now())
        print(f"no new commits (already synced at cursor={synced})")
        return 0

    to_take, skip = compute_window(synced, total)
    commits = fetch_recent_commits(to_take, skip=skip)

    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 小雪项目 · 开发变更流水（自动生成，勿手编）",
        "",
        f"> 本文件由 `scripts/sync_development_view.py` 自动维护。它把 git 真实改动",
        f"> （commit）回流到这里，让后续开发看到「改完之后的最新状态」，不用人手工登记。",
        f"> 每次改动落地 commit 后，下一次运行本脚本即自动纳入；流水只追加、不改旧条。",
        "",
        f"> 上游 commit 数（同步游标）: {synced + len(commits)}",
        f"> 最近同步: {now}",
        "",
        f"## {today} 自动同步",
        "",
        f"- 新增同步 commit 数：{new_count}（本次写入 {len(commits)} 条）",
        "",
    ]
    lines += build_changelog_entries(commits)
    lines += [""]

    prev = f"{CHANGELOG.read_text(encoding='utf-8').strip()}\n" if CHANGELOG.exists() else ""
    CHANGELOG.write_text(prev + "\n".join(lines) + "\n", encoding="utf-8")

    _touch_progress_timestamp(now)
    print(f"synced {len(commits)} commits; cursor now {synced + len(commits)}")
    return 0


def _touch_progress_timestamp(when) -> None:
    if not PROGRESS.exists():
        return
    text = PROGRESS.read_text(encoding="utf-8")
    # 更新时间戳行："> 最后更新：YYYY-MM-DD | 更新人：..."
    import re
    new = re.sub(
        r"> 最后更新：[^|]*\|",
        f"> 最后更新：{when} |",
        text,
        count=1,
    )
    if new != text:
        PROGRESS.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
