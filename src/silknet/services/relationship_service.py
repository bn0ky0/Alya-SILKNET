"""Validated directional relationship claims and provenance links."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from silknet.core.enums import VerificationStatus
from silknet.core.exceptions import (
    DuplicateRelationshipError,
    RecordNotFoundError,
    ValidationError,
)
from silknet.core.models import Relationship
from silknet.core.validation import (
    clean_date,
    clean_source_ids,
    clean_text,
    clean_verification_status,
)
from silknet.database.repositories import EntityRepository, RelationshipRepository, SourceRepository


class RelationshipService:
    def __init__(
        self,
        repository: RelationshipRepository,
        entity_repository: EntityRepository,
        source_repository: SourceRepository,
    ) -> None:
        self.repository = repository
        self.entity_repository = entity_repository
        self.source_repository = source_repository

    def create(
        self,
        *,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        description: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        verification_status: VerificationStatus | str = VerificationStatus.UNVERIFIED,
        confidence_notes: str = "",
        notes: str = "",
        source_ids: tuple[str, ...] | list[str] = (),
        relationship_domain: str = "general",
    ) -> Relationship:
        source_id = clean_text(source_entity_id, "Source entity ID", required=True, limit=64)
        target_id = clean_text(target_entity_id, "Target entity ID", required=True, limit=64)
        if source_id == target_id:
            raise ValidationError("A relationship must connect two different entities.")
        self._require_entity(source_id)
        self._require_entity(target_id)

        start = clean_date(start_date, "Relationship start date")
        end = clean_date(end_date, "Relationship end date")
        if start and end and start > end:
            raise ValidationError("Relationship end date must be on or after its start date.")
        provenance_ids = self._validate_source_ids(source_ids)
        relationship = Relationship(
            id=str(uuid4()),
            source_entity_id=source_id,
            target_entity_id=target_id,
            relationship_type=clean_text(
                relationship_type, "Relationship type", required=True, limit=128
            ),
            description=clean_text(description, "Relationship description"),
            start_date=start,
            end_date=end,
            verification_status=clean_verification_status(verification_status),
            confidence_notes=clean_text(confidence_notes, "Confidence notes"),
            notes=clean_text(notes, "Relationship notes"),
            source_ids=provenance_ids,
            created_at=datetime.now(UTC).isoformat(timespec="microseconds"),
            relationship_domain=_clean_relationship_domain(relationship_domain),
        )
        duplicate = next(
            (item for item in self.repository.list() if _same_claim(item, relationship)),
            None,
        )
        return duplicate or self.repository.create(relationship)

    def update(self, relationship: Relationship) -> Relationship:
        self._require_entity(relationship.source_entity_id)
        self._require_entity(relationship.target_entity_id)
        if relationship.source_entity_id == relationship.target_entity_id:
            raise ValidationError("A relationship must connect two different entities.")
        start = clean_date(relationship.start_date, "Relationship start date")
        end = clean_date(relationship.end_date, "Relationship end date")
        if start and end and start > end:
            raise ValidationError("Relationship end date must be on or after its start date.")
        candidate = Relationship(
            id=relationship.id,
            source_entity_id=relationship.source_entity_id,
            target_entity_id=relationship.target_entity_id,
            relationship_type=clean_text(
                relationship.relationship_type, "Relationship type", required=True, limit=128
            ),
            description=clean_text(relationship.description, "Relationship description"),
            start_date=start,
            end_date=end,
            verification_status=clean_verification_status(relationship.verification_status),
            confidence_notes=clean_text(relationship.confidence_notes, "Confidence notes"),
            notes=clean_text(relationship.notes, "Relationship notes"),
            source_ids=self._validate_source_ids(relationship.source_ids),
            created_at=relationship.created_at,
            relationship_domain=_clean_relationship_domain(relationship.relationship_domain),
        )
        duplicate = next(
            (
                item
                for item in self.repository.list()
                if item.id != candidate.id and _same_claim(item, candidate)
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicateRelationshipError(
                "An identical relationship claim already exists with the same sources and dates."
            )
        result = self.repository.update(candidate)
        if result is None:
            raise RecordNotFoundError(f"Relationship '{relationship.id}' was not found.")
        return result

    def get(self, relationship_id: str) -> Relationship:
        relationship = self.repository.get(relationship_id)
        if relationship is None:
            raise RecordNotFoundError(f"Relationship '{relationship_id}' was not found.")
        return relationship

    def list(self) -> list[Relationship]:
        return self.repository.list()

    def delete(self, relationship_id: str) -> bool:
        return self.repository.delete(relationship_id)

    def _require_entity(self, entity_id: str) -> None:
        if self.entity_repository.get(entity_id) is None:
            raise RecordNotFoundError(f"Entity '{entity_id}' was not found.")

    def _validate_source_ids(self, source_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        ids = clean_source_ids(source_ids)
        for source_id in ids:
            if self.source_repository.get(source_id) is None:
                raise RecordNotFoundError(f"Source '{source_id}' was not found.")
        return ids


def _same_claim(left: Relationship, right: Relationship) -> bool:
    return (
        left.source_entity_id == right.source_entity_id
        and left.target_entity_id == right.target_entity_id
        and left.relationship_type.casefold() == right.relationship_type.casefold()
        and left.start_date == right.start_date
        and left.end_date == right.end_date
        and left.source_ids == right.source_ids
        and left.relationship_domain == right.relationship_domain
    )


def _clean_relationship_domain(value: str) -> str:
    domain = value.strip().casefold()
    if domain not in {"general", "family"}:
        raise ValidationError("Relationship category must be general or family.")
    return domain
