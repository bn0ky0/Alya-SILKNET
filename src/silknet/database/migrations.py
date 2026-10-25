"""Transactional, ordered SQLite schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from silknet.core.exceptions import MigrationError

LATEST_SCHEMA_VERSION = 8


def _create_record_tables(connection: sqlite3.Connection) -> None:
    schema = """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            description TEXT NOT NULL DEFAULT '',
            aliases_json TEXT NOT NULL DEFAULT '[]',
            attributes_json TEXT NOT NULL DEFAULT '{}',
            tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE custom_entity_types (
            type_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL UNIQUE,
            fields_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL CHECK (length(trim(title)) > 0),
            source_type TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            local_path TEXT NOT NULL DEFAULT '',
            observed_at TEXT,
            notes TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE relationships (
            id TEXT PRIMARY KEY,
            source_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            target_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            relationship_type TEXT NOT NULL CHECK (length(trim(relationship_type)) > 0),
            description TEXT NOT NULL DEFAULT '',
            start_date TEXT,
            end_date TEXT,
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            confidence_notes TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            CHECK (source_entity_id <> target_entity_id),
            CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
        );

        CREATE TABLE entity_sources (
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            linked_at TEXT NOT NULL,
            PRIMARY KEY (entity_id, source_id)
        );

        CREATE TABLE relationship_sources (
            relationship_id TEXT NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            PRIMARY KEY (relationship_id, source_id)
        );

        CREATE INDEX idx_entities_name ON entities(name COLLATE NOCASE);
        CREATE INDEX idx_entities_type ON entities(entity_type);
        CREATE INDEX idx_relationships_source ON relationships(source_entity_id);
        CREATE INDEX idx_relationships_target ON relationships(target_entity_id);
        CREATE INDEX idx_relationships_type ON relationships(relationship_type);
        CREATE INDEX idx_sources_title ON sources(title COLLATE NOCASE);
        """
    for statement in schema.split(";"):
        if statement.strip():
            connection.execute(statement)


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _create_graph_layout(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE entity_graph_positions (
            entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
            x REAL NOT NULL,
            y REAL NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )


def _add_relationship_domain(connection: sqlite3.Connection) -> None:
    connection.execute(
        """ALTER TABLE relationships ADD COLUMN relationship_domain TEXT NOT NULL
           DEFAULT 'general' CHECK (relationship_domain IN ('general', 'family'))"""
    )


def _create_graph_boards(connection: sqlite3.Connection) -> None:
    """Introduce named graph views and preserve the old default layout."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS graph_boards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS graph_board_nodes (
            board_id TEXT NOT NULL REFERENCES graph_boards(id) ON DELETE CASCADE,
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            x REAL,
            y REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (board_id, entity_id)
        )"""
    )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_boards_default
           ON graph_boards(is_default) WHERE is_default = 1"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_graph_board_nodes_entity
           ON graph_board_nodes(entity_id)"""
    )

    timestamp = datetime.now(UTC).isoformat(timespec="microseconds")
    connection.execute(
        """INSERT OR IGNORE INTO graph_boards
           (id, name, is_default, created_at, updated_at) VALUES (?, ?, 1, ?, ?)""",
        ("graph-default", "All entities", timestamp, timestamp),
    )
    connection.execute(
        """INSERT OR IGNORE INTO graph_board_nodes
           (board_id, entity_id, x, y, updated_at)
           SELECT ?, entity_id, x, y, ? FROM entity_graph_positions""",
        ("graph-default", timestamp),
    )


def _create_graph_board_exclusions(connection: sqlite3.Connection) -> None:
    """Let the all-entities graph hide cards without deleting records."""

    connection.execute(
        """CREATE TABLE IF NOT EXISTS graph_board_exclusions (
            board_id TEXT NOT NULL REFERENCES graph_boards(id) ON DELETE CASCADE,
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            PRIMARY KEY (board_id, entity_id)
        )"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_graph_board_exclusions_entity
           ON graph_board_exclusions(entity_id)"""
    )


def _create_graph_board_hidden_relationships(connection: sqlite3.Connection) -> None:
    """Remember the connections a card had when it left a graph.

    Removing a card should not remove the underlying relationship claims. The
    graph only remembers which claim lines were visible at that moment so the
    user can decide whether those lines return with the card.
    """

    connection.execute(
        """CREATE TABLE IF NOT EXISTS graph_board_hidden_relationships (
            board_id TEXT NOT NULL REFERENCES graph_boards(id) ON DELETE CASCADE,
            relationship_id TEXT NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
            PRIMARY KEY (board_id, relationship_id)
        )"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_graph_hidden_relationships_claim
           ON graph_board_hidden_relationships(relationship_id)"""
    )


