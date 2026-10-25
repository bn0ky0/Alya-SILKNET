"""Per-user application paths and settings."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

_ACCENT_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_APP_DIRECTORY = "SILKNET"

#: The display scale is a fixed six-step control instead of a free slider.
#: It is deliberately capped at 100% so the window layout never grows with it.
UI_SCALE_OPTIONS = (0.75, 0.8, 0.85, 0.9, 0.95, 1.0)


def nearest_ui_scale(value: float) -> float:
    """Return the fixed UI scale option closest to ``value``."""
    return min(UI_SCALE_OPTIONS, key=lambda option: (abs(option - value), option))


#: Themes shipped with Alya SILKNET. ``dark`` and ``light`` follow the chosen
#: accent color; the remaining themes keep their own tuned accent palettes.
SUPPORTED_THEMES = frozenset({"dark", "light", "pink", "dark-red", "dark-purple", "dark-green"})

#: Limited, curated secondary colors for the dark and light themes.
DARK_ACCENTS: dict[str, tuple[str, str]] = {
    "baby-blue": ("Baby blue", "#9BB7FF"),
    "violet": ("Violet", "#B69CFF"),
    "crimson": ("Crimson", "#EC7D8F"),
    "mint": ("Mint", "#79D7B1"),
    "amber": ("Amber", "#E9BA71"),
}
DEFAULT_DARK_ACCENT = DARK_ACCENTS["baby-blue"][1]
PRESET_ACCENT_COLORS = frozenset(color for _label, color in DARK_ACCENTS.values())

# Themes that existed in earlier versions are folded into the closest current one.
_LEGACY_THEMES = {
    "ocean": "dark",
    "amber": "dark",
    "custom": "dark",
    "high-contrast": "dark",
    "glass": "light",
}
_SETTINGS_KEYS = frozenset({"theme", "accent_color", "ui_scale"})


class SettingsError(ValueError):
    """The settings file could not be used."""


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def log_file(self) -> Path:
        return self.config_dir / "logs" / "silknet.log"

    @property
    def database_file(self) -> Path:
        return self.data_dir / "silknet.sqlite3"

    def ensure_directories(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
        platform: str | None = None,
    ) -> AppPaths:
        env = os.environ if environ is None else environ
        user_home = Path.home() if home is None else home
        os_name = os.name if platform is None else platform

        if os_name == "nt":
            default_config = Path(env.get("APPDATA", user_home / "AppData" / "Roaming"))
            default_data = Path(env.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
        else:
            default_config = Path(env.get("XDG_CONFIG_HOME", user_home / ".config"))
            default_data = Path(env.get("XDG_DATA_HOME", user_home / ".local" / "share"))

        config_dir = Path(env.get("SILKNET_CONFIG_DIR", default_config / _APP_DIRECTORY))
        data_dir = Path(env.get("SILKNET_DATA_DIR", default_data / _APP_DIRECTORY))
        return cls(config_dir=config_dir, data_dir=data_dir)


@dataclass(frozen=True)
class AppSettings:
    """Appearance preferences shared by the window, pages and settings screen."""

    theme: str = "dark"
    accent_color: str = DEFAULT_DARK_ACCENT
    #: Scales typography and button padding only. Window geometry, spacing and
    #: card dimensions stay fixed so the layout never has to reflow.
    ui_scale: float = 0.9

    def __post_init__(self) -> None:
        if not isinstance(self.theme, str):
            raise SettingsError("Theme must be one of the themes included with SILKNET.")
        theme = self.theme.strip().casefold()
        if theme not in SUPPORTED_THEMES:
            raise SettingsError("Theme must be one of the themes included with SILKNET.")
        object.__setattr__(self, "theme", theme)

        if not isinstance(self.accent_color, str) or not _ACCENT_PATTERN.fullmatch(
            self.accent_color
        ):
            raise SettingsError("Accent color must be a six-digit hexadecimal color.")
        object.__setattr__(self, "accent_color", self.accent_color.upper())

        if isinstance(self.ui_scale, bool) or not isinstance(self.ui_scale, (int, float)):
            raise SettingsError("UI scale must be a number.")
        if not UI_SCALE_OPTIONS[0] <= self.ui_scale <= UI_SCALE_OPTIONS[-1]:
            raise SettingsError("UI scale must be between 75% and 100%.")
        object.__setattr__(self, "ui_scale", nearest_ui_scale(float(self.ui_scale)))


def load_settings(path: Path) -> AppSettings:
    if not path.exists():
        return AppSettings()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SettingsError("Settings file must contain a JSON object.")
        raw.pop("text_scale", None)
        theme = raw.get("theme")
        if theme is not None:
            raw["theme"] = _LEGACY_THEMES.get(theme, theme)
        else:
            raw.pop("theme", None)
        if not isinstance(raw.get("accent_color"), str) or not _ACCENT_PATTERN.fullmatch(
            raw["accent_color"]
        ):
            raw["accent_color"] = DEFAULT_DARK_ACCENT
        legacy_scale = raw.get("ui_scale")
        if isinstance(legacy_scale, (int, float)) and not isinstance(legacy_scale, bool):
            raw["ui_scale"] = nearest_ui_scale(float(legacy_scale))
        known = {key: raw[key] for key in _SETTINGS_KEYS if key in raw}
        return AppSettings(**known)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise SettingsError(f"Could not read settings at {path}: {exc}") from exc


def save_settings(path: Path, settings: AppSettings) -> None:
    temp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(asdict(settings), temp_file, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        raise SettingsError(f"Could not save settings at {path}: {exc}") from exc
