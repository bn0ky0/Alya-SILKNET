from dataclasses import replace
from math import inf

import pytest

from silknet.core.enums import VerificationStatus
from silknet.graph.model import InvestigationGraph


def test_graph_keeps_direction_and_ignores_missing_endpoints(data_services) -> None:
    source = data_services.entities.create(entity_type="person", name="Source person")
    target = data_services.entities.create(entity_type="organization", name="Target group")
    claim = data_services.relationships.create(
        source_entity_id=source.id,
        target_entity_id=target.id,
        relationship_type="works with",
        verification_status=VerificationStatus.USER_REPORTED,
    )

    orphaned = replace(claim, target_entity_id="missing-entity")
    graph = InvestigationGraph.build(data_services.entities.list(), [claim, orphaned])

    assert [node.entity.id for node in graph.nodes] == [source.id, target.id]
    assert graph.edges[0].relationship.source_entity_id == source.id
    assert graph.edges[0].relationship.target_entity_id == target.id
    assert len(graph.edges) == 1
    assert graph.edges[0].relationship.verification_status is VerificationStatus.USER_REPORTED


def test_graph_node_positions_survive_reloading(data_services) -> None:
    entity = data_services.entities.create(entity_type="person", name="Placed person")
    workspace = data_services.graph_layout.ensure_workspace()
    data_services.graph_layout.save(entity.id, 42.5, -18.25, workspace.id)

    assert data_services.graph_layout.positions(workspace.id)[entity.id] == (42.5, -18.25)


def test_graph_layout_rejects_non_finite_positions(data_services) -> None:
    entity = data_services.entities.create(entity_type="person", name="Position check")
    with pytest.raises(ValueError, match="finite"):
        data_services.graph_layout.save(entity.id, inf, 0)


def test_named_graphs_keep_independent_members_and_positions(data_services) -> None:
    layout = data_services.graph_layout
    first = data_services.entities.create(entity_type="person", name="First person")
    second = data_services.entities.create(entity_type="organization", name="Second group")
    custom = layout.create_board("Project")
    overview = layout.ensure_workspace()

    layout.add_entity(custom.id, first.id, 12.5, -7.0)
    layout.save(first.id, 80.0, 40.0, overview.id)

    assert layout.board_entity_ids(custom.id) == {first.id}
    assert layout.positions(custom.id)[first.id] == (12.5, -7.0)
    assert layout.positions(overview.id)[first.id] == (80.0, 40.0)
    assert layout.positions(custom.id).get(second.id) is None

    layout.save(first.id, 1.0, 2.0, custom.id)
    assert layout.positions(custom.id)[first.id] == (1.0, 2.0)
    assert layout.positions(overview.id)[first.id] == (80.0, 40.0)


def test_graph_workspaces_can_be_deleted_but_one_always_remains(data_services) -> None:
    layout = data_services.graph_layout
    board = layout.create_board("  Project  ")
    assert board.name == "Project"

    with pytest.raises(ValueError, match="already exists"):
        layout.create_board("project")
    renamed = layout.rename_board(board.id, "Research")
    assert renamed.name == "Research"
    with pytest.raises(ValueError, match="already exists"):
        layout.rename_board(layout.ensure_workspace().id, "research")

    assert layout.delete_board(renamed.id)
    assert [item.name for item in layout.boards()] == ["Overview"]

    only_board = layout.ensure_workspace()
    assert layout.delete_board(only_board.id)
    remaining = layout.boards()
    assert len(remaining) == 1
    assert remaining[0].name == "Overview"
    assert remaining[0].id != only_board.id


def test_graph_members_can_be_removed_and_restored_on_any_board(data_services) -> None:
    layout = data_services.graph_layout
    entity = data_services.entities.create(entity_type="person", name="Member")
    board = layout.create_board("Curated")
    layout.add_entity(board.id, entity.id, 0, 0)

    assert layout.remove_entity(board.id, entity.id)
    assert layout.board_entity_ids(board.id) == set()

    overview = layout.ensure_workspace()
    layout.save(entity.id, 18.0, 24.0, overview.id)
    assert layout.remove_entity(overview.id, entity.id)
    assert entity.id not in layout.board_entity_ids(overview.id)
    assert entity.id not in layout.positions(overview.id)

    layout.add_entity(overview.id, entity.id, 30.0, 40.0)
    assert layout.positions(overview.id)[entity.id] == (30.0, 40.0)


def test_graph_removed_card_can_keep_old_connections_hidden(data_services) -> None:
    layout = data_services.graph_layout
    first = data_services.entities.create(entity_type="person", name="First")
    second = data_services.entities.create(entity_type="person", name="Second")
    claim = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    workspace = layout.ensure_workspace()
    layout.save(first.id, 12.0, 18.0, workspace.id)

    assert layout.remove_entity(workspace.id, first.id, {claim.id})
    assert layout.hidden_relationship_ids(workspace.id) == {claim.id}
    assert layout.removed_connection_ids(workspace.id, first.id) == {claim.id}
    layout.add_entity(workspace.id, first.id)
    assert layout.removed_connection_ids(workspace.id, first.id) == {claim.id}

    assert layout.restore_entity_connections(workspace.id, first.id) == 1
    assert layout.removed_connection_ids(workspace.id, first.id) == set()
    assert layout.hidden_relationship_ids(workspace.id) == set()
