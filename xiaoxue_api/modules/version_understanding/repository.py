from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from xiaoxue_api.core.database import DB_PATH as DEFAULT_DB_PATH


UNIFIED_VERSION_ID = 229
VERSION_SOURCE_CATEGORY = "版本理解"


def get_unified_version_understanding() -> dict | None:
    """Read the one confirmed global object without falling back to other rows."""

    database_path = Path(os.environ.get("XIAOXUE_DB_PATH", DEFAULT_DB_PATH))
    if not database_path.exists():
        return None
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT id, topic, content, created_at, content_type
               FROM shared_version_analysis
               WHERE id = ? AND source_category = ?
               LIMIT 1""",
            (UNIFIED_VERSION_ID, VERSION_SOURCE_CATEGORY),
        ).fetchone()
    finally:
        connection.close()
    return dict(row) if row else None
