from __future__ import annotations

import os
import sqlite3


DB_PATH = os.environ.get("XIAOXUE_DB_PATH", "/home/ubuntu/lol_data/英雄联盟数据库.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
