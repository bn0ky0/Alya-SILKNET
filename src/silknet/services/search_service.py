"""Local full-text search over the records already saved in this workspace."""

from __future__ import annotations

from dataclasses import dataclass

from silknet.services.entity_service import EntityService
from silknet.services.relationship_service import RelationshipService
from silknet.services.source_service import SourceService


@dataclass(frozen=True, slots=True)
class SearchResult:
    kind: str
    record_id: str
    title: str
    summary: str


class SearchService:
    def __init__(
        self,
        entities: EntityService,
        relationships: RelationshipService,
        sources: SourceService,
    ) -> None:
        self.entities = entities
        self.relationships = relationships
        self.sources = sources

    def search(
        self,
        query: str,
        *,
        result_kind: str = "all",
        entity_type: str = "",
        verification_status: str = "",
        tag: str = "",
    ) -> list[SearchResult]:
        needle = query.strip().casefold()
        tag_filter = tag.strip().casefold()
        entities = self.entities.list()
        names = {entity.id: entity.name for entity in entities}
        results: list[SearchResult] = []
        if result_kind in {"all", "entity"} and not verification_status:
            for entity in entities:
                if entity_type and entity.entity_type != entity_type:
                    continue
                if tag_filter and tag_filter not in {value.casefold() for value in entity.tags}:
                    continue
                fields = [
                    entity.name,
                    entity.entity_type,
                    entity.description,
                    entity.notes,
                    *entity.aliases,
                    *entity.tags,
                    *(str(value) for value in entity.attributes.values()),
                ]
                if needle and not _contains(fields, needle):
                    continue
                if not needle and not (entity_type or tag_filter) and result_kind == "all":
                    continue
                results.append(
                    SearchResult(
                        "entity",
                        entity.id,
                        entity.name,
                        f"{entity.entity_type.replace('_', ' ').title()} · "
                        f"{entity.description or 'No description'}",
                    )
                )
        if result_kind in {"all", "relationship"} and not (tag_filter or entity_type):
            for relationship in self.relationships.list():
                if (
                    verification_status
                    and relationship.verification_status.value != verification_status
                ):
                    continue
                source_name = names.get(relationship.source_entity_id, "Missing record")
                target_name = names.get(relationship.target_entity_id, "Missing record")
                fields = [
                    relationship.relationship_type,
                    relationship.description,
                    relationship.notes,
                    relationship.confidence_notes,
                    source_name,
                    target_name,
                    relationship.verification_status.value,
                ]
                if needle and not _contains(fields, needle):
                    continue
                if not needle and not verification_status and result_kind == "all":
                    continue
                results.append(
                    SearchResult(
                        "relationship",
                        relationship.id,
                        relationship.relationship_type,
                        f"{source_name} → {target_name} · "
                        f"{relationship.verification_status.value.replace('_', ' ')}",
                    )
                )
        if result_kind in {"all", "source"} and not (
            tag_filter or entity_type or verification_status
        ):
            for source in self.sources.list():
                fields = [
                    source.title,
                    source.url,
                    source.local_path,
                    source.notes,
                    source.content_hash,
                ]
                if needle and not _contains(fields, needle):
                    continue
                if not needle and result_kind == "all":
                    continue
                results.append(
                    SearchResult(
                        "source",
                        source.id,
                        source.title,
                        f"{source.source_type.value.replace('_', ' ').title()} · "
                        f"{source.url or source.local_path or 'No location'}",
                    )
                )
        return sorted(results, key=lambda result: (result.title.casefold(), result.kind))


def _contains(fields: list[str], needle: str) -> bool:
    return any(needle in field.casefold() for field in fields)
