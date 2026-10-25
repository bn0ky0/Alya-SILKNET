"""SQLite initialization and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from silknet.database.migrations import LATEST_SCHEMA_VERSION, migrate_database

SCHEMA_VERSION = LATEST_SCHEMA_VERSION


def connect(database_file: Path) -> sqlite3.Connection:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_file, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_file: Path) -> None:
    with closing(connect(database_file)) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            migrate_database(connection)
