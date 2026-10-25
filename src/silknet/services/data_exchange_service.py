"""Validated workspace export and import for JSON and entity CSV files."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from silknet.core.enums import EntityType, SourceType, VerificationStatus
from silknet.core.exceptions import ValidationError
from silknet.core.models import Relationship, Source
from silknet.core.validation import clean_date, clean_source_type, clean_url

if TYPE_CHECKING:
    from silknet.services.container import ApplicationServices

_MAX_IMPORT_BYTES = 25 * 1024 * 1024
_CSV_FIELDS = (
    "entity_type",
    "name",
    "description",
    "aliases_json",
    "attributes_json",
    "tags_json",
    "notes",
)


@dataclass(frozen=True, slots=True)
class ImportPreview:
    file_type: str
    new_entities: int = 0
    duplicate_entities: int = 0
    new_sources: int = 0
    duplicate_sources: int = 0
    relationships: int = 0
    errors: tuple[str, ...] = ()

    @property
    def can_import(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class ImportSummary:
    imported_entities: int = 0
    skipped_entities: int = 0
    imported_sources: int = 0
    skipped_sources: int = 0
    imported_relationships: int = 0
    skipped_relationships: int = 0
    warnings: tuple[str, ...] = ()


class DataExchangeService:
    def __init__(self, services: ApplicationServices) -> None:
        self.services = services

    def _ensure_safe_export_path(self, destination: Path) -> None:
        if destination.resolve() == self.services.backups.database_file.resolve():
            raise ValidationError(
                "Choose a separate file for the export. "
                "The workspace database cannot be overwritten."
            )

    def export_json(self, destination: Path) -> None:
        self._ensure_safe_export_path(destination)
        document = {
            "format": "silknet-workspace",
            "version": 1,
            "sources": [_source_to_dict(source) for source in self.services.sources.list()],
            "entities": [asdict(entity) for entity in self.services.entities.list()],
            "relationships": [
                _relationship_to_dict(item) for item in self.services.relationships.list()
            ],
            "custom_entity_types": [
                asdict(item) for item in self.services.entities.list_custom_types()
            ],
        }
        _write_json(destination, document)

    def export_csv(self, destination: Path) -> None:
        self._ensure_safe_export_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for entity in self.services.entities.list():
                writer.writerow(
                    {
                        "entity_type": entity.entity_type,
                        "name": entity.name,
                        "description": entity.description,
                        "aliases_json": json.dumps(list(entity.aliases), ensure_ascii=False),
                        "attributes_json": json.dumps(
                            entity.attributes, ensure_ascii=False, allow_nan=False
                        ),
                        "tags_json": json.dumps(list(entity.tags), ensure_ascii=False),
                        "notes": entity.notes,
                    }
                )

    def preview_json(self, source: Path) -> ImportPreview:
        errors: list[str] = []
        try:
            document = _read_json(source)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            return ImportPreview("JSON", errors=(str(exc),))
        if document.get("format") != "silknet-workspace" or document.get("version") != 1:
            return ImportPreview("JSON", errors=("This is not a supported SILKNET export.",))
        sources = _records(document, "sources", errors)
        entities = _records(document, "entities", errors)
        relationships = _records(document, "relationships", errors)
        custom_types = _records(document, "custom_entity_types", errors)
        registered_types = {item.key for item in self.services.entities.list_custom_types()}
        imported_types: set[str] = set()
        for index, custom_type in enumerate(custom_types, 1):
            if not isinstance(custom_type.get("key"), str) or not isinstance(
                custom_type.get("display_name"), str
            ):
                errors.append(f"Custom entity type {index} is missing its key or display name.")
                continue
            imported_types.add(custom_type["key"])
        known_types = {item.value for item in EntityType} | registered_types | imported_types
        source_ids: set[str] = set()
        seen_source_ids: set[str] = set()
        for index, row in enumerate(sources, 1):
            if not _valid_source(row):
                errors.append(f"Source {index} is missing a title or source type.")
                continue
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id:
                errors.append(f"Source {index} has no record ID.")
            elif row_id in seen_source_ids:
                errors.append(f"Source {index} repeats a record ID.")
            else:
                source_ids.add(row_id)
                seen_source_ids.add(row_id)
            try:
                clean_source_type(row["source_type"])
                clean_url(row.get("url", ""))
                clean_date(row.get("observed_at"), "Observed date")
                source_type = SourceType(row["source_type"])
                if source_type is SourceType.PUBLIC_URL and not row.get("url"):
                    raise ValidationError("A public URL source requires a URL.")
                if source_type is SourceType.LOCAL_DOCUMENT and not row.get("local_path"):
                    raise ValidationError("A local document source requires a file path.")
            except (TypeError, ValidationError) as exc:
                errors.append(f"Source {index}: {exc}")

        entity_ids: set[str] = set()
        seen_entity_ids: set[str] = set()
        entity_types: dict[str, str] = {}
        for index, row in enumerate(entities, 1):
            if not _valid_entity(row):
                errors.append(f"Entity {index} has invalid fields or a missing name.")
                continue
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id:
                errors.append(f"Entity {index} has no record ID.")
            elif row_id in seen_entity_ids:
                errors.append(f"Entity {index} repeats a record ID.")
            else:
                entity_ids.add(row_id)
                seen_entity_ids.add(row_id)
                entity_types[row_id] = row["entity_type"]
            if row["entity_type"] not in known_types:
                errors.append(f"Entity {index} has an unregistered entity type.")
            if row["entity_type"] == "social_profile":
                attributes = row.get("attributes", {})
                try:
                    if (
                        not isinstance(attributes.get("platform"), str)
                        or not attributes["platform"].strip()
                    ):
                        raise ValidationError("A social profile requires a platform.")
                    clean_url(attributes.get("profile_url", ""))
                    VerificationStatus(attributes.get("verification_status", "unverified"))
                except (TypeError, ValueError, ValidationError) as exc:
                    errors.append(f"Entity {index}: {exc}")
            image_path = row.get("attributes", {}).get("profile_image_path")
            if image_path and not isinstance(image_path, str):
                errors.append(f"Entity {index} has an invalid profile image path.")
            elif image_path and _is_workspace_image(self.services, Path(image_path)):
                try:
                    self.services.profile_images.read_image(Path(image_path))
                except ValidationError as exc:
                    errors.append(f"Entity {index} profile image: {exc}")
            for source_id in row.get("source_ids", []):
                if source_id not in source_ids and not _source_exists(self.services, source_id):
                    errors.append(
                        f"Entity {index} refers to a source that is not in this workspace or file."
                    )

        for index, row in enumerate(relationships, 1):
            if not _valid_relationship(row):
                errors.append(f"Relationship {index} has invalid fields.")
                continue
            if row["source_entity_id"] not in entity_ids:
                if self.services.entities.repository.get(row["source_entity_id"]) is None:
                    errors.append(f"Relationship {index} refers to a missing source entity.")
            if row["target_entity_id"] not in entity_ids:
                if self.services.entities.repository.get(row["target_entity_id"]) is None:
                    errors.append(f"Relationship {index} refers to a missing target entity.")
            source_type = entity_types.get(row["source_entity_id"])
            target_type = entity_types.get(row["target_entity_id"])
            if source_type is None:
                current_source = self.services.entities.repository.get(row["source_entity_id"])
                source_type = current_source.entity_type if current_source else None
            if target_type is None:
                current_target = self.services.entities.repository.get(row["target_entity_id"])
                target_type = current_target.entity_type if current_target else None
            if row.get("relationship_domain", "general") == "family" and (
                source_type != EntityType.PERSON.value or target_type != EntityType.PERSON.value
            ):
                errors.append(f"Relationship {index}: family claims must connect person records.")
            for source_id in row.get("source_ids", []):
                if source_id not in source_ids and not _source_exists(self.services, source_id):
                    errors.append(f"Relationship {index} refers to a missing evidence source.")
            try:
                VerificationStatus(row.get("verification_status", "unverified"))
                clean_date(row.get("start_date"), "Relationship start date")
                clean_date(row.get("end_date"), "Relationship end date")
                start, end = row.get("start_date"), row.get("end_date")
                if start and end and start > end:
                    raise ValidationError("Relationship end date precedes its start date.")
                if row.get("relationship_domain", "general") not in {"general", "family"}:
                    raise ValidationError("Relationship category must be general or family.")
            except (TypeError, ValueError, ValidationError) as exc:
                errors.append(f"Relationship {index}: {exc}")

        existing_sources = {_source_key(item) for item in self.services.sources.list()}
        existing_entities = {_entity_key(item) for item in self.services.entities.list()}
        seen_sources: set[tuple[str, str, str]] = set()
        seen_entities: set[tuple[str, str]] = set()
        duplicate_sources = duplicate_entities = 0
        for row in sources:
            if _valid_source(row):
                key = _source_key(row)
                duplicate_sources += key in existing_sources or key in seen_sources
                seen_sources.add(key)
        for row in entities:
            if _valid_entity(row):
                key = _entity_key(row)
                duplicate_entities += key in existing_entities or key in seen_entities
                seen_entities.add(key)
        return ImportPreview(
            "JSON",
            new_entities=max(0, len(entities) - duplicate_entities),
            duplicate_entities=duplicate_entities,
            new_sources=max(0, len(sources) - duplicate_sources),
            duplicate_sources=duplicate_sources,
            relationships=len(relationships),
            errors=tuple(errors),
        )

    def preview_csv(self, source: Path) -> ImportPreview:
        errors: list[str] = []
        try:
            rows = _read_csv(source)
        except (OSError, UnicodeError, csv.Error, ValidationError) as exc:
            return ImportPreview("CSV", errors=(str(exc),))
        existing = {_entity_key(item) for item in self.services.entities.list()}
        seen: set[tuple[str, str]] = set()
        duplicates = 0
        for index, row in enumerate(rows, 1):
            try:
                _validate_csv_entity(row)
            except (TypeError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                errors.append(f"Row {index}: {exc}")
                continue
            key = (row["entity_type"].casefold(), row["name"].strip().casefold())
            duplicates += key in existing or key in seen
            seen.add(key)
        return ImportPreview(
            "CSV",
            new_entities=max(0, len(rows) - duplicates),
            duplicate_entities=duplicates,
            errors=tuple(errors),
        )

    def import_json(self, source: Path) -> ImportSummary:
        preview = self.preview_json(source)
        if not preview.can_import:
            raise ValidationError("Import preview found errors:\n" + "\n".join(preview.errors))
        document = _read_json(source)
        return self._run_with_rollback(lambda images: self._import_json_document(document, images))

    def _import_json_document(
        self, document: dict[str, Any], created_images: list[Path]
    ) -> ImportSummary:
        warnings: list[str] = []
        source_map: dict[str, str] = {}
        entity_map: dict[str, str] = {}
        imported_sources = skipped_sources = 0
        imported_entities = skipped_entities = 0
        imported_relationships = skipped_relationships = 0

        for custom_type in document.get("custom_entity_types", []):
            if self.services.entities.repository.get_custom_type(custom_type["key"]) is None:
                self.services.entities.create_custom_type(
                    key=custom_type["key"],
                    display_name=custom_type["display_name"],
                    fields=custom_type.get("fields", []),
                )

        for row in document["sources"]:
            existing = next(
                (
                    item
                    for item in self.services.sources.list()
                    if _source_key(item) == _source_key(row)
                ),
                None,
            )
            if existing:
                source_map[row["id"]] = existing.id
                skipped_sources += 1
                continue
            created = self.services.sources.create(
                title=row["title"],
                source_type=row["source_type"],
                url=row.get("url", ""),
                local_path=row.get("local_path", ""),
                observed_at=row.get("observed_at"),
                notes=row.get("notes", ""),
                content_hash=row.get("content_hash", ""),
            )
            source_map[row["id"]] = created.id
            imported_sources += 1

        for row in document["entities"]:
            key = (row["entity_type"].casefold(), row["name"].strip().casefold())
            existing = next(
                (item for item in self.services.entities.list() if _entity_key(item) == key),
                None,
            )
            if existing:
                entity_map[row["id"]] = existing.id
                skipped_entities += 1
                continue
            attributes = dict(row.get("attributes", {}))
            image_path = attributes.get("profile_image_path")
            if image_path:
                if _is_workspace_image(self.services, Path(image_path)):
                    stored_image = self.services.profile_images.store(Path(image_path))
                    created_images.append(stored_image)
                    attributes["profile_image_path"] = str(stored_image)
                else:
                    attributes.pop("profile_image_path", None)
                    warnings.append(
                        f"Profile image for '{row['name']}' was not found and was skipped."
                    )
            if row["entity_type"] == "social_profile":
                self.services.platforms.add(str(attributes.get("platform", "")))
            linked_sources = [
                source_map.get(source_id, source_id) for source_id in row.get("source_ids", [])
            ]
            created = self.services.entities.create(
                entity_type=row["entity_type"],
                name=row["name"],
                description=row.get("description", ""),
                aliases=row.get("aliases", []),
                attributes=attributes,
                tags=row.get("tags", []),
                notes=row.get("notes", ""),
                source_ids=linked_sources,
            )
            entity_map[row["id"]] = created.id
            imported_entities += 1

        existing_claims = {_relationship_key(item) for item in self.services.relationships.list()}
        for row in document["relationships"]:
            source_id = entity_map.get(row["source_entity_id"], row["source_entity_id"])
            target_id = entity_map.get(row["target_entity_id"], row["target_entity_id"])
            linked_sources = tuple(
                sorted(
                    source_map.get(source_id, source_id) for source_id in row.get("source_ids", [])
                )
            )
            key = (
                source_id,
                target_id,
                row["relationship_type"].casefold(),
                row.get("start_date"),
                row.get("end_date"),
                linked_sources,
                row.get("relationship_domain", "general"),
            )
            if key in existing_claims:
                skipped_relationships += 1
                continue
            self.services.relationships.create(
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type=row["relationship_type"],
                description=row.get("description", ""),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                verification_status=row.get("verification_status", "unverified"),
                confidence_notes=row.get("confidence_notes", ""),
                notes=row.get("notes", ""),
                source_ids=linked_sources,
                relationship_domain=row.get("relationship_domain", "general"),
            )
            existing_claims.add(key)
            imported_relationships += 1
        return ImportSummary(
            imported_entities,
            skipped_entities,
            imported_sources,
            skipped_sources,
            imported_relationships,
            skipped_relationships,
            tuple(warnings),
        )

    def import_csv(self, source: Path) -> ImportSummary:
        preview = self.preview_csv(source)
        if not preview.can_import:
            raise ValidationError("Import preview found errors:\n" + "\n".join(preview.errors))
        return self._run_with_rollback(lambda _images: self._import_csv_rows(_read_csv(source)))

    def _import_csv_rows(self, rows: list[dict[str, str]]) -> ImportSummary:
        existing = {_entity_key(item) for item in self.services.entities.list()}
        imported = skipped = 0
        for row in rows:
            _validate_csv_entity(row)
            key = (row["entity_type"].casefold(), row["name"].strip().casefold())
            if key in existing:
                skipped += 1
                continue
            self.services.entities.create(
                entity_type=row["entity_type"],
                name=row["name"],
                description=row["description"],
                aliases=row["aliases"],
                attributes=row["attributes"],
                tags=row["tags"],
                notes=row["notes"],
            )
            existing.add(key)
            imported += 1
        return ImportSummary(imported_entities=imported, skipped_entities=skipped)

    def _run_with_rollback(self, operation):
        database_file = self.services.entities.repository.database_file
        with tempfile.TemporaryDirectory(
            dir=database_file.parent, prefix="silknet-import-"
        ) as directory:
            snapshot = Path(directory) / "before.sqlite3"
            with (
                closing(sqlite3.connect(database_file)) as source,
                closing(sqlite3.connect(snapshot)) as destination,
            ):
                source.backup(destination)
                destination.commit()
            created_images: list[Path] = []
            try:
                return operation(created_images)
            except Exception as exc:
                try:
                    os.replace(snapshot, database_file)
                except OSError as rollback_error:
                    raise ValidationError(
                        f"Import failed and the workspace could not be restored: {rollback_error}"
                    ) from exc
                for image in created_images:
                    self.services.profile_images.discard(image)
                raise


def _source_to_dict(source: Source) -> dict[str, Any]:
    return {**asdict(source), "source_type": source.source_type.value}


def _relationship_to_dict(relationship: Relationship) -> dict[str, Any]:
    return {
        **asdict(relationship),
        "verification_status": relationship.verification_status.value,
    }


def _write_json(destination: Path, document: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _read_json(source: Path) -> dict[str, Any]:
    if source.stat().st_size > _MAX_IMPORT_BYTES:
        raise ValidationError("Import files must be 25 MB or smaller.")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError("JSON import must contain an object at the top level.")
    return value


def _read_csv(source: Path) -> list[dict[str, str]]:
    if source.stat().st_size > _MAX_IMPORT_BYTES:
        raise ValidationError("Import files must be 25 MB or smaller.")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(_CSV_FIELDS).issubset(reader.fieldnames):
            raise ValidationError("CSV must include the SILKNET entity export columns.")
        return list(reader)


def _records(document: dict[str, Any], key: str, errors: list[str]) -> list[dict[str, Any]]:
    value = document.get(key, [])
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        errors.append(f"The '{key}' section must be a list of records.")
        return []
    return value


def _valid_source(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("title"), str)
        and bool(row["title"].strip())
        and isinstance(row.get("source_type"), str)
        and all(
            isinstance(row.get(key, ""), str)
            for key in ("url", "local_path", "notes", "content_hash")
        )
        and (row.get("observed_at") is None or isinstance(row.get("observed_at"), str))
    )


def _valid_entity(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("entity_type"), str)
        and isinstance(row.get("name"), str)
        and bool(row["name"].strip())
        and isinstance(row.get("attributes", {}), dict)
        and isinstance(row.get("description", ""), str)
        and isinstance(row.get("notes", ""), str)
        and isinstance(row.get("aliases", []), list)
        and all(isinstance(value, str) for value in row.get("aliases", []))
        and isinstance(row.get("tags", []), list)
        and all(isinstance(value, str) for value in row.get("tags", []))
        and isinstance(row.get("source_ids", []), list)
        and all(isinstance(value, str) for value in row.get("source_ids", []))
    )


def _valid_relationship(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("source_entity_id"), str)
        and isinstance(row.get("target_entity_id"), str)
        and row["source_entity_id"] != row["target_entity_id"]
        and isinstance(row.get("relationship_type"), str)
        and bool(row["relationship_type"].strip())
        and isinstance(row.get("source_ids", []), list)
        and all(isinstance(value, str) for value in row.get("source_ids", []))
        and isinstance(row.get("description", ""), str)
        and isinstance(row.get("confidence_notes", ""), str)
        and isinstance(row.get("notes", ""), str)
    )


def _validate_csv_entity(row: dict[str, str]) -> dict[str, Any]:
    for field in ("aliases_json", "attributes_json", "tags_json"):
        row[field] = json.loads(row.get(field) or ("{}" if field == "attributes_json" else "[]"))
    if not _valid_entity(
        {
            "entity_type": row.get("entity_type"),
            "name": row.get("name"),
            "aliases": row["aliases_json"],
            "attributes": row["attributes_json"],
            "tags": row["tags_json"],
            "source_ids": [],
        }
    ):
        raise ValidationError(
            "Entity type or name is missing, or a JSON field has the wrong shape."
        )
    row["aliases"] = row.pop("aliases_json")
    row["attributes"] = row.pop("attributes_json")
    row["tags"] = row.pop("tags_json")
    return row


def _entity_key(item: Any) -> tuple[str, str]:
    if isinstance(item, dict):
        return str(item.get("entity_type", "")).casefold(), str(
            item.get("name", "")
        ).strip().casefold()
    return item.entity_type.casefold(), item.name.strip().casefold()


def _source_key(item: Any) -> tuple[str, str, str]:
    if isinstance(item, dict):
        source_type = str(item.get("source_type", ""))
        url = str(item.get("url", ""))
        path = str(item.get("local_path", ""))
        title = str(item.get("title", ""))
    else:
        source_type = item.source_type.value
        url = item.url
        path = item.local_path
        title = item.title
    location = (url or path).strip().casefold()
    return source_type.casefold(), title.strip().casefold(), location


def _source_exists(services: ApplicationServices, source_id: str) -> bool:
    try:
        services.sources.get(source_id)
    except LookupError:
        return False
    return True


def _is_workspace_image(services: ApplicationServices, image_path: Path) -> bool:
    try:
        return image_path.resolve().parent == services.profile_images.image_directory.resolve()
    except OSError:
        return False


def _relationship_key(item: Relationship) -> tuple[Any, ...]:
    return (
        item.source_entity_id,
        item.target_entity_id,
        item.relationship_type.casefold(),
        item.start_date,
        item.end_date,
        tuple(sorted(item.source_ids)),
        item.relationship_domain,
    )
