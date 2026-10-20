from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager


DB_PATH = os.environ.get("XIAOXUE_DB_PATH", "/home/ubuntu/lol_data/英雄联盟数据库.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """Open a row-factory connection with commit/rollback/close lifecycle.

    Use this for every read-write repository path: successful exits commit,
    exceptions roll back, and the connection is always closed (avoids leaking
    file descriptors that plain `with connect() as conn` leaves open).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
