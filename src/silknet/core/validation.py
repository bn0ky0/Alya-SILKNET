"""Input normalization and validation for domain services."""

from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urlsplit
from uuid import UUID

from silknet.core.enums import EntityType, SourceType, VerificationStatus
from silknet.core.exceptions import ValidationError

_CUSTOM_TYPE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_FIELD_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FIELD_TYPES = {"text", "number", "date", "boolean", "url"}


def clean_text(value: str, label: str, *, required: bool = False, limit: int = 10_000) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    result = value.strip()
    if required and not result:
        raise ValidationError(f"{label} is required.")
    if len(result) > limit:
        raise ValidationError(f"{label} must be {limit} characters or fewer.")
    return result


def clean_entity_type(value: str) -> str:
    result = clean_text(value, "Entity type", required=True, limit=64).lower()
    if result in {entity_type.value for entity_type in EntityType}:
        return result
    if not _CUSTOM_TYPE_KEY.fullmatch(result):
        raise ValidationError(
            "Custom entity type keys must use lowercase letters, numbers, and underscores."
        )
    return result


def clean_string_list(values: tuple[str, ...] | list[str], label: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (tuple, list)):
        raise ValidationError(f"{label} must be a list of text values.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = clean_text(value, label, limit=256)
        if not item:
            continue
        folded = item.casefold()
        if folded not in seen:
            seen.add(folded)
            cleaned.append(item)
    if len(cleaned) > 100:
        raise ValidationError(f"{label} can contain at most 100 values.")
    return tuple(cleaned)


def clean_attributes(attributes: dict[str, object]) -> dict[str, object]:
    if not isinstance(attributes, dict) or not all(isinstance(key, str) for key in attributes):
        raise ValidationError("Attributes must be an object with text keys.")
    try:
        encoded = json.dumps(attributes, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Attributes must contain only JSON-compatible values.") from exc
    if len(encoded) > 1_000_000:
        raise ValidationError("Attributes are too large to store (maximum 1 MB).")
    return json.loads(encoded)


def clean_date(value: str | None, label: str) -> str | None:
    if value is None or value == "":
        return None
    result = clean_text(value, label, limit=10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", result):
        raise ValidationError(f"{label} must use YYYY-MM-DD format.")
    try:
        date.fromisoformat(result)
    except ValueError as exc:
        raise ValidationError(f"{label} must use YYYY-MM-DD format.") from exc
    return result


def clean_verification_status(value: VerificationStatus | str) -> VerificationStatus:
    try:
        return VerificationStatus(value)
    except ValueError as exc:
        choices = ", ".join(status.value for status in VerificationStatus)
        raise ValidationError(f"Verification status must be one of: {choices}.") from exc


def clean_source_type(value: SourceType | str) -> SourceType:
    try:
        return SourceType(value)
    except ValueError as exc:
        choices = ", ".join(source_type.value for source_type in SourceType)
        raise ValidationError(f"Source type must be one of: {choices}.") from exc


def clean_url(value: str) -> str:
    result = clean_text(value, "Source URL", limit=2_048)
    if not result:
        return result
    try:
        parsed = urlsplit(result)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Source URL must be a complete http or https URL.") from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValidationError("Source URL must be a complete http or https URL.")
    if port is not None and not 1 <= port <= 65_535:
        raise ValidationError("Source URL port must be between 1 and 65535.")
    return result


def clean_source_ids(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    source_ids = clean_string_list(values, "Source IDs")
    canonical_ids: list[str] = []
    for source_id in source_ids:
        try:
            canonical_ids.append(str(UUID(source_id)))
        except ValueError as exc:
            raise ValidationError("Source IDs must be valid record identifiers.") from exc
    return tuple(sorted(canonical_ids))


def clean_custom_type_fields(
    fields: tuple[dict[str, object], ...] | list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    if not isinstance(fields, (tuple, list)):
        raise ValidationError("Custom type fields must be a list.")
    cleaned: list[dict[str, object]] = []
    seen: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValidationError("Each custom field must be an object.")
        key = clean_text(field.get("key", ""), "Field key", required=True, limit=64).lower()
        if not _FIELD_KEY.fullmatch(key):
            raise ValidationError(
                "Field keys must use lowercase letters, numbers, and underscores."
            )
        if key in seen:
            raise ValidationError(f"Custom field '{key}' is duplicated.")
        seen.add(key)
        display_name = clean_text(
            field.get("display_name", ""), "Field name", required=True, limit=128
        )
        field_type = clean_text(
            field.get("field_type", "text"), "Field type", required=True, limit=16
        )
        if field_type not in _FIELD_TYPES:
            allowed_types = ", ".join(sorted(_FIELD_TYPES))
            raise ValidationError(f"Field type must be one of: {allowed_types}.")
        required = field.get("required", False)
        if not isinstance(required, bool):
            raise ValidationError("Custom field 'required' must be true or false.")
        cleaned.append(
            {
                "key": key,
                "display_name": display_name,
                "field_type": field_type,
                "required": required,
            }
        )
    if len(cleaned) > 100:
        raise ValidationError("A custom entity type can define at most 100 fields.")
    return tuple(cleaned)
