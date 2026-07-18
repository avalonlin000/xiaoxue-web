from __future__ import annotations

from xiaoxue_api.core.module_registry import ModuleRegistry


def project_module_health(checks: dict, boot_status: dict | None = None) -> dict:
    registry = ModuleRegistry()

    database_ok = bool((checks.get("database") or {}).get("ok"))
    tk_ok = bool((checks.get("tk_dir") or {}).get("ok"))
    skills_ok = bool((checks.get("skill_dirs") or {}).get("ok"))
    market_ok = bool((checks.get("market_notes") or {}).get("ok"))
    daily_ok = bool((checks.get("data_readiness") or {}).get("ok"))
    shell_ok = bool((checks.get("dist") or {}).get("ok"))

    _record(registry, "platform", "应用外壳", shell_ok, "dist_missing", critical=True)
    _record(registry, "team_data", "队伍资料", database_ok, "database_unavailable")
    _record(registry, "tk_knowledge", "TK知识", tk_ok, "tk_directory_unavailable")
    if skills_ok or database_ok:
        registry.healthy("profiles", "队伍画像", message="画像正源或数据库兜底可用")
    else:
        registry.broken(
            "profiles",
            "队伍画像",
            reason_code="profile_sources_unavailable",
            message="画像正源和数据库兜底均不可用",
        )
    _record(registry, "fundamentals", "横向基本面", database_ok, "database_unavailable")
    _record(registry, "market_notes", "临场记录", market_ok, "market_notes_unavailable")
    daily_operation = checks.get("daily_operation") or {}
    if daily_operation.get("state") == "paused_by_user":
        registry.disabled(
            "daily_content",
            "每日日报",
            message=daily_operation.get("message") or "钧钧已主动暂停，待确认后恢复",
        )
    else:
        _record(registry, "daily_content", "每日日报", daily_ok, "readiness_missing")

    registry.healthy("lineup", "阵容交接", message="本地输入契约可用")
    registry.disabled("pre_match", "旧赛前判断", message="保留兼容，等待新版赛前判断替换")
    registry.disabled("analyst", "双分析师", message="非核心能力，失败不影响其他模块")
    registry.disabled("legacy_trades", "旧交易记录兼容", message="仅保留历史接口")
    registry.disabled("weread_bridge", "知识导入登录", message="按需启用")
    _apply_boot_status(registry, boot_status or {})
    return registry.as_dict()


def _record(
    registry: ModuleRegistry,
    module_id: str,
    name: str,
    ok: bool,
    reason_code: str,
    *,
    critical: bool = False,
) -> None:
    if ok:
        registry.healthy(module_id, name)
        return
    registry.broken(
        module_id,
        name,
        reason_code=reason_code,
        message="该模块当前不可用，其他模块继续运行",
        critical=critical,
    )


def _apply_boot_status(registry: ModuleRegistry, boot_status: dict) -> None:
    names = {
        "lineup": "阵容交接",
        "market_notes": "临场记录",
        "team_data": "队伍资料",
        "daily_content": "每日准备",
    }
    for module_id, status in boot_status.items():
        if status.get("status") != "broken":
            continue
        registry.broken(
            module_id,
            names.get(module_id, module_id),
            reason_code=status.get("reason_code") or "module_load_failed",
            message="该模块加载失败，其他模块继续运行",
        )
