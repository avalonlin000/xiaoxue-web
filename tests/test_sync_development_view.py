"""回归测试：sync_development_view 的游标解析与窗口计算。

背景（2026-09-20 修复）：
- changelog 是多段追加结构，同步游标必须取**最后一段**；原实现取第一个匹配，
  导致每次运行都重复追加同一批 commit（手动跑一次 + cron 跑一次 = 两段重复）。
- 积压超过 MAX_COMMITS 时，应"先补最旧的未同步 commit"（写入窗口从旧到新推进），
  而不是每次只取最新 20 条导致中间漏记。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sync_development_view as sdv  # noqa: E402


def test_cursor_takes_last_segment(tmp_path):
    """多段追加结构中，游标应取最后一段（52），而不是第一段（37）。"""
    f = tmp_path / "changelog.md"
    f.write_text(
        "# 流水\n\n"
        "> 上游 commit 数（同步游标）: 37\n\n## 2026-08-19 自动同步\n...\n\n"
        "> 上游 commit 数（同步游标）: 52\n\n## 2026-09-20 自动同步\n...\n",
        encoding="utf-8",
    )
    assert sdv.last_synced_count(f) == 52


def test_cursor_single_segment(tmp_path):
    f = tmp_path / "changelog.md"
    f.write_text("> 上游 commit 数（同步游标）: 12\n", encoding="utf-8")
    assert sdv.last_synced_count(f) == 12


def test_cursor_missing_file(tmp_path):
    assert sdv.last_synced_count(tmp_path / "nope.md") == 0


def test_compute_window_incremental():
    # 新增 15 条、上限 20：全写、不跳
    assert sdv.compute_window(37, 52) == (15, 0)
    # 新增 30 条、上限 20：写 20、跳过最新 10（先补最旧）
    assert sdv.compute_window(37, 67) == (20, 10)
    # 无新增
    assert sdv.compute_window(52, 52) == (0, 0)
