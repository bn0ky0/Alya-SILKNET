"""Named graph workspaces and their saved entity positions."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from math import isfinite
from uuid import uuid4

from silknet.core.models import GraphBoard
from silknet.database.repositories import GraphLayoutRepository

DEFAULT_WORKSPACE_NAME = "Overview"


class GraphLayoutService:
    def __init__(self, repository: GraphLayoutRepository) -> None:
        self.repository = repository

    # --------------------------------------------------------------- workspaces
    def boards(self) -> list[GraphBoard]:
        return self.repository.list_boards()

    def get_board(self, board_id: str) -> GraphBoard:
        board = self.repository.get_board(board_id)
        if board is None:
            raise LookupError(f"Graph '{board_id}' was not found.")
        return board

    def ensure_workspace(self) -> GraphBoard:
        """Return an existing graph workspace, creating one when none remain."""
        boards = self.boards()
        if boards:
            return boards[0]
        return self.create_board(DEFAULT_WORKSPACE_NAME)

    def create_board(self, name: str) -> GraphBoard:
        cleaned = _clean_name(name)
        if any(board.name.casefold() == cleaned.casefold() for board in self.boards()):
            raise ValueError(f"A graph named '{cleaned}' already exists.")
        now = _now()
        board = GraphBoard(
            id=str(uuid4()),
            name=cleaned,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create_board(board)

    def rename_board(self, board_id: str, name: str) -> GraphBoard:
        board = self.get_board(board_id)
        cleaned = _clean_name(name)
        if any(
            other.id != board.id and other.name.casefold() == cleaned.casefold()
            for other in self.boards()
        ):
            raise ValueError(f"A graph named '{cleaned}' already exists.")
        if not self.repository.rename_board(board.id, cleaned):
            raise LookupError(f"Graph '{board_id}' was not found.")
        return self.get_board(board.id)

    def delete_board(self, board_id: str) -> bool:
        """Delete one graph workspace and keep at least one workspace available."""
        board = self.get_board(board_id)
        if not self.repository.delete_board(board.id):
            raise LookupError(f"Graph '{board_id}' was not found.")
        if not self.boards():
            self.create_board(DEFAULT_WORKSPACE_NAME)
        return True

    # ----------------------------------------------------------------- members
    def board_entity_ids(self, board_id: str) -> set[str]:
        self.get_board(board_id)
        return self.repository.board_entity_ids(board_id)

    def add_entity(
        self,
        board_id: str,
        entity_id: str,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        self.get_board(board_id)
        if not entity_id.strip():
            raise ValueError("An entity ID is required to add a graph node.")
        if (x is not None and not isfinite(x)) or (y is not None and not isfinite(y)):
            raise ValueError("Graph positions must be finite numbers.")
        self.repository.add_board_entity(board_id, entity_id, x, y)

    def remove_entity(
        self,
        board_id: str,
        entity_id: str,
        connection_ids: Iterable[str] = (),
    ) -> bool:
        """Remove a card and remember the claim lines it was showing.

        The relationship claims themselves are workspace records, so they are
        never deleted here. The IDs are saved only for this graph view and are
        used when the user chooses whether to bring the connections back.
        """

        self.get_board(board_id)
        unique_ids = tuple(dict.fromkeys(connection_ids))
        return self.repository.remove_board_entity(board_id, entity_id, unique_ids)

    def hidden_relationship_ids(self, board_id: str) -> set[str]:
        """Claim lines hidden from this graph, including card-only restores."""
        self.get_board(board_id)
        return self.repository.hidden_relationship_ids(board_id)

    def removed_connection_ids(self, board_id: str, entity_id: str) -> set[str]:
        """Old connections saved for a card that is not currently on the graph."""
        self.get_board(board_id)
        return self.repository.hidden_relationship_ids_for_entity(board_id, entity_id)

    def restore_entity_connections(self, board_id: str, entity_id: str) -> int:
        """Make all old connections for a restored card visible again."""
        self.get_board(board_id)
        return self.repository.restore_entity_relationships(board_id, entity_id)

    def restore_relationship(self, board_id: str, relationship_id: str) -> bool:
        """Reveal one claim on a graph without restoring all of a card's links."""
        self.get_board(board_id)
        return self.repository.restore_relationship(board_id, relationship_id)

    # ---------------------------------------------------------------- positions
    def positions(self, board_id: str | None = None) -> dict[str, tuple[float, float]]:
        if board_id is None:
            board_id = self.ensure_workspace().id
        self.get_board(board_id)
        return self.repository.board_positions(board_id)

    def save(
        self,
        entity_id: str,
        x: float,
        y: float,
        board_id: str | None = None,
    ) -> None:
        if not entity_id.strip():
            raise ValueError("An entity ID is required to save a graph position.")
        if not isfinite(x) or not isfinite(y):
            raise ValueError("Graph positions must be finite numbers.")
        if board_id is None:
            board_id = self.ensure_workspace().id
        self.get_board(board_id)
        self.repository.save_board_position(board_id, entity_id, x, y)


def _clean_name(name: str) -> str:
    cleaned = " ".join(str(name).split())
    if not cleaned:
        raise ValueError("Graph name is required.")
    if len(cleaned) > 80:
        raise ValueError("Graph name must be 80 characters or fewer.")
    return cleaned


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
