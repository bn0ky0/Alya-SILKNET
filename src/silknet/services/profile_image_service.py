"""Validated, local copies of user-selected profile images."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtGui import QImage, QImageReader

from silknet.core.exceptions import ValidationError

_MAX_BYTES = 20 * 1024 * 1024
_MAX_PIXELS = 20_000_000
_EXTENSIONS = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "webp": ".webp", "bmp": ".bmp"}


class ProfileImageService:
    def __init__(self, image_directory: Path) -> None:
        self.image_directory = image_directory

    def read_image(self, image_file: Path) -> QImage:
        try:
            if not image_file.is_file():
                raise ValidationError("Choose an existing image file.")
            if image_file.stat().st_size > _MAX_BYTES:
                raise ValidationError("Profile images must be 20 MB or smaller.")
        except OSError as exc:
            raise ValidationError(f"Could not read the selected image: {exc}") from exc

        reader = QImageReader(str(image_file))
        reader.setDecideFormatFromContent(True)
        image_format = bytes(reader.format()).decode("ascii", errors="ignore").casefold()
        if image_format not in _EXTENSIONS or not reader.canRead():
            raise ValidationError("Choose a PNG, JPEG, WebP, or BMP image.")
        size = reader.size()
        if size.width() < 1 or size.height() < 1 or size.width() * size.height() > _MAX_PIXELS:
            raise ValidationError("The image dimensions are too large to use safely.")
        image = reader.read()
        if image.isNull():
            raise ValidationError("SILKNET could not decode the selected image.")
        return image

    def store(self, image_file: Path) -> Path:
        self.read_image(image_file)
        reader = QImageReader(str(image_file))
        reader.setDecideFormatFromContent(True)
        image_format = bytes(reader.format()).decode("ascii", errors="ignore").casefold()
        self.image_directory.mkdir(parents=True, exist_ok=True)
        destination = self.image_directory / f"{uuid4().hex}{_EXTENSIONS[image_format]}"
        try:
            shutil.copyfile(image_file, destination)
        except OSError as exc:
            raise ValidationError(f"The profile image could not be stored: {exc}") from exc
        return destination

    def discard(self, image_file: Path) -> None:
        try:
            if image_file.resolve().parent == self.image_directory.resolve():
                image_file.unlink(missing_ok=True)
        except OSError:
            return
