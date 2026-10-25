"""User-defined social platforms stored with the local workspace."""

from silknet.core.validation import clean_text
from silknet.database.repositories import PlatformRepository

BUILTIN_PLATFORMS = (
    "Instagram",
    "Facebook",
    "X",
    "LinkedIn",
    "TikTok",
    "YouTube",
    "Reddit",
    "Telegram",
    "Discord",
    "Pinterest",
    "Snapchat",
    "Twitch",
    "Threads",
    "Bluesky",
    "Mastodon",
    "GitHub",
)


class PlatformService:
    def __init__(self, repository: PlatformRepository) -> None:
        self.repository = repository

    def list(self) -> list[str]:
        custom = self.repository.list_custom()
        known = {name.casefold() for name in BUILTIN_PLATFORMS}
        return [*BUILTIN_PLATFORMS, *(name for name in custom if name.casefold() not in known)]

    def add(self, name: str) -> str:
        cleaned = clean_text(name, "Platform", required=True, limit=64)
        existing = self.list()
        match = next((item for item in existing if item.casefold() == cleaned.casefold()), None)
        if match:
            return match
        custom = self.repository.list_custom()
        custom.append(cleaned)
        self.repository.save_custom(custom)
        return cleaned
