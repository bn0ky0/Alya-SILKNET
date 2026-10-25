"""Stable vocabulary for persisted SILKNET records."""

from enum import StrEnum


class EntityType(StrEnum):
    PERSON = "person"
    SOCIAL_PROFILE = "social_profile"
    ORGANIZATION = "organization"
    WEBSITE = "website"
    EMAIL = "email"
    PHONE = "phone"
    LOCATION = "location"
    DOCUMENT = "document"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    USER_REPORTED = "user_reported"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"


class SourceType(StrEnum):
    PUBLIC_URL = "public_url"
    OBSERVATION = "observation"
    LOCAL_DOCUMENT = "local_document"
    NOTE = "note"
    OTHER = "other"
