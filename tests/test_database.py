import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from silknet.core.exceptions import MigrationError
from silknet.database.connection import SCHEMA_VERSION, connect, initialize_database
from silknet.database.repositories import (
    EntityRepository,
    GraphLayoutRepository,
    RelationshipRepository,
    SourceRepository,
)
from silknet.services.entity_service import EntityService
from silknet.services.graph_layout_service import GraphLayoutService
from silknet.services.relationship_service import RelationshipService


def test_database_initialization_is_safe_and_idempotent(tmp_path: Path) -> None:
    database_file = tmp_path / "nested" / "silknet.sqlite3"

    initialize_database(database_file)
    initialize_database(database_file)

    with closing(connect(database_file)) as connection:
        metadata = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", ("schema_version",)
        ).fetchone()
        assert metadata["value"] == str(SCHEMA_VERSION)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'entities'"
            ).fetchone()[0]
            == "entities"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'graph_boards'"
            ).fetchone()[0]
            == "graph_boards"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'graph_board_exclusions'"
            ).fetchone()
            is None
        )
        board_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(graph_boards)")
        }
        assert "is_default" not in board_columns
        assert connection.execute("SELECT count(*) FROM graph_boards").fetchone()[0] == 1


def test_database_uses_sqlite_file(tmp_path: Path) -> None:
    database_file = tmp_path / "silknet.sqlite3"
    initialize_database(database_file)

    assert database_file.is_file()
    with sqlite3.connect(database_file) as connection:
        assert connection.execute("SELECT count(*) FROM app_metadata").fetchone()[0] == 1


def test_phase_one_database_migrates_without_dropping_existing_data(tmp_path: Path) -> None:
    database_file = tmp_path / "phase-one.sqlite3"
    with sqlite3.connect(database_file) as connection:
        connection.execute("CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)", ("schema_version", "1")
        )
        connection.execute("CREATE TABLE legacy_record (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_record (value) VALUES (?)", ("preserve me",))
        connection.execute("PRAGMA user_version = 1")

    initialize_database(database_file)

    with closing(connect(database_file)) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", ("schema_version",)
        ).fetchone()[0]
        assert version == str(SCHEMA_VERSION)
        assert connection.execute("SELECT value FROM legacy_record").fetchone()[0] == "preserve me"


def test_newer_database_schema_is_refused_without_modification(tmp_path: Path) -> None:
    database_file = tmp_path / "future.sqlite3"
    with sqlite3.connect(database_file) as connection:
        connection.execute("CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)", ("schema_version", "99")
        )
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(MigrationError, match="newer SILKNET version"):
        initialize_database(database_file)


def test_schema_three_migrates_relationship_domain_without_losing_claims(tmp_path: Path) -> None:
    database_file = tmp_path / "schema-three.sqlite3"
    initialize_database(database_file)
    entities_repository = EntityRepository(database_file)
    sources_repository = SourceRepository(database_file)
    entity_service = EntityService(entities_repository, sources_repository)
    relationship_service = RelationshipService(
        RelationshipRepository(database_file), entities_repository, sources_repository
    )
    source = entity_service.create(entity_type="person", name="Source")
    target = entity_service.create(entity_type="person", name="Target")
    claim = relationship_service.create(
        source_entity_id=source.id,
        target_entity_id=target.id,
        relationship_type="related to",
    )
    with closing(connect(database_file)) as connection:
        with connection:
            connection.execute("ALTER TABLE relationships DROP COLUMN relationship_domain")
            connection.execute("DROP TABLE graph_board_hidden_relationships")
            connection.execute("DROP TABLE graph_board_nodes")
            connection.execute("DROP TABLE IF EXISTS graph_board_exclusions")
            connection.execute("DROP TABLE graph_boards")
            connection.execute("UPDATE app_metadata SET value = '3' WHERE key = 'schema_version'")
            connection.execute("PRAGMA user_version = 3")

    initialize_database(database_file)

    migrated = relationship_service.get(claim.id)
    assert migrated.relationship_domain == "general"
    assert migrated.source_entity_id == source.id


def test_schema_four_positions_move_into_a_regular_graph_workspace(tmp_path: Path) -> None:
    database_file = tmp_path / "schema-four.sqlite3"
    initialize_database(database_file)
    entities_repository = EntityRepository(database_file)
    sources_repository = SourceRepository(database_file)
    entity_service = EntityService(entities_repository, sources_repository)
    entity = entity_service.create(entity_type="person", name="Legacy placement")

    with closing(connect(database_file)) as connection:
        with connection:
            connection.execute(
                """INSERT INTO entity_graph_positions
                   (entity_id, x, y, updated_at) VALUES (?, ?, ?, ?)""",
                (entity.id, 42.5, -18.25, "2026-10-19T00:00:00+00:00"),
            )
            connection.execute("DROP TABLE graph_board_hidden_relationships")
            connection.execute("DROP TABLE graph_board_nodes")
            connection.execute("DROP TABLE IF EXISTS graph_board_exclusions")
            connection.execute("DROP TABLE graph_boards")
            connection.execute("UPDATE app_metadata SET value = '4' WHERE key = 'schema_version'")
            connection.execute("PRAGMA user_version = 4")

    initialize_database(database_file)

    layout = GraphLayoutRepository(database_file)
    boards = layout.list_boards()
    assert len(boards) == 1
    assert boards[0].name == "Overview"
    assert layout.board_positions(boards[0].id)[entity.id] == (42.5, -18.25)


