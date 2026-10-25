from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from silknet.core.exceptions import ValidationError
from silknet.services.profile_image_service import ProfileImageService


def test_profile_image_is_checked_and_copied_with_detected_format(tmp_path: Path) -> None:
    original = tmp_path / "misleading.exe"
    image = QImage(QSize(12, 10), QImage.Format.Format_ARGB32)
    image.fill(0xFF80683F)
    assert image.save(str(original), "PNG")
    service = ProfileImageService(tmp_path / "local-images")

    stored = service.store(original)

    assert stored.suffix == ".png"
    assert stored.parent == service.image_directory
    assert service.read_image(stored).size() == QSize(12, 10)


def test_profile_image_rejects_unreadable_files(tmp_path: Path) -> None:
    image = tmp_path / "broken.png"
    image.write_bytes(b"not an image")
    service = ProfileImageService(tmp_path / "local-images")

    with pytest.raises(ValidationError, match="Choose a PNG"):
        service.read_image(image)
