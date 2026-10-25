"""Immutable domain records persisted by SILKNET."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from silknet.core.enums import SourceType, VerificationStatus


@dataclass(frozen=True, slots=True)
class GraphBoard:
    id: str
    name: str
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    entity_type: str
    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    notes: str = ""
    source_ids: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class Relationship:
    id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    description: str = ""
    start_date: str | None = None
    end_date: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    confidence_notes: str = ""
    notes: str = ""
    source_ids: tuple[str, ...] = ()
    created_at: str = ""
    relationship_domain: str = "general"


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    title: str
    source_type: SourceType
    url: str = ""
    local_path: str = ""
    observed_at: str | None = None
    notes: str = ""
    content_hash: str = ""
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class CustomEntityType:
    key: str
    display_name: str
    fields: tuple[dict[str, Any], ...] = ()
    created_at: str = ""
