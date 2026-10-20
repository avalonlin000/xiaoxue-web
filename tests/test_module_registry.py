from __future__ import annotations

import unittest


class ModuleRegistryTests(unittest.TestCase):
    def test_one_broken_module_degrades_app_without_hiding_healthy_modules(self) -> None:
        from xiaoxue_api.core.module_registry import ModuleRegistry

        registry = ModuleRegistry()
        registry.healthy("teams", "队伍资料")
        registry.broken(
            "daily",
            "每日准备",
            reason_code="readiness_missing",
            message="当天数据尚未准备好",
        )
        registry.disabled("analyst", "双分析师", message="暂不启用")

        payload = registry.as_dict()

        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["modules"]["teams"]["status"], "healthy")
        self.assertEqual(payload["modules"]["daily"]["status"], "broken")
        self.assertEqual(payload["modules"]["analyst"]["status"], "disabled")

    def test_disabled_module_does_not_degrade_app(self) -> None:
        from xiaoxue_api.core.module_registry import ModuleRegistry

        registry = ModuleRegistry()
        registry.healthy("teams", "队伍资料")
        registry.disabled("analyst", "双分析师", message="暂不启用")

        self.assertEqual(registry.as_dict()["status"], "healthy")

    def test_broken_shell_marks_app_broken(self) -> None:
        from xiaoxue_api.core.module_registry import ModuleRegistry

        registry = ModuleRegistry()
        registry.broken(
            "platform",
            "应用外壳",
            reason_code="startup_failed",
            message="应用无法启动",
            critical=True,
        )
        registry.healthy("tk_library", "TK资料库")

        self.assertEqual(registry.as_dict()["status"], "broken")

    def test_registered_manifest_enriches_health_without_changing_module_status(self) -> None:
        from xiaoxue_api.core.module_registry import ModuleRegistry

        registry = ModuleRegistry()
        registry.register_manifest(_manifest("teams", effect="read"), module_name="teams")
        registry.healthy("teams")

        payload = registry.as_dict()
        self.assertEqual(payload["modules"]["teams"]["version"], "1.0.0")
        self.assertEqual(payload["modules"]["teams"]["effect"], "read")
        self.assertEqual(payload["capabilities"]["teams"]["purpose"], "test capability")

    def test_capability_result_has_the_complete_stable_envelope(self) -> None:
        from xiaoxue_api.core.module_registry import capability_result

        payload = capability_result(
            "partial",
            summary="部分资料可用",
            data={"teams": ["HLE", "GEN"]},
            gaps=["TS 缺失"],
            effects={"network": False, "writes": []},
            trace={"capability": "match_context", "version": "1.0.0"},
        )

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(
            set(payload),
            {"status", "summary", "data", "sources", "effects", "readback", "gaps", "conflicts", "error", "trace"},
        )
        self.assertEqual(payload["gaps"], ["TS 缺失"])


def _manifest(module_id: str, *, effect: str) -> dict:
    return {
        "id": module_id,
        "name": module_id,
        "version": "1.0.0",
        "purpose": "test capability",
        "examples": [],
        "inputs": {},
        "effect": effect,
        "reads": [],
        "writes": [],
        "output_schema": {},
        "source_policy": {},
        "settings": {},
        "dependencies": [],
        "health": {},
        "tests": [],
    }


if __name__ == "__main__":
    unittest.main()
