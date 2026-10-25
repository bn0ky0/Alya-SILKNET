from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from silknet.core.exceptions import ValidationError
from silknet.ui.entity_manager import EntityRecordDialog


def test_family_tree_reuses_people_and_keeps_non_biological_labels(data_services) -> None:
    parent = data_services.entities.create(entity_type="person", name="Mina")
    child = data_services.entities.create(entity_type="person", name="Yara")
    claim = data_services.family.create_relationship(
        source_entity_id=parent.id,
        target_entity_id=child.id,
        relationship_type="adoptive parent",
        relationship_domain="general",
    )

    assert claim.relationship_domain == "family"
    assert [person.id for person in data_services.family.people()] == [parent.id, child.id]
    assert [item.relationship_type for item in data_services.family.relationships_for_people()] == [
        "adoptive parent"
    ]


def test_family_service_rejects_non_person_entities(data_services) -> None:
    person = data_services.entities.create(entity_type="person", name="Person")
    organization = data_services.entities.create(entity_type="organization", name="Organization")

    with pytest.raises(ValidationError, match="person records"):
        data_services.family.create_relationship(
            source_entity_id=person.id,
            target_entity_id=organization.id,
            relationship_type="guardian",
        )


def test_general_person_claim_does_not_appear_in_family_tree(data_services) -> None:
    first = data_services.entities.create(entity_type="person", name="First")
    second = data_services.entities.create(entity_type="person", name="Second")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="colleague",
    )

    assert data_services.family.relationships_for_people() == []


def test_entity_dialog_saves_custom_social_platform_and_profile_url(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = EntityRecordDialog(data_services.entities, platform_service=data_services.platforms)
    dialog.type_field.setCurrentIndex(dialog.type_field.findData("social_profile"))
    dialog.name_field.setText("Research profile")
    dialog.platform_field.setCurrentText("Mastodon")
    dialog.profile_url_field.setText("https://mastodon.social/@sample")
    dialog.username_field.setText("@sample")

    dialog._save()

    assert dialog.saved_entity is not None
    assert dialog.saved_entity.attributes["platform"] == "Mastodon"
    assert dialog.saved_entity.attributes["profile_url"] == "https://mastodon.social/@sample"
    assert "Mastodon" in data_services.platforms.list()
    app.quit()


def test_entity_dialog_copies_person_image_to_local_storage(data_services, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "portrait.png"
    image = QImage(QSize(12, 12), QImage.Format.Format_ARGB32)
    image.fill(0xFF80683F)
    assert image.save(str(source))
    dialog = EntityRecordDialog(
        data_services.entities,
        image_service=data_services.profile_images,
        platform_service=data_services.platforms,
    )
    dialog.name_field.setText("Person with portrait")
    dialog._selected_image_source = source

    dialog._save()

    assert dialog.saved_entity is not None
    image_path = dialog.saved_entity.attributes["profile_image_path"]
    assert image_path.startswith(str(data_services.profile_images.image_directory))
    assert data_services.profile_images.read_image(Path(image_path)).size() == QSize(12, 12)
    app.quit()
