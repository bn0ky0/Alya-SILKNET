import json
from pathlib import Path

import pytest

from silknet.config import (
    DARK_ACCENTS,
    DEFAULT_DARK_ACCENT,
    PRESET_ACCENT_COLORS,
    SUPPORTED_THEMES,
    UI_SCALE_OPTIONS,
    AppPaths,
    AppSettings,
    SettingsError,
    load_settings,
    save_settings,
)


def test_windows_paths_use_separate_per_user_config_and_data_dirs(tmp_path: Path) -> None:
    paths = AppPaths.from_environment(
        {"APPDATA": str(tmp_path / "roaming"), "LOCALAPPDATA": str(tmp_path / "local")},
        home=tmp_path,
        platform="nt",
    )

    assert paths.config_dir == tmp_path / "roaming" / "SILKNET"
    assert paths.data_dir == tmp_path / "local" / "SILKNET"
    assert paths.database_file == paths.data_dir / "silknet.sqlite3"


def test_environment_overrides_are_respected(tmp_path: Path) -> None:
    config = tmp_path / "custom-config"
    data = tmp_path / "custom-data"
    paths = AppPaths.from_environment(
        {"SILKNET_CONFIG_DIR": str(config), "SILKNET_DATA_DIR": str(data)}, home=tmp_path
    )

    assert paths.config_dir == config
    assert paths.data_dir == data


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    settings_file = tmp_path / "config" / "settings.json"
    settings = AppSettings(theme="light", accent_color="#123ABC")

    save_settings(settings_file, settings)

    assert load_settings(settings_file) == settings
    assert "motion_enabled" not in json.loads(settings_file.read_text(encoding="utf-8"))
    with pytest.raises(SettingsError, match="Theme"):
        AppSettings(theme="sepia")
    with pytest.raises(SettingsError, match="hexadecimal"):
        AppSettings(accent_color="violet")


def test_invalid_settings_file_is_actionable(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"theme": "unknown"}), encoding="utf-8")

    with pytest.raises(SettingsError, match="Theme"):
        load_settings(settings_file)


def test_non_utf8_settings_file_raises_settings_error(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_bytes(b"\xff\xfe\x00not utf8")

    with pytest.raises(SettingsError, match="Could not read settings"):
        load_settings(settings_file)


def test_legacy_theme_and_text_scale_settings_are_migrated(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "theme": "high-contrast",
                "text_scale": 1.4,
                "ui_scale": 1.2,
                "accent_color": "#9bb7ff",
                "motion_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.theme == "dark"
    assert settings.ui_scale == pytest.approx(1.0)
    assert settings.accent_color == "#9BB7FF"
    assert not hasattr(settings, "motion_enabled")


def test_saved_glass_theme_migrates_to_light(tmp_path: Path) -> None:
    assert len(SUPPORTED_THEMES) == 6
    assert "glass" not in SUPPORTED_THEMES
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"theme": "glass"}), encoding="utf-8")

    assert load_settings(settings_file).theme == "light"
    with pytest.raises(SettingsError, match="Theme"):
        AppSettings(theme="glass")


def test_unusable_accent_and_unknown_keys_fall_back(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"accent_color": "violet", "unknown_future_key": 1}),
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.theme == "dark"
    assert settings.accent_color == DEFAULT_DARK_ACCENT


def test_ui_scale_accepts_bounds_and_rejects_out_of_range() -> None:
    assert UI_SCALE_OPTIONS == (0.75, 0.8, 0.85, 0.9, 0.95, 1.0)
    assert AppSettings(ui_scale=0.75).ui_scale == pytest.approx(0.75)
    assert AppSettings(ui_scale=1.0).ui_scale == pytest.approx(1.0)
    assert AppSettings(ui_scale=0.88).ui_scale == pytest.approx(0.9)
    with pytest.raises(SettingsError, match="UI scale"):
        AppSettings(ui_scale=0.5)
    with pytest.raises(SettingsError, match="UI scale"):
        AppSettings(ui_scale=1.1)


def test_accent_colors_are_limited_to_curated_choices() -> None:
    assert len(DARK_ACCENTS) == len(PRESET_ACCENT_COLORS)
    assert DEFAULT_DARK_ACCENT in PRESET_ACCENT_COLORS
    for _key, (_label, color) in DARK_ACCENTS.items():
        assert AppSettings(accent_color=color).accent_color == color.upper()


def test_pink_theme_is_supported() -> None:
    settings = AppSettings(theme="pink")
    assert settings.theme == "pink"
    assert settings.accent_color == DEFAULT_DARK_ACCENT
