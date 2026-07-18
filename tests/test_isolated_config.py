from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest


class IsolatedConfigTests(unittest.TestCase):
    def test_one_bad_module_config_does_not_hide_other_module_configs(self) -> None:
        from xiaoxue_api.core.config_loader import load_isolated_configs

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "daily_content").mkdir()
            (root / "lineup").mkdir()
            (root / "daily_content" / "config.json").write_text(
                json.dumps({"daily_content": {"artifacts": []}}), encoding="utf-8"
            )
            (root / "lineup" / "config.json").write_text("{bad json", encoding="utf-8")

            loaded = load_isolated_configs(root)

        self.assertIn("daily_content", loaded.config)
        self.assertEqual(loaded.modules["daily_content"]["status"], "healthy")
        self.assertEqual(loaded.modules["lineup"]["status"], "broken")


if __name__ == "__main__":
    unittest.main()
