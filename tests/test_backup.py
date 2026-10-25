import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from silknet.core.exceptions import ValidationError


def test_backup_restore_recovers_records_and_profile_images(data_services, tmp_path: Path) -> None:
    source_image = tmp_path / "portrait.png"
    image = QImage(QSize(10, 10), QImage.Format.Format_ARGB32)
    image.fill(0xFF80683F)
    assert image.save(str(source_image))
    stored_image = data_services.profile_images.store(source_image)
    entity = data_services.entities.create(
        entity_type="person",
        name="Before backup",
        attributes={"profile_image_path": str(stored_image)},
    )
    archive = tmp_path / "backup.zip"
    data_services.backups.create_backup(archive)
    data_services.entities.update(entity.id, name="Changed after backup")

    data_services.backups.restore_backup(archive)

    restored = data_services.entities.get(entity.id)
    restored_image = Path(restored.attributes["profile_image_path"])
    assert restored.name == "Before backup"
    assert restored_image.parent == data_services.profile_images.image_directory
    assert restored_image.is_file()
    assert data_services.profile_images.read_image(restored_image).size() == QSize(10, 10)
    backup_dir = data_services.entities.repository.database_file.parent / "backups"
    assert list(backup_dir.glob("*.zip"))


def test_corrupt_backup_is_rejected_without_changing_workspace(
    data_services, tmp_path: Path
) -> None:
    entity = data_services.entities.create(entity_type="person", name="Keep this record")
    invalid = tmp_path / "broken.zip"
    invalid.write_bytes(b"not a zip archive")

    with pytest.raises(ValidationError, match="damaged"):
        data_services.backups.restore_backup(invalid)

    assert data_services.entities.get(entity.id).name == "Keep this record"


def test_restore_requires_a_silknet_database_member(data_services, tmp_path: Path) -> None:
    invalid = tmp_path / "unrelated.zip"
    with zipfile.ZipFile(invalid, "w") as archive:
        archive.writestr("notes.txt", "not a workspace")

    with pytest.raises(ValidationError, match="does not contain"):
        data_services.backups.restore_backup(invalid)
