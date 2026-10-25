"""Errors shown to the user or handled by the app."""


class ValidationError(ValueError):
    """The supplied values are not valid for this record."""


class RecordNotFoundError(LookupError):
    """The requested record does not exist."""


class DuplicateRelationshipError(ValueError):
    """The same relationship claim is already stored."""


class MigrationError(RuntimeError):
    """The database could not be upgraded safely."""


class IntegrationError(RuntimeError):
    """An optional external provider did not complete its request."""
