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


if __name__ == "__main__":
    unittest.main()
