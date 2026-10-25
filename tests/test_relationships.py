from dataclasses import replace

import pytest

from silknet.core.enums import VerificationStatus
from silknet.core.exceptions import (
    DuplicateRelationshipError,
    RecordNotFoundError,
    ValidationError,
)


def test_relationships_persist_direction_status_and_distinct_provenance(data_services) -> None:
    first = data_services.entities.create(entity_type="person", name="First")
    second = data_services.entities.create(entity_type="organization", name="Second")
    source_a = data_services.sources.create(title="Report A", source_type="note")
    source_b = data_services.sources.create(title="Report B", source_type="note")

    claim = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works for",
        start_date="2024-01-01",
        verification_status=VerificationStatus.USER_REPORTED,
        source_ids=[source_a.id],
    )
    duplicate = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="Works For",
        start_date="2024-01-01",
        verification_status="user_reported",
        source_ids=[source_a.id],
    )
    independently_sourced = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works for",
        start_date="2024-01-01",
        source_ids=[source_b.id],
    )
    reverse = data_services.relationships.create(
        source_entity_id=second.id,
        target_entity_id=first.id,
        relationship_type="works for",
        start_date="2024-01-01",
    )

    assert duplicate.id == claim.id
    assert independently_sourced.id != claim.id
    assert reverse.source_entity_id == second.id
    assert reverse.target_entity_id == first.id
    assert data_services.relationships.get(claim.id).source_ids == (source_a.id,)
    assert len(data_services.relationships.list()) == 3


def test_relationship_validation_and_entity_deletion_cascade(data_services) -> None:
    first = data_services.entities.create(entity_type="person", name="First")
    second = data_services.entities.create(entity_type="person", name="Second")

    with pytest.raises(ValidationError, match="different entities"):
        data_services.relationships.create(
            source_entity_id=first.id,
            target_entity_id=first.id,
            relationship_type="associated with",
        )
    with pytest.raises(ValidationError, match="end date"):
        data_services.relationships.create(
            source_entity_id=first.id,
            target_entity_id=second.id,
            relationship_type="associated with",
            start_date="2025-01-01",
            end_date="2024-01-01",
        )
    with pytest.raises(RecordNotFoundError, match="not found"):
        data_services.relationships.create(
            source_entity_id=first.id,
            target_entity_id="00000000-0000-0000-0000-000000000000",
            relationship_type="associated with",
        )

    claim = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="associated with",
    )
    assert data_services.entities.delete(first.id)
    assert data_services.relationships.list() == []
    with pytest.raises(RecordNotFoundError, match="not found"):
        data_services.relationships.get(claim.id)


def test_relationship_edits_keep_ids_and_reject_duplicate_claims(data_services) -> None:
    first = data_services.entities.create(entity_type="person", name="First")
    second = data_services.entities.create(entity_type="person", name="Second")
    source_a = data_services.sources.create(title="A", source_type="note")
    source_b = data_services.sources.create(title="B", source_type="note")
    original = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="associated with",
        source_ids=[source_a.id],
    )
    separate = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="associated with",
        source_ids=[source_b.id],
    )
    assert original.id != separate.id

    updated = data_services.relationships.update(replace(separate, notes="Updated note"))
    assert updated.id == separate.id
    assert data_services.relationships.get(separate.id).notes == "Updated note"
    with pytest.raises(DuplicateRelationshipError, match="identical relationship claim"):
        data_services.relationships.update(replace(separate, source_ids=(source_a.id,)))
