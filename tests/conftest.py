import os
from typing import NamedTuple

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class DataServices(NamedTuple):
    entities: object
    relationships: object
    sources: object
    graph_layout: object
    family: object
    profile_images: object
    platforms: object
    backups: object


@pytest.fixture
def data_services(tmp_path):
    from silknet.database.connection import initialize_database
    from silknet.database.repositories import (
        EntityRepository,
        GraphLayoutRepository,
        PlatformRepository,
        RelationshipRepository,
        SourceRepository,
    )
    from silknet.services.backup_service import BackupService
    from silknet.services.entity_service import EntityService
    from silknet.services.family_service import FamilyService
    from silknet.services.graph_layout_service import GraphLayoutService
    from silknet.services.platform_service import PlatformService
    from silknet.services.profile_image_service import ProfileImageService
    from silknet.services.relationship_service import RelationshipService
    from silknet.services.source_service import SourceService

    database_file = tmp_path / "workspace" / "silknet.sqlite3"
    initialize_database(database_file)
    entities_repository = EntityRepository(database_file)
    sources_repository = SourceRepository(database_file)
    entities = EntityService(entities_repository, sources_repository)
    relationships = RelationshipService(
        RelationshipRepository(database_file), entities_repository, sources_repository
    )
    return DataServices(
        entities,
        relationships,
        SourceService(sources_repository),
        GraphLayoutService(GraphLayoutRepository(database_file)),
        FamilyService(entities, relationships),
        ProfileImageService(database_file.parent / "profile-images"),
        PlatformService(PlatformRepository(database_file)),
        BackupService(database_file, database_file.parent / "profile-images"),
    )
