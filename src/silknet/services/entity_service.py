"""Validated entity and custom entity-type operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from silknet.core.enums import EntityType
from silknet.core.exceptions import RecordNotFoundError, ValidationError
from silknet.core.models import CustomEntityType, Entity
from silknet.core.validation import (
    clean_attributes,
    clean_custom_type_fields,
    clean_date,
    clean_entity_type,
    clean_source_ids,
    clean_string_list,
    clean_text,
    clean_url,
    clean_verification_status,
)
from silknet.database.repositories import EntityRepository, SourceRepository


class EntityService:
    def __init__(self, repository: EntityRepository, source_repository: SourceRepository) -> None:
        self.repository = repository
        self.source_repository = source_repository

    def create(
        self,
        *,
        entity_type: str,
        name: str,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        attributes: dict[str, object] | None = None,
        tags: tuple[str, ...] | list[str] = (),
        notes: str = "",
        source_ids: tuple[str, ...] | list[str] = (),
    ) -> Entity:
        type_key = self._validate_entity_type(entity_type)
        now = _now()
        entity = Entity(
            id=str(uuid4()),
            entity_type=type_key,
            name=clean_text(name, "Name", required=True, limit=256),
            description=clean_text(description, "Description"),
            aliases=clean_string_list(aliases, "Aliases"),
            attributes=self._validate_custom_attributes(
                type_key,
                self._validate_person_role(
                    type_key,
                    self._validate_social_profile(
                        type_key, clean_attributes(attributes if attributes is not None else {})
                    ),
                ),
            ),
            tags=clean_string_list(tags, "Tags"),
            notes=clean_text(notes, "Notes"),
            source_ids=self._validate_source_ids(source_ids),
            created_at=now,
            updated_at=now,
        )
        return self.repository.create(entity)

    def update(self, entity_id: str, **changes: object) -> Entity:
        allowed = {
            "entity_type",
            "name",
            "description",
            "aliases",
            "attributes",
            "tags",
            "notes",
            "source_ids",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"Unknown entity fields: {', '.join(sorted(unknown))}.")
        current = self.repository.get(entity_id)
        if current is None:
            raise RecordNotFoundError(f"Entity '{entity_id}' was not found.")

        entity_type = changes.get("entity_type", current.entity_type)
        name = changes.get("name", current.name)
        description = changes.get("description", current.description)
        aliases = changes.get("aliases", current.aliases)
        attributes = changes.get("attributes", current.attributes)
        tags = changes.get("tags", current.tags)
        notes = changes.get("notes", current.notes)
        source_ids = changes.get("source_ids", current.source_ids)
        if not isinstance(entity_type, str) or not isinstance(name, str):
            raise ValidationError("Entity type and name must be text.")
        if not isinstance(description, str) or not isinstance(notes, str):
            raise ValidationError("Description and notes must be text.")
        if not isinstance(aliases, (tuple, list)) or not isinstance(tags, (tuple, list)):
            raise ValidationError("Aliases and tags must be lists of text values.")
        if not isinstance(attributes, dict) or not isinstance(source_ids, (tuple, list)):
            raise ValidationError("Attributes and source IDs must be objects and lists.")

        type_key = self._validate_entity_type(entity_type)
        cleaned_attributes = self._validate_custom_attributes(
            type_key,
            self._validate_person_role(
                type_key, self._validate_social_profile(type_key, clean_attributes(attributes))
            ),
        )
        updated = Entity(
            id=current.id,
            entity_type=type_key,
            name=clean_text(name, "Name", required=True, limit=256),
            description=clean_text(description, "Description"),
            aliases=clean_string_list(aliases, "Aliases"),
            attributes=cleaned_attributes,
            tags=clean_string_list(tags, "Tags"),
            notes=clean_text(notes, "Notes"),
            source_ids=self._validate_source_ids(source_ids),
            created_at=current.created_at,
            updated_at=_now(),
        )
        result = self.repository.update(updated)
        if result is None:
            raise RecordNotFoundError(f"Entity '{entity_id}' was not found.")
        return result

    def get(self, entity_id: str) -> Entity:
        entity = self.repository.get(entity_id)
        if entity is None:
            raise RecordNotFoundError(f"Entity '{entity_id}' was not found.")
        return entity

    def list(self) -> list[Entity]:
        return self.repository.list()

    def delete(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)

    def create_custom_type(
        self,
        *,
        key: str,
        display_name: str,
        fields: tuple[dict[str, object], ...] | list[dict[str, object]] = (),
    ) -> CustomEntityType:
        type_key = clean_entity_type(key)
        if type_key in {entity_type.value for entity_type in EntityType}:
            raise ValidationError("A custom type cannot reuse a built-in entity type key.")
        if self.repository.get_custom_type(type_key) is not None:
            raise ValidationError(f"Custom entity type key '{type_key}' already exists.")
        name = clean_text(display_name, "Custom type name", required=True, limit=128)
        custom_types = self.repository.list_custom_types()
        if any(item.display_name.casefold() == name.casefold() for item in custom_types):
            raise ValidationError(f"A custom entity type named '{name}' already exists.")
        custom_type = CustomEntityType(
            key=type_key,
            display_name=name,
            fields=clean_custom_type_fields(fields),
            created_at=_now(),
        )
        return self.repository.create_custom_type(custom_type)

    def list_custom_types(self) -> list[CustomEntityType]:
        return self.repository.list_custom_types()

    def _validate_entity_type(self, entity_type: str) -> str:
        type_key = clean_entity_type(entity_type)
        if type_key not in {item.value for item in EntityType}:
            if self.repository.get_custom_type(type_key) is None:
                raise ValidationError(
                    f"Custom entity type '{type_key}' is not registered in this workspace."
                )
        return type_key

    def _validate_source_ids(self, source_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        ids = clean_source_ids(source_ids)
        for source_id in ids:
            if self.source_repository.get(source_id) is None:
                raise RecordNotFoundError(f"Source '{source_id}' was not found.")
        return ids

    def _validate_custom_attributes(
        self, type_key: str, attributes: dict[str, object]
    ) -> dict[str, object]:
        custom_type = self.repository.get_custom_type(type_key)
        if custom_type is None:
            return attributes
        for field in custom_type.fields:
            key = str(field["key"])
            value = attributes.get(key)
            label = str(field["display_name"])
            if value is None or value == "":
                if field["required"]:
                    raise ValidationError(f"Custom field '{label}' is required.")
                continue
            field_type = field["field_type"]
            if field_type == "text" and not isinstance(value, str):
                raise ValidationError(f"Custom field '{label}' must be text.")
            if field_type == "number" and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                raise ValidationError(f"Custom field '{label}' must be a number.")
            if field_type == "boolean" and not isinstance(value, bool):
                raise ValidationError(f"Custom field '{label}' must be true or false.")
            if field_type == "date":
                if not isinstance(value, str):
                    raise ValidationError(f"Custom field '{label}' must be a date.")
                clean_date(value, label)
            if field_type == "url":
                if not isinstance(value, str):
                    raise ValidationError(f"Custom field '{label}' must be a URL.")
                clean_url(value)
        return attributes

    def _validate_person_role(
        self, type_key: str, attributes: dict[str, object]
    ) -> dict[str, object]:
        if type_key != EntityType.PERSON.value:
            return attributes
        role = attributes.get("role")
        if role is None or role == "":
            attributes.pop("role", None)
            return attributes
        if not isinstance(role, str):
            raise ValidationError("Person role must be text.")
        cleaned = clean_text(role, "Role", limit=128)
        if cleaned:
            attributes["role"] = cleaned
        else:
            attributes.pop("role", None)
        return attributes

    def _validate_social_profile(
        self, type_key: str, attributes: dict[str, object]
    ) -> dict[str, object]:
        if type_key != EntityType.SOCIAL_PROFILE.value:
            return attributes
        platform = attributes.get("platform", "")
        profile_url = attributes.get("profile_url", "")
        username = attributes.get("username", "")
        if not isinstance(platform, str):
            raise ValidationError("Social profile platform must be text.")
        if not isinstance(profile_url, str) or not isinstance(username, str):
            raise ValidationError("Social profile URL and username must be text.")
        attributes["platform"] = clean_text(platform, "Platform", required=True, limit=64)
        attributes["profile_url"] = clean_url(profile_url)
        attributes["username"] = clean_text(username, "Username", limit=256)
        status = clean_verification_status(str(attributes.get("verification_status", "unverified")))
        attributes["verification_status"] = status.value
        return attributes


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
