from dataclasses import replace

import pytest

from silknet.core.exceptions import ValidationError


def test_source_create_and_url_validation(data_services) -> None:
    source = data_services.sources.create(
        title="Public report",
        source_type="public_url",
        url="https://example.test/report",
        observed_at="2026-10-01",
        notes="User provided this link.",
    )

    assert data_services.sources.get(source.id) == source
    with pytest.raises(ValidationError, match="http or https"):
        data_services.sources.create(
            title="Unsafe URL", source_type="public_url", url="javascript:alert(1)"
        )
    with pytest.raises(ValidationError, match="http or https"):
        data_services.sources.create(
            title="Malformed URL", source_type="public_url", url="https://[invalid"
        )
    with pytest.raises(ValidationError, match="requires a URL"):
        data_services.sources.create(title="Missing URL", source_type="public_url")
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        data_services.sources.create(
            title="Bad date", source_type="observation", observed_at="yesterday"
        )
    with pytest.raises(ValidationError, match="requires a file path"):
        data_services.sources.create(title="Missing file", source_type="local_document")

    revised = data_services.sources.update(replace(source, title="Updated public report"))
    assert revised.id == source.id
    assert data_services.sources.get(source.id).title == "Updated public report"


def test_deleting_source_removes_links_but_not_entities(data_services) -> None:
    source = data_services.sources.create(title="Manual note", source_type="note")
    entity = data_services.entities.create(
        entity_type="person", name="Recorded person", source_ids=[source.id]
    )
    assert data_services.sources.delete(source.id)

    reloaded = data_services.entities.get(entity.id)
    assert reloaded.source_ids == ()
    assert reloaded.name == "Recorded person"
