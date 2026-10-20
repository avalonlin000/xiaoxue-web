from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xiaoxue_api.core.project_identity import load_project_identity


class ProjectIdentityTests(unittest.TestCase):
    def _make_project(self, root: Path) -> None:
        (root / "config" / "agents").mkdir(parents=True)
        (root / "config" / "project-contract.json").write_text(
            json.dumps(
                {
                    "schema": "esports-project-contract-v1",
                    "project_id": "esports-trading",
                    "knowledge_namespace": "小雪电竞",
                    "default_agent_adapter": "xiaoxue",
                    "agent_adapter_dir": "config/agents",
                }
            ),
            encoding="utf-8",
        )
        for agent_id, display_name, namespace in (
            ("xiaoxue", "小雪", "小雪电竞"),
            ("xiaomei", "小美", "小雪电竞"),
        ):
            (root / "config" / "agents" / f"{agent_id}.json").write_text(
                json.dumps(
                    {
                        "schema": "esports-agent-adapter-v1",
                        "agent_id": agent_id,
                        "display_name": display_name,
                        "profile": agent_id,
                    }
                ),
                encoding="utf-8",
            )

    def test_agent_adapter_changes_identity_without_changing_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._make_project(root)
            xiaoxue = load_project_identity(root, "xiaoxue")
            xiaomei = load_project_identity(root, "xiaomei")

        self.assertEqual(xiaoxue.project["project_id"], "esports-trading")
        self.assertEqual(xiaomei.project["project_id"], "esports-trading")
        self.assertEqual(xiaoxue.display_name, "小雪")
        self.assertEqual(xiaomei.display_name, "小美")
        self.assertIn("小雪电竞", xiaoxue.resolve_path_template("/wiki/{knowledge_namespace}/plan.md"))
        self.assertIn("小雪电竞", xiaomei.resolve_path_template("/wiki/{knowledge_namespace}/plan.md"))

    def test_invalid_adapter_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._make_project(root)
            with self.assertRaises(ValueError):
                load_project_identity(root, "../小美")


if __name__ == "__main__":
    unittest.main()
