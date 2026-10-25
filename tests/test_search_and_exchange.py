import json
from pathlib import Path

import pytest

from silknet.core.enums import SourceType, VerificationStatus
from silknet.core.exceptions import IntegrationError, ValidationError
from silknet.database.connection import initialize_database
from silknet.services.container import create_services
from silknet.services.data_exchange_service import DataExchangeService
from silknet.services.integrations import IntegrationRegistry
from silknet.services.search_service import SearchService


def test_local_search_matches_entities_claims_and_sources(data_services) -> None:
    source = data_services.sources.create(title="Harbor archive", source_type=SourceType.NOTE)
    first = data_services.entities.create(
        entity_type="person", name="Nadia", tags=["follow-up"], source_ids=[source.id]
    )
    second = data_services.entities.create(entity_type="organization", name="Harbor Office")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="visited",
        verification_status=VerificationStatus.DISPUTED,
        confidence_notes="Account needs confirmation",
    )
    search = SearchService(
        data_services.entities, data_services.relationships, data_services.sources
    )

    assert [result.kind for result in search.search("follow-up", result_kind="entity")] == [
        "entity"
    ]
    assert {result.kind for result in search.search("Harbor")} == {
        "entity",
        "relationship",
        "source",
    }
    status_results = search.search("", verification_status="disputed")
    assert len(status_results) == 1
    assert status_results[0].kind == "relationship"


def test_search_kind_filter_alone_lists_records_of_that_kind(data_services) -> None:
    data_services.sources.create(title="Field note", source_type=SourceType.NOTE)
    first = data_services.entities.create(entity_type="person", name="Mina")
    second = data_services.entities.create(entity_type="organization", name="Atlas")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works with",
    )
    search = SearchService(
        data_services.entities, data_services.relationships, data_services.sources
    )

    assert search.search("") == []
    assert {result.kind for result in search.search("", result_kind="entity")} == {"entity"}
    assert {result.kind for result in search.search("", result_kind="relationship")} == {
        "relationship"
    }
    assert {result.kind for result in search.search("", result_kind="source")} == {"source"}
    assert len(search.search("", result_kind="entity")) == 2
    assert len(search.search("", result_kind="relationship")) == 1
    assert len(search.search("", result_kind="source")) == 1


def test_json_export_import_preserves_links_and_skips_duplicates(
    data_services, tmp_path: Path
) -> None:
    source = data_services.sources.create(title="Case note", source_type="note")
    parent = data_services.entities.create(
        entity_type="person", name="Salma", source_ids=[source.id]
    )
    child = data_services.entities.create(entity_type="person", name="Tarek")
    data_services.family.create_relationship(
        source_entity_id=parent.id,
        target_entity_id=child.id,
        relationship_type="foster parent",
        verification_status="user_reported",
        source_ids=[source.id],
    )
    exchange = DataExchangeService(data_services)
    archive = tmp_path / "workspace.json"
    exchange.export_json(archive)

    target_path = tmp_path / "target.sqlite3"
    initialize_database(target_path)
    target = create_services(target_path)
    target_exchange = DataExchangeService(target)
    preview = target_exchange.preview_json(archive)
    assert preview.can_import
    assert (preview.new_entities, preview.new_sources, preview.relationships) == (2, 1, 1)

    summary = target_exchange.import_json(archive)
    assert summary.imported_entities == 2
    assert summary.imported_sources == 1
    assert summary.imported_relationships == 1
    assert target.family.relationships_for_people()[0].relationship_type == "foster parent"
    assert target.entities.get(
        target.family.relationships_for_people()[0].source_entity_id
    ).source_ids

    repeated = target_exchange.import_json(archive)
    assert repeated.skipped_entities == 2
    assert repeated.skipped_sources == 1
    assert repeated.skipped_relationships == 1


def test_csv_round_trip_and_duplicate_preview(data_services, tmp_path: Path) -> None:
    data_services.entities.create(
        entity_type="person",
        name="Omar, Jr.",
        aliases=["Omar"],
        attributes={"birth_year": 1998},
        tags=["review"],
    )
    exchange = DataExchangeService(data_services)
    csv_file = tmp_path / "entities.csv"
    exchange.export_csv(csv_file)
    target_path = tmp_path / "csv-target.sqlite3"
    initialize_database(target_path)
    target_exchange = DataExchangeService(create_services(target_path))
    assert target_exchange.preview_csv(csv_file).new_entities == 1
    summary = target_exchange.import_csv(csv_file)
    assert summary.imported_entities == 1
    target = target_exchange.services.entities.list()[0]
    assert target.name == "Omar, Jr."
    assert target.aliases == ("Omar",)
    assert target.attributes == {"birth_year": 1998}
    assert target_exchange.preview_csv(csv_file).duplicate_entities == 1


def test_invalid_json_preview_does_not_change_workspace(data_services, tmp_path: Path) -> None:
    file = tmp_path / "bad.json"
    file.write_text(json.dumps({"format": "other", "version": 1}), encoding="utf-8")
    exchange = DataExchangeService(data_services)

    preview = exchange.preview_json(file)

    assert not preview.can_import
    assert len(preview.errors) == 1
    with pytest.raises(ValidationError, match="Import preview found errors"):
        exchange.import_json(file)
    assert data_services.entities.list() == []


def test_failed_import_rolls_back_records_already_written(
    data_services, tmp_path: Path, monkeypatch
) -> None:
    source_workspace = tmp_path / "source.sqlite3"
    initialize_database(source_workspace)
    source_services = create_services(source_workspace)
    source_services.sources.create(title="First", source_type="note")
    source_services.sources.create(title="Second", source_type="note")
    archive = tmp_path / "two-sources.json"
    DataExchangeService(source_services).export_json(archive)

    original_create = data_services.sources.create
    calls = 0

    def fail_second_source(**values):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated write failure")
        return original_create(**values)

    monkeypatch.setattr(data_services.sources, "create", fail_second_source)
    with pytest.raises(RuntimeError, match="simulated write failure"):
        DataExchangeService(data_services).import_json(archive)

    assert data_services.sources.list() == []
    assert data_services.entities.list() == []


def test_optional_provider_failures_are_reported() -> None:
    class BrokenProvider:
        name = "Example provider"

        def search(self, query: str) -> list[dict[str, str]]:
            raise OSError("service is unavailable")

    registry = IntegrationRegistry()
    registry.register(BrokenProvider())

    with pytest.raises(IntegrationError, match="service is unavailable"):
        registry.search("example provider", "person")


def test_exports_cannot_overwrite_the_workspace_database(data_services) -> None:
    exchange = DataExchangeService(data_services)
    database = data_services.backups.database_file
    before = database.read_bytes()

    with pytest.raises(ValidationError, match="separate file"):
        exchange.export_json(database)
    with pytest.raises(ValidationError, match="separate file"):
        exchange.export_csv(database)

    assert database.read_bytes() == before
