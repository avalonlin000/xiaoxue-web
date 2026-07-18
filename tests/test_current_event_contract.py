import tempfile
import unittest
from pathlib import Path

from xiaoxue_api.modules.current_event.service import build_current_event


class CurrentEventContractTests(unittest.TestCase):
    def test_missing_plan_is_explicit_instead_of_fabricated(self):
        payload = build_current_event({"event": "EWC 2026", "phase": "当前阶段"}, None)

        self.assertEqual(payload["plan_status"], "not_created")
        self.assertEqual(payload["plan_content"], "")

    def test_existing_plan_is_returned_as_the_full_current_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.md"
            path.write_text("# EWC 交易预案\n\n主要矛盾：跨赛区强弱。", encoding="utf-8")

            payload = build_current_event(
                {"event": "EWC 2026", "phase": "当前阶段"},
                {"content": path.read_text(encoding="utf-8"), "updated_at": "2026-07-18 04:30"},
            )

        self.assertEqual(payload["plan_status"], "ready")
        self.assertEqual(payload["plan_title"], "EWC 交易预案")
        self.assertIn("主要矛盾", payload["plan_content"])


if __name__ == "__main__":
    unittest.main()
