"""Validated provenance source operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from silknet.core.enums import SourceType
from silknet.core.exceptions import RecordNotFoundError, ValidationError
from silknet.core.models import Source
from silknet.core.validation import clean_date, clean_source_type, clean_text, clean_url
from silknet.database.repositories import SourceRepository


class SourceService:
    def __init__(self, repository: SourceRepository) -> None:
        self.repository = repository

    def create(
        self,
        *,
        title: str,
        source_type: SourceType | str,
        url: str = "",
        local_path: str = "",
        observed_at: str | None = None,
        notes: str = "",
        content_hash: str = "",
    ) -> Source:
        kind = clean_source_type(source_type)
        normalized_url = clean_url(url)
        normalized_path = clean_text(local_path, "Local file path", limit=2_048)
        if kind is SourceType.PUBLIC_URL and not normalized_url:
            raise ValidationError("A public URL source requires a URL.")
        if kind is SourceType.LOCAL_DOCUMENT and not normalized_path:
            raise ValidationError("A local document source requires a file path.")
        source = Source(
            id=str(uuid4()),
            title=clean_text(title, "Source title", required=True, limit=512),
            source_type=kind,
            url=normalized_url,
            local_path=normalized_path,
            observed_at=clean_date(observed_at, "Observed date"),
            notes=clean_text(notes, "Source notes"),
            content_hash=clean_text(content_hash, "Content hash", limit=256),
            created_at=datetime.now(UTC).isoformat(timespec="microseconds"),
        )
        return self.repository.create(source)

    def get(self, source_id: str) -> Source:
        source = self.repository.get(source_id)
        if source is None:
            raise RecordNotFoundError(f"Source '{source_id}' was not found.")
        return source

    def list(self) -> list[Source]:
        return self.repository.list()

    def update(self, source: Source) -> Source:
        kind = clean_source_type(source.source_type)
        url = clean_url(source.url)
        local_path = clean_text(source.local_path, "Local file path", limit=2_048)
        if kind is SourceType.PUBLIC_URL and not url:
            raise ValidationError("A public URL source requires a URL.")
        if kind is SourceType.LOCAL_DOCUMENT and not local_path:
            raise ValidationError("A local document source requires a file path.")
        updated = Source(
            id=source.id,
            title=clean_text(source.title, "Source title", required=True, limit=512),
            source_type=kind,
            url=url,
            local_path=local_path,
            observed_at=clean_date(source.observed_at, "Observed date"),
            notes=clean_text(source.notes, "Source notes"),
            content_hash=clean_text(source.content_hash, "Content hash", limit=256),
            created_at=source.created_at,
        )
        result = self.repository.update(updated)
        if result is None:
            raise RecordNotFoundError(f"Source '{source.id}' was not found.")
        return result

    def delete(self, source_id: str) -> bool:
        return self.repository.delete(source_id)
