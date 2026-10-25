"""SQLite repositories that translate domain records to stored rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from silknet.core.enums import SourceType, VerificationStatus
from silknet.core.models import (
    CustomEntityType,
    Entity,
    GraphBoard,
    Relationship,
    Source,
)
from silknet.database.connection import connect


@contextmanager
def _transaction(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(connect(database_file)) as connection:
        with connection:
            yield connection


class EntityRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file

    def create(self, entity: Entity) -> Entity:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO entities
                   (id, entity_type, name, description, aliases_json, attributes_json,
                    tags_json, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity.id,
                    entity.entity_type,
                    entity.name,
                    entity.description,
                    _dump(list(entity.aliases)),
                    _dump(entity.attributes),
                    _dump(list(entity.tags)),
                    entity.notes,
                    entity.created_at,
                    entity.updated_at,
                ),
            )
            _replace_entity_sources(connection, entity.id, entity.source_ids, entity.created_at)
        return entity

    def get(self, entity_id: str) -> Entity | None:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if row is None:
                return None
            sources = connection.execute(
                "SELECT source_id FROM entity_sources WHERE entity_id = ? ORDER BY source_id",
                (entity_id,),
            ).fetchall()
            return _entity_from_row(row, tuple(source["source_id"] for source in sources))

    def list(self) -> list[Entity]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                "SELECT * FROM entities ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
            source_rows = connection.execute(
                "SELECT entity_id, source_id FROM entity_sources ORDER BY entity_id, source_id"
            ).fetchall()
            sources_by_entity: dict[str, list[str]] = {}
            for source in source_rows:
                sources_by_entity.setdefault(source["entity_id"], []).append(source["source_id"])
            return [
                _entity_from_row(row, tuple(sources_by_entity.get(row["id"], ()))) for row in rows
            ]

    def update(self, entity: Entity) -> Entity | None:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                """UPDATE entities SET entity_type = ?, name = ?, description = ?,
                   aliases_json = ?, attributes_json = ?, tags_json = ?, notes = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    entity.entity_type,
                    entity.name,
                    entity.description,
                    _dump(list(entity.aliases)),
                    _dump(entity.attributes),
                    _dump(list(entity.tags)),
                    entity.notes,
                    entity.updated_at,
                    entity.id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute("DELETE FROM entity_sources WHERE entity_id = ?", (entity.id,))
            _replace_entity_sources(connection, entity.id, entity.source_ids, entity.updated_at)
        return entity

    def delete(self, entity_id: str) -> bool:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            return cursor.rowcount > 0

    def get_custom_type(self, type_key: str) -> CustomEntityType | None:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute(
                "SELECT * FROM custom_entity_types WHERE type_key = ?", (type_key,)
            ).fetchone()
            return _custom_entity_type_from_row(row) if row else None

    def list_custom_types(self) -> list[CustomEntityType]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                "SELECT * FROM custom_entity_types ORDER BY display_name COLLATE NOCASE"
            ).fetchall()
            return [_custom_entity_type_from_row(row) for row in rows]

    def create_custom_type(self, entity_type: CustomEntityType) -> CustomEntityType:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO custom_entity_types
                   (type_key, display_name, fields_json, created_at) VALUES (?, ?, ?, ?)""",
                (
                    entity_type.key,
                    entity_type.display_name,
                    _dump(list(entity_type.fields)),
                    entity_type.created_at,
                ),
            )
        return entity_type


class RelationshipRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file

    def create(self, relationship: Relationship) -> Relationship:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO relationships
                   (id, source_entity_id, target_entity_id, relationship_type, description,
                    start_date, end_date, verification_status, confidence_notes, notes,
                    created_at, relationship_domain)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relationship.id,
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                    relationship.relationship_type,
                    relationship.description,
                    relationship.start_date,
                    relationship.end_date,
                    relationship.verification_status.value,
                    relationship.confidence_notes,
                    relationship.notes,
                    relationship.created_at,
                    relationship.relationship_domain,
                ),
            )
            _replace_relationship_sources(connection, relationship.id, relationship.source_ids)
        return relationship

    def get(self, relationship_id: str) -> Relationship | None:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute(
                "SELECT * FROM relationships WHERE id = ?", (relationship_id,)
            ).fetchone()
            if row is None:
                return None
            sources = connection.execute(
                """SELECT source_id FROM relationship_sources WHERE relationship_id = ?
                   ORDER BY source_id""",
                (relationship_id,),
            ).fetchall()
            return _relationship_from_row(row, tuple(source["source_id"] for source in sources))

    def list(self) -> list[Relationship]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                "SELECT * FROM relationships ORDER BY created_at, id"
            ).fetchall()
            source_rows = connection.execute(
                """SELECT relationship_id, source_id FROM relationship_sources
                   ORDER BY relationship_id, source_id"""
            ).fetchall()
            sources_by_relationship: dict[str, list[str]] = {}
            for source in source_rows:
                sources_by_relationship.setdefault(source["relationship_id"], []).append(
                    source["source_id"]
                )
            return [
                _relationship_from_row(row, tuple(sources_by_relationship.get(row["id"], ())))
                for row in rows
            ]

    def update(self, relationship: Relationship) -> Relationship | None:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                """UPDATE relationships SET source_entity_id = ?, target_entity_id = ?,
                   relationship_type = ?, description = ?, start_date = ?, end_date = ?,
                   verification_status = ?, confidence_notes = ?, notes = ?,
                   relationship_domain = ? WHERE id = ?""",
                (
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                    relationship.relationship_type,
                    relationship.description,
                    relationship.start_date,
                    relationship.end_date,
                    relationship.verification_status.value,
                    relationship.confidence_notes,
                    relationship.notes,
                    relationship.relationship_domain,
                    relationship.id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                "DELETE FROM relationship_sources WHERE relationship_id = ?",
                (relationship.id,),
            )
            _replace_relationship_sources(connection, relationship.id, relationship.source_ids)
        return relationship

    def delete(self, relationship_id: str) -> bool:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                "DELETE FROM relationships WHERE id = ?", (relationship_id,)
            )
            return cursor.rowcount > 0


class SourceRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file

    def create(self, source: Source) -> Source:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO sources
                   (id, title, source_type, url, local_path, observed_at, notes,
                    content_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.id,
                    source.title,
                    source.source_type.value,
                    source.url,
                    source.local_path,
                    source.observed_at,
                    source.notes,
                    source.content_hash,
                    source.created_at,
                ),
            )
        return source

    def get(self, source_id: str) -> Source | None:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            return _source_from_row(row) if row else None

    def list(self) -> list[Source]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                "SELECT * FROM sources ORDER BY title COLLATE NOCASE"
            ).fetchall()
            return [_source_from_row(row) for row in rows]

    def update(self, source: Source) -> Source | None:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                """UPDATE sources SET title = ?, source_type = ?, url = ?, local_path = ?,
                   observed_at = ?, notes = ?, content_hash = ? WHERE id = ?""",
                (
                    source.title,
                    source.source_type.value,
                    source.url,
                    source.local_path,
                    source.observed_at,
                    source.notes,
                    source.content_hash,
                    source.id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return source

    def delete(self, source_id: str) -> bool:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            return cursor.rowcount > 0


class GraphLayoutRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file

    def list_boards(self) -> list[GraphBoard]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                """SELECT * FROM graph_boards
                   ORDER BY name COLLATE NOCASE, created_at"""
            ).fetchall()
            return [_graph_board_from_row(row) for row in rows]

    def get_board(self, board_id: str) -> GraphBoard | None:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute(
                "SELECT * FROM graph_boards WHERE id = ?", (board_id,)
            ).fetchone()
            return _graph_board_from_row(row) if row else None

    def create_board(self, board: GraphBoard) -> GraphBoard:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO graph_boards
                   (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)""",
                (board.id, board.name, board.created_at, board.updated_at),
            )
        return board

    def rename_board(self, board_id: str, name: str) -> bool:
        timestamp = datetime.now(UTC).isoformat(timespec="microseconds")
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                "UPDATE graph_boards SET name = ?, updated_at = ? WHERE id = ?",
                (name, timestamp, board_id),
            )
            return cursor.rowcount > 0

    def delete_board(self, board_id: str) -> bool:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute("DELETE FROM graph_boards WHERE id = ?", (board_id,))
            return cursor.rowcount > 0

    def list_board_nodes(self, board_id: str) -> list[tuple[str, float | None, float | None]]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                """SELECT entity_id, x, y FROM graph_board_nodes
                   WHERE board_id = ? ORDER BY entity_id""",
                (board_id,),
            ).fetchall()
            return [(row["entity_id"], row["x"], row["y"]) for row in rows]

    def board_positions(self, board_id: str) -> dict[str, tuple[float, float]]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                """SELECT entity_id, x, y FROM graph_board_nodes
                   WHERE board_id = ? AND x IS NOT NULL AND y IS NOT NULL""",
                (board_id,),
            ).fetchall()
            return {row["entity_id"]: (row["x"], row["y"]) for row in rows}

    def board_entity_ids(self, board_id: str) -> set[str]:
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                "SELECT entity_id FROM graph_board_nodes WHERE board_id = ?",
                (board_id,),
            ).fetchall()
            return {row["entity_id"] for row in rows}

    def hidden_relationship_ids(self, board_id: str) -> set[str]:
        """Claim lines the user chose not to show on this graph view."""
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                """SELECT relationship_id FROM graph_board_hidden_relationships
                   WHERE board_id = ?""",
                (board_id,),
            ).fetchall()
            return {row["relationship_id"] for row in rows}

    def hidden_relationship_ids_for_entity(self, board_id: str, entity_id: str) -> set[str]:
        """Saved connections that would return with a removed card."""
        with closing(connect(self.database_file)) as connection:
            rows = connection.execute(
                """SELECT hidden.relationship_id
                   FROM graph_board_hidden_relationships AS hidden
                   JOIN relationships AS claim
                     ON claim.id = hidden.relationship_id
                   WHERE hidden.board_id = ?
                     AND (claim.source_entity_id = ? OR claim.target_entity_id = ?)""",
                (board_id, entity_id, entity_id),
            ).fetchall()
            return {row["relationship_id"] for row in rows}

    def restore_entity_relationships(self, board_id: str, entity_id: str) -> int:
        """Make every saved connection for one card visible again."""
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                """DELETE FROM graph_board_hidden_relationships
                   WHERE board_id = ?
                     AND relationship_id IN (
                         SELECT id FROM relationships
                         WHERE source_entity_id = ? OR target_entity_id = ?
                     )""",
                (board_id, entity_id, entity_id),
            )
            return cursor.rowcount

    def restore_relationship(self, board_id: str, relationship_id: str) -> bool:
        """Reveal one claim line without touching the other hidden lines."""
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                """DELETE FROM graph_board_hidden_relationships
                   WHERE board_id = ? AND relationship_id = ?""",
                (board_id, relationship_id),
            )
            return cursor.rowcount > 0

    def add_board_entity(
        self,
        board_id: str,
        entity_id: str,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        if (x is None) != (y is None):
            raise ValueError("Graph positions require both x and y.")
        timestamp = datetime.now(UTC).isoformat(timespec="microseconds")
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO graph_board_nodes
                   (board_id, entity_id, x, y, updated_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(board_id, entity_id) DO UPDATE SET
                       x = COALESCE(excluded.x, graph_board_nodes.x),
                       y = COALESCE(excluded.y, graph_board_nodes.y),
                       updated_at = excluded.updated_at""",
                (board_id, entity_id, x, y, timestamp),
            )
            connection.execute(
                "UPDATE graph_boards SET updated_at = ? WHERE id = ?",
                (timestamp, board_id),
            )

    def save_board_position(self, board_id: str, entity_id: str, x: float, y: float) -> None:
        if not isfinite(x) or not isfinite(y):
            raise ValueError("Graph positions must be finite numbers.")
        self.add_board_entity(board_id, entity_id, x, y)

    def remove_board_entity(
        self,
        board_id: str,
        entity_id: str,
        relationship_ids: Iterable[str] = (),
    ) -> bool:
        with _transaction(self.database_file) as connection:
            cursor = connection.execute(
                "DELETE FROM graph_board_nodes WHERE board_id = ? AND entity_id = ?",
                (board_id, entity_id),
            )
            if cursor.rowcount:
                _remember_hidden_relationships(connection, board_id, relationship_ids)
            return cursor.rowcount > 0


class PlatformRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file

    def list_custom(self) -> list[str]:
        with closing(connect(self.database_file)) as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", ("custom_platforms",)
            ).fetchone()
            if row is None:
                return []
            try:
                value = json.loads(row["value"])
            except json.JSONDecodeError:
                return []
            return (
                [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
            )

    def save_custom(self, platforms: list[str]) -> None:
        with _transaction(self.database_file) as connection:
            connection.execute(
                """INSERT INTO app_metadata (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                ("custom_platforms", _dump(platforms)),
            )


def _remember_hidden_relationships(
    connection: sqlite3.Connection,
    board_id: str,
    relationship_ids: Iterable[str],
) -> None:
    """Keep old claim lines out of a graph until the user asks for them."""
    connection.executemany(
        """INSERT OR IGNORE INTO graph_board_hidden_relationships
           (board_id, relationship_id) VALUES (?, ?)""",
        [(board_id, relationship_id) for relationship_id in relationship_ids],
    )


def _replace_entity_sources(
    connection: sqlite3.Connection,
    entity_id: str,
    source_ids: tuple[str, ...],
    linked_at: str,
) -> None:
    connection.executemany(
        "INSERT INTO entity_sources (entity_id, source_id, linked_at) VALUES (?, ?, ?)",
        [(entity_id, source_id, linked_at) for source_id in source_ids],
    )


def _replace_relationship_sources(
    connection: sqlite3.Connection,
    relationship_id: str,
    source_ids: tuple[str, ...],
) -> None:
    connection.executemany(
        "INSERT INTO relationship_sources (relationship_id, source_id) VALUES (?, ?)",
        [(relationship_id, source_id) for source_id in source_ids],
    )


def _entity_from_row(row: sqlite3.Row, source_ids: tuple[str, ...]) -> Entity:
    return Entity(
        id=row["id"],
        entity_type=row["entity_type"],
        name=row["name"],
        description=row["description"],
        aliases=tuple(json.loads(row["aliases_json"])),
        attributes=json.loads(row["attributes_json"]),
        tags=tuple(json.loads(row["tags_json"])),
        notes=row["notes"],
        source_ids=source_ids,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _relationship_from_row(row: sqlite3.Row, source_ids: tuple[str, ...]) -> Relationship:
    return Relationship(
        id=row["id"],
        source_entity_id=row["source_entity_id"],
        target_entity_id=row["target_entity_id"],
        relationship_type=row["relationship_type"],
        description=row["description"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        verification_status=VerificationStatus(row["verification_status"]),
        confidence_notes=row["confidence_notes"],
        notes=row["notes"],
        source_ids=source_ids,
        created_at=row["created_at"],
        relationship_domain=row["relationship_domain"],
    )


def _source_from_row(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        title=row["title"],
        source_type=SourceType(row["source_type"]),
        url=row["url"],
        local_path=row["local_path"],
        observed_at=row["observed_at"],
        notes=row["notes"],
        content_hash=row["content_hash"],
        created_at=row["created_at"],
    )


def _custom_entity_type_from_row(row: sqlite3.Row) -> CustomEntityType:
    return CustomEntityType(
        key=row["type_key"],
        display_name=row["display_name"],
        fields=tuple(json.loads(row["fields_json"])),
        created_at=row["created_at"],
    )


def _graph_board_from_row(row: sqlite3.Row) -> GraphBoard:
    return GraphBoard(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
