"""GitHub Releases update checks for Alya SILKNET."""

from __future__ import annotations

import re
from dataclasses import dataclass

from silknet import __version__

#: Public repository used for release downloads and update checks.
UPDATE_REPOSITORY = "bn0ky0/Alya-SILKNET"
LATEST_RELEASE_API = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{UPDATE_REPOSITORY}/releases"
UPDATE_USER_AGENT = f"Alya-SILKNET/{__version__}"
UPDATE_TIMEOUT_MS = 8000

_VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class ReleaseInfo:
    """The latest published release returned by GitHub."""

    version: str
    url: str
    notes: str = ""
    published_at: str = ""


def version_key(version: str) -> tuple[int, ...]:
    """Return a comparable tuple for tags such as ``v0.1.2``."""
    match = _VERSION_PATTERN.search(version.strip())
    if match is None:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str) -> bool:
    """Return whether ``latest`` is a later version than ``current``."""
    return version_key(latest) > version_key(current)


def parse_release(payload: object, *, fallback_url: str = RELEASES_PAGE) -> ReleaseInfo:
    """Turn a GitHub release payload into :class:`ReleaseInfo`.

    Raises :class:`ValueError` when the payload does not contain a version.
    """
    if not isinstance(payload, dict):
        raise ValueError("The update response was not a GitHub release.")

    tag = payload.get("tag_name") or payload.get("name")
    if not isinstance(tag, str) or not tag.strip():
        raise ValueError("The latest release has no version tag.")

    url = payload.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        url = fallback_url

    notes = payload.get("body")
    published = payload.get("published_at")
    return ReleaseInfo(
        version=tag.strip().lstrip("vV"),
        url=url,
        notes=notes.strip() if isinstance(notes, str) else "",
        published_at=published if isinstance(published, str) else "",
    )