def _make_graph_workspaces_regular(connection: sqlite3.Connection) -> None:
    """Turn the old all-entities graph into an ordinary, deletable workspace.

    The old board implicitly showed every entity that was not excluded. The
    conversion materializes that visible membership so the board keeps the same
    cards, then removes the default flag and the exclusion table.
    """

    timestamp = datetime.now(UTC).isoformat(timespec="microseconds")
    default_row = connection.execute(
        """SELECT id, name FROM graph_boards
           WHERE is_default = 1 ORDER BY created_at LIMIT 1"""
    ).fetchone()
    if default_row is not None:
        board_id = default_row["id"]
        connection.execute(
            """DELETE FROM graph_board_nodes
               WHERE board_id = ?
                 AND entity_id IN (
                     SELECT entity_id FROM graph_board_exclusions WHERE board_id = ?
                 )""",
            (board_id, board_id),
        )
        connection.execute(
            """INSERT OR IGNORE INTO graph_board_nodes
               (board_id, entity_id, x, y, updated_at)
               SELECT ?, entity.id, saved.x, saved.y, ?
               FROM entities AS entity
               LEFT JOIN graph_board_nodes AS saved
                 ON saved.board_id = ? AND saved.entity_id = entity.id
               WHERE NOT EXISTS (
                   SELECT 1 FROM graph_board_exclusions AS hidden
                   WHERE hidden.board_id = ? AND hidden.entity_id = entity.id
               )""",
            (board_id, timestamp, board_id, board_id),
        )
        if default_row["name"].casefold() == "all entities":
            connection.execute(
                "UPDATE graph_boards SET name = ?, updated_at = ? WHERE id = ?",
                (_unique_graph_name(connection, "Overview"), timestamp, board_id),
            )

    connection.execute("UPDATE graph_boards SET is_default = 0")
    connection.execute("DROP INDEX IF EXISTS idx_graph_boards_default")
    connection.execute("ALTER TABLE graph_boards DROP COLUMN is_default")
    connection.execute("DROP TABLE IF EXISTS graph_board_exclusions")

    if connection.execute("SELECT 1 FROM graph_boards LIMIT 1").fetchone() is None:
        connection.execute(
            """INSERT INTO graph_boards (id, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (str(uuid4()), "Overview", timestamp, timestamp),
        )


def _unique_graph_name(connection: sqlite3.Connection, preferred: str) -> str:
    candidate = preferred
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM graph_boards WHERE name = ? COLLATE NOCASE", (candidate,)
    ).fetchone():
        candidate = f"{preferred} {suffix}"
        suffix += 1
    return candidate


MIGRATIONS = (
    Migration(2, "create_records", _create_record_tables),
    Migration(3, "save_graph_layout", _create_graph_layout),
    Migration(4, "classify_relationships", _add_relationship_domain),
    Migration(5, "create_graph_boards", _create_graph_boards),
    Migration(6, "hide_cards_from_graphs", _create_graph_board_exclusions),
    Migration(7, "remember_card_connections", _create_graph_board_hidden_relationships),
    Migration(8, "make_graph_workspaces_regular", _make_graph_workspaces_regular),
)


def migrate_database(connection: sqlite3.Connection) -> None:
    """Apply any schema changes this database still needs."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    metadata_row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = ?", ("schema_version",)
    ).fetchone()
    pragma_version = int(connection.execute("PRAGMA user_version").fetchone()[0])

    if metadata_row is None:
        current_version = pragma_version or 1
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            ("schema_version", str(current_version)),
        )
    else:
        try:
            metadata_version = int(metadata_row["value"])
        except (TypeError, ValueError) as exc:
            raise MigrationError("Database schema version metadata is invalid.") from exc
        if pragma_version and pragma_version != metadata_version:
            raise MigrationError(
                "Database schema version markers disagree; no migration was applied."
            )
        current_version = metadata_version or pragma_version or 1

    if current_version > LATEST_SCHEMA_VERSION:
        raise MigrationError(
            "This database was created by a newer SILKNET version and cannot be opened safely."
        )
    if current_version < 1:
        raise MigrationError("Database schema version is invalid; no migration was applied.")

    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        try:
            migration.apply(connection)
        except sqlite3.DatabaseError as exc:
            raise MigrationError(
                f"Could not apply database migration {migration.version} ({migration.name}): {exc}"
            ) from exc
        current_version = migration.version
        connection.execute(
            "UPDATE app_metadata SET value = ? WHERE key = ?",
            (str(current_version), "schema_version"),
        )
        connection.execute(f"PRAGMA user_version = {current_version}")
