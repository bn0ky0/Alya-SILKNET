"""Family-specific views and validation over the shared entity records."""

from silknet.core.enums import EntityType
from silknet.core.exceptions import ValidationError
from silknet.core.models import Entity, Relationship
from silknet.services.entity_service import EntityService
from silknet.services.relationship_service import RelationshipService


class FamilyService:
    def __init__(self, entities: EntityService, relationships: RelationshipService) -> None:
        self.entities = entities
        self.relationships = relationships

    def people(self) -> list[Entity]:
        return [
            entity
            for entity in self.entities.list()
            if entity.entity_type == EntityType.PERSON.value
        ]

    def relationships_for_people(self) -> list[Relationship]:
        people_ids = {person.id for person in self.people()}
        return [
            relationship
            for relationship in self.relationships.list()
            if relationship.relationship_domain == "family"
            and relationship.source_entity_id in people_ids
            and relationship.target_entity_id in people_ids
        ]

    def create_relationship(self, **values: object) -> Relationship:
        values.pop("relationship_domain", None)
        source_id = values.get("source_entity_id")
        target_id = values.get("target_entity_id")
        for entity_id in (source_id, target_id):
            if not isinstance(entity_id, str):
                raise ValidationError("Family relationships must connect two person records.")
            if self.entities.get(entity_id).entity_type != EntityType.PERSON.value:
                raise ValidationError("Family relationships must connect two person records.")
        return self.relationships.create(relationship_domain="family", **values)