def test_schema_seven_converts_default_graph_to_a_regular_workspace(tmp_path: Path) -> None:
    database_file = tmp_path / "schema-seven.sqlite3"
    initialize_database(database_file)
    entities = EntityRepository(database_file)
    sources = SourceRepository(database_file)
    entity_service = EntityService(entities, sources)
    visible = entity_service.create(entity_type="person", name="Visible card")
    hidden = entity_service.create(entity_type="person", name="Hidden card")
    layout = GraphLayoutRepository(database_file)
    board = layout.list_boards()[0]
    layout.add_board_entity(board.id, visible.id, 4.0, 8.0)

    with closing(connect(database_file)) as connection:
        with connection:
            _restore_legacy_default_board(connection, board.id)
            connection.execute(
                "INSERT INTO graph_board_exclusions (board_id, entity_id) VALUES (?, ?)",
                (board.id, hidden.id),
            )
            connection.execute("UPDATE app_metadata SET value = '7' WHERE key = 'schema_version'")
            connection.execute("PRAGMA user_version = 7")

    initialize_database(database_file)

    layout = GraphLayoutRepository(database_file)
    boards = layout.list_boards()
    assert len(boards) == 1
    assert boards[0].name == "Overview"
    assert layout.board_entity_ids(boards[0].id) == {visible.id}
    assert layout.board_positions(boards[0].id)[visible.id] == (4.0, 8.0)
    with closing(connect(database_file)) as connection:
        board_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(graph_boards)")
        }
        assert "is_default" not in board_columns
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'graph_board_exclusions'"
            ).fetchone()
            is None
        )
    replacement = GraphLayoutService(layout)
    assert replacement.delete_board(boards[0].id)
    assert [item.name for item in replacement.boards()] == ["Overview"]


def test_schema_six_adds_remembered_card_connections(tmp_path: Path) -> None:
    database_file = tmp_path / "schema-six.sqlite3"
    initialize_database(database_file)
    entities = EntityRepository(database_file)
    sources = SourceRepository(database_file)
    entity_service = EntityService(entities, sources)
    relationship_service = RelationshipService(
        RelationshipRepository(database_file), entities, sources
    )
    first = entity_service.create(entity_type="person", name="First")
    second = entity_service.create(entity_type="person", name="Second")
    claim = relationship_service.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    layout = GraphLayoutRepository(database_file)
    board = layout.list_boards()[0]
    layout.add_board_entity(board.id, first.id, 4.0, 8.0)

    with closing(connect(database_file)) as connection:
        with connection:
            connection.execute("DROP TABLE graph_board_hidden_relationships")
            _restore_legacy_default_board(connection, board.id)
            connection.execute("UPDATE app_metadata SET value = '6' WHERE key = 'schema_version'")
            connection.execute("PRAGMA user_version = 6")

    initialize_database(database_file)

    layout = GraphLayoutRepository(database_file)
    board = layout.list_boards()[0]
    assert layout.hidden_relationship_ids(board.id) == set()
    assert layout.remove_board_entity(board.id, first.id, {claim.id})
    assert layout.hidden_relationship_ids(board.id) == {claim.id}
    assert layout.hidden_relationship_ids_for_entity(board.id, first.id) == {claim.id}
    assert layout.restore_entity_relationships(board.id, first.id) == 1
    assert layout.hidden_relationship_ids(board.id) == set()


def _restore_legacy_default_board(connection: sqlite3.Connection, board_id: str) -> None:
    """Recreate the version-7 default-board shape for migration tests."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(graph_boards)")}
    if "is_default" not in columns:
        connection.execute(
            "ALTER TABLE graph_boards ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
        )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_boards_default
           ON graph_boards(is_default) WHERE is_default = 1"""
    )
    connection.execute(
        "UPDATE graph_boards SET name = ?, is_default = 1 WHERE id = ?",
        ("All entities", board_id),
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS graph_board_exclusions (
            board_id TEXT NOT NULL REFERENCES graph_boards(id) ON DELETE CASCADE,
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            PRIMARY KEY (board_id, entity_id)
        )"""
    )
