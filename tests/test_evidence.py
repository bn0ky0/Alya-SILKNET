from PySide6.QtWidgets import QApplication

from silknet.core.enums import SourceType, VerificationStatus
from silknet.ui.evidence_view import EvidencePage


def test_source_links_show_entities_and_claim_status(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    source = data_services.sources.create(
        title="Interview notes",
        source_type=SourceType.NOTE,
        observed_at="2026-05-08",
    )
    first = data_services.entities.create(entity_type="person", name="Nora", source_ids=[source.id])
    second = data_services.entities.create(entity_type="person", name="Omar")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="met with",
        verification_status=VerificationStatus.USER_REPORTED,
        confidence_notes="Second-hand account",
        source_ids=[source.id],
    )

    page = EvidencePage(data_services)

    assert "Entities: Nora" in page.linked_records.text()
    assert "Nora → Omar: met with (user reported)" in page.linked_records.text()
    assert "Observed: 2026-05-08" in page.detail_copy.text()
    app.quit()


def test_source_can_be_selected_as_provenance_for_entities_and_claims(data_services) -> None:
    source = data_services.sources.create(title="Archive record", source_type="note")
    first = data_services.entities.create(entity_type="person", name="A", source_ids=[source.id])
    second = data_services.entities.create(entity_type="person", name="B")
    relationship = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="reported by",
        source_ids=[source.id],
    )

    assert data_services.entities.get(first.id).source_ids == (source.id,)
    assert data_services.relationships.get(relationship.id).source_ids == (source.id,)
