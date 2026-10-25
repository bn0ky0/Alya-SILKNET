from pathlib import Path

import pytest

from silknet.core.exceptions import RecordNotFoundError, ValidationError
from silknet.database.repositories import EntityRepository, SourceRepository
from silknet.services.entity_service import EntityService


def test_entity_creation_update_and_reload(data_services) -> None:
    entities = data_services.entities
    entity = entities.create(
        entity_type="person",
        name="  Ada Example  ",
        aliases=["Ada", "ada", " A. Example "],
        tags=["research", "Research"],
        attributes={"birth_year": 1990, "links": ["profile"]},
    )

    assert entity.name == "Ada Example"
    assert entity.aliases == ("Ada", "A. Example")
    assert entity.tags == ("research",)
    assert entity.attributes == {"birth_year": 1990, "links": ["profile"]}
    assert entities.get(entity.id) == entity

    updated = entities.update(entity.id, name="Ada E.", notes="User-reported detail")
    reloaded = entities.get(entity.id)
    assert updated.id == entity.id
    assert reloaded.name == "Ada E."
    assert reloaded.notes == "User-reported detail"
    assert reloaded.created_at == entity.created_at
    assert len(entities.list()) == 1


def test_entity_validation_and_delete(data_services) -> None:
    entities = data_services.entities
    with pytest.raises(ValidationError, match="Name is required"):
        entities.create(entity_type="person", name="  ")
    with pytest.raises(ValidationError, match="JSON-compatible"):
        entities.create(entity_type="person", name="Invalid", attributes={"bad": object()})

    entity = entities.create(entity_type="organization", name="Example Group")
    assert entities.delete(entity.id)
    assert not entities.delete(entity.id)
    with pytest.raises(RecordNotFoundError, match="not found"):
        entities.get(entity.id)


def test_person_role_is_optional_and_validated(data_services) -> None:
    entities = data_services.entities
    person = entities.create(
        entity_type="person",
        name="Role holder",
        attributes={"role": "  lead analyst  "},
    )
    assert person.attributes["role"] == "lead analyst"

    without_role = entities.create(
        entity_type="person",
        name="No role",
        attributes={"role": "   "},
    )
    assert "role" not in without_role.attributes

    with pytest.raises(ValidationError, match="role must be text"):
        entities.create(
            entity_type="person",
            name="Bad role",
            attributes={"role": 7},
        )

    updated = entities.update(person.id, attributes={"role": "founder"})
    assert updated.attributes["role"] == "founder"


def test_custom_entity_type_requires_registered_schema(data_services) -> None:
    entities = data_services.entities
    with pytest.raises(ValidationError, match="not registered"):
        entities.create(entity_type="vehicle", name="Car 1")

    custom_type = entities.create_custom_type(
        key="vehicle",
        display_name="Vehicle",
        fields=[
            {
                "key": "registration",
                "display_name": "Registration",
                "field_type": "text",
                "required": True,
            }
        ],
    )
    with pytest.raises(ValidationError, match="Registration.*required"):
        entities.create(entity_type=custom_type.key, name="Car 1")
    vehicle = entities.create(
        entity_type=custom_type.key,
        name="Car 1",
        attributes={"registration": "ABC-123"},
    )

    assert vehicle.entity_type == "vehicle"
    assert entities.list_custom_types()[0].fields[0]["key"] == "registration"
    with pytest.raises(ValidationError, match="Registration.*text"):
        entities.create(
            entity_type=custom_type.key,
            name="Bad vehicle",
            attributes={"registration": 12},
        )
    with pytest.raises(ValidationError, match="lowercase letters"):
        entities.create_custom_type(key="invalid-key", display_name="Invalid", fields=[])


def test_entity_source_links_are_transactional_and_referential(data_services) -> None:
    source = data_services.sources.create(
        title="Manual note", source_type="note", notes="Observed by the user"
    )
    entity = data_services.entities.create(
        entity_type="person", name="Source-backed person", source_ids=[source.id]
    )
    assert data_services.entities.get(entity.id).source_ids == (source.id,)

    with pytest.raises(RecordNotFoundError, match="Source"):
        data_services.entities.create(
            entity_type="person",
            name="Invalid source link",
            source_ids=["00000000-0000-0000-0000-000000000000"],
        )
    assert len(data_services.entities.list()) == 1

    with pytest.raises(RecordNotFoundError, match="Source"):
        data_services.entities.update(
            entity.id,
            name="Should roll back",
            source_ids=["00000000-0000-0000-0000-000000000000"],
        )
    assert data_services.entities.get(entity.id).name == "Source-backed person"


def test_repositories_keep_user_database_path_isolated(tmp_path: Path) -> None:
    database_file = tmp_path / "data" / "records.sqlite3"
    from silknet.database.connection import initialize_database

    initialize_database(database_file)
    service = EntityService(EntityRepository(database_file), SourceRepository(database_file))
    created = service.create(entity_type="email", name="person@example.test")

    assert service.get(created.id).name == "person@example.test"
