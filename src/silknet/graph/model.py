"""A view-friendly graph built from saved SILKNET entities and claims."""

from __future__ import annotations

from dataclasses import dataclass

from silknet.core.models import Entity, Relationship


@dataclass(frozen=True, slots=True)
class GraphNode:
    entity: Entity


@dataclass(frozen=True, slots=True)
class GraphEdge:
    relationship: Relationship


@dataclass(frozen=True, slots=True)
class InvestigationGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @classmethod
    def build(cls, entities: list[Entity], relationships: list[Relationship]) -> InvestigationGraph:
        entity_ids = {entity.id for entity in entities}
        return cls(
            nodes=tuple(GraphNode(entity) for entity in entities),
            edges=tuple(
                GraphEdge(relationship)
                for relationship in relationships
                if relationship.source_entity_id in entity_ids
                and relationship.target_entity_id in entity_ids
            ),
        )
