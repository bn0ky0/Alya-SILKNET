"""Verified workspace backups and guarded restore operations."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from silknet.core.exceptions import MigrationError, ValidationError
from silknet.database.connection import initialize_database

_DATABASE_MEMBER = "workspace.sqlite3"
_IMAGE_PREFIX = "profile-images/"
_MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024


class BackupService:
    def __init__(self, database_file: Path, image_directory: Path) -> None:
        self.database_file = database_file
        self.image_directory = image_directory

    def create_backup(self, destination: Path) -> Path:
        if not self.database_file.is_file():
            raise ValidationError("The SILKNET workspace database does not exist yet.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.database_file.resolve():
            raise ValidationError("Choose a separate file for the workspace backup.")
        with tempfile.TemporaryDirectory(
            dir=destination.parent, prefix="silknet-backup-"
        ) as folder:
            workspace_copy = Path(folder) / _DATABASE_MEMBER
            archive_copy = Path(folder) / "backup.tmp"
            _copy_database(self.database_file, workspace_copy)
            with zipfile.ZipFile(archive_copy, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(workspace_copy, _DATABASE_MEMBER)
                if self.image_directory.is_dir():
                    from silknet.services.profile_image_service import ProfileImageService

                    image_service = ProfileImageService(self.image_directory)
                    for image in self.image_directory.iterdir():
                        if (
                            image.is_file()
                            and not image.is_symlink()
                            and image.suffix.casefold() in {".png", ".jpg", ".webp", ".bmp"}
                        ):
                            image_service.read_image(image)
                            archive.write(image, f"{_IMAGE_PREFIX}{image.name}")
            os.replace(archive_copy, destination)
        return destination

    def restore_backup(self, backup_file: Path) -> None:
        if not backup_file.is_file():
            raise ValidationError("Choose an existing SILKNET backup file.")
        if backup_file.resolve() == self.database_file.resolve():
            raise ValidationError("A workspace database is not a backup archive.")
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        self.image_directory.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            dir=self.database_file.parent, prefix="silknet-restore-"
        ) as folder:
            staging = Path(folder)
            staged_database = staging / _DATABASE_MEMBER
            staged_images = staging / "profile-images"
            image_names = self._extract_backup(backup_file, staged_database, staged_images)
            _check_database(staged_database)
            try:
                initialize_database(staged_database)
            except MigrationError as exc:
                raise ValidationError(f"This backup cannot be restored: {exc}") from exc
            _rewrite_image_paths(staged_database, self.image_directory, image_names)
            _check_database(staged_database)

            if self.database_file.exists():
                safety_path = (
                    self.database_file.parent
                    / "backups"
                    / (
                        "silknet-before-restore-"
                        + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                        + "-"
                        + uuid4().hex[:6]
                        + ".zip"
                    )
                )
                self.create_backup(safety_path)
            for image in staged_images.iterdir() if staged_images.exists() else ():
                destination = self.image_directory / image.name
                temporary_image = destination.with_suffix(destination.suffix + ".tmp")
                shutil.copyfile(image, temporary_image)
                os.replace(temporary_image, destination)
            os.replace(staged_database, self.database_file)

    def _extract_backup(self, backup_file: Path, database: Path, images: Path) -> set[str]:
        try:
            with zipfile.ZipFile(backup_file) as archive:
                members = archive.infolist()
                total_size = sum(member.file_size for member in members)
                if total_size > _MAX_BACKUP_BYTES:
                    raise ValidationError("Backup archives must be 2 GB or smaller.")
                image_names: set[str] = set()
                found_database = False
                for member in members:
                    path = PurePosixPath(member.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValidationError("Backup contains an unsafe file path.")
                    if member.filename == _DATABASE_MEMBER:
                        target = database
                        found_database = True
                    elif member.filename.startswith(_IMAGE_PREFIX) and len(path.parts) == 2:
                        name = path.name
                        if (
                            not name
                            or name in {".", ".."}
                            or "\\" in name
                            or ":" in name
                            or Path(name).suffix.casefold() not in {".png", ".jpg", ".webp", ".bmp"}
                        ):
                            raise ValidationError("Backup contains an invalid image name.")
                        target = images / name
                        images.mkdir(parents=True, exist_ok=True)
                        image_names.add(name)
                    else:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
                if not found_database:
                    raise ValidationError("Backup does not contain a SILKNET workspace database.")
                if images.exists():
                    from silknet.services.profile_image_service import ProfileImageService

                    image_service = ProfileImageService(images)
                    for image in images.iterdir():
                        image_service.read_image(image)
                return image_names
        except zipfile.BadZipFile as exc:
            raise ValidationError("This backup file is damaged or is not a ZIP archive.") from exc
        except OSError as exc:
            raise ValidationError(f"The backup could not be read: {exc}") from exc


def _copy_database(source: Path, destination: Path) -> None:
    try:
        with (
            closing(sqlite3.connect(source)) as source_connection,
            closing(sqlite3.connect(destination)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            destination_connection.commit()
    except sqlite3.DatabaseError as exc:
        raise ValidationError(f"The workspace database could not be backed up: {exc}") from exc
    _check_database(destination)


def _check_database(database_file: Path) -> None:
    try:
        with closing(sqlite3.connect(database_file)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValidationError("The backup database failed SQLite's integrity check.")
            has_metadata = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_metadata'"
            ).fetchone()
            if has_metadata is None:
                raise ValidationError("The archive does not contain a SILKNET database.")
    except sqlite3.DatabaseError as exc:
        raise ValidationError(f"The backup database could not be checked: {exc}") from exc


def _rewrite_image_paths(database_file: Path, image_directory: Path, image_names: set[str]) -> None:
    with closing(sqlite3.connect(database_file)) as connection, connection:
        rows = connection.execute("SELECT id, attributes_json FROM entities").fetchall()
        for entity_id, encoded in rows:
            try:
                attributes = json.loads(encoded)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(attributes, dict):
                continue
            old_path = attributes.get("profile_image_path")
            if not old_path:
                continue
            name = Path(str(old_path)).name
            if name in image_names:
                attributes["profile_image_path"] = str(image_directory / name)
            else:
                attributes.pop("profile_image_path", None)
            connection.execute(
                "UPDATE entities SET attributes_json = ? WHERE id = ?",
                (
                    json.dumps(attributes, ensure_ascii=False, sort_keys=True, allow_nan=False),
                    entity_id,
                ),
            )
