"""Application-level wiring for persistence services."""

from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    entities: EntityService
    relationships: RelationshipService
    sources: SourceService
    graph_layout: GraphLayoutService
    family: FamilyService
    profile_images: ProfileImageService
    platforms: PlatformService
    backups: BackupService


def create_services(database_file: Path) -> ApplicationServices:
    entity_repository = EntityRepository(database_file)
    source_repository = SourceRepository(database_file)
    entities = EntityService(entity_repository, source_repository)
    profile_images = ProfileImageService(database_file.parent / "profile-images")
    relationships = RelationshipService(
        RelationshipRepository(database_file), entity_repository, source_repository
    )
    return ApplicationServices(
        entities=entities,
        relationships=relationships,
        sources=SourceService(source_repository),
        graph_layout=GraphLayoutService(GraphLayoutRepository(database_file)),
        family=FamilyService(entities, relationships),
        profile_images=profile_images,
        platforms=PlatformService(PlatformRepository(database_file)),
        backups=BackupService(database_file, profile_images.image_directory),
    )
