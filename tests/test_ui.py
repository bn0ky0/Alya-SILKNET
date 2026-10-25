import sys
from pathlib import Path

import pytest
from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QUrl,
)
from PySide6.QtGui import QDropEvent, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QScrollArea

import silknet.ui.graph_view as graph_view
from silknet.config import UI_SCALE_OPTIONS, AppSettings, load_settings
from silknet.ui.assets import ICON_FILE
from silknet.ui.entity_manager import CustomEntityTypeDialog, EntityRecordDialog
from silknet.ui.intro import INTRO_DURATION
from silknet.ui.main_window import SilknetWindow
from silknet.ui.mascot import _MESSAGES
from silknet.ui.pages import AboutPage
from silknet.ui.theme import build_stylesheet, graph_colors, theme_colors
from silknet.ui.widgets import ON_GRAPH_ROLE, SUBTITLE_ROLE, ComboBox, ComboItemDelegate
from silknet.ui.window_effects import apply_taskbar_icon
from silknet.updates import ReleaseInfo


@pytest.fixture(autouse=True)
def _disable_about_update_checks(monkeypatch) -> None:
    monkeypatch.setattr(AboutPage, "auto_check_updates", False)


def _place_on_graph(data_services, *entities):
    """Put cards into the initial graph workspace for UI tests."""
    workspace = data_services.graph_layout.ensure_workspace()
    for index, entity in enumerate(entities):
        data_services.graph_layout.add_entity(
            workspace.id,
            entity.id,
            120.0 + index * 260.0,
            120.0 + index * 40.0,
        )
    return workspace


def test_shell_has_all_workspace_pages_and_persisted_entity_list(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(entity_type="person", name="Stored person")
    window = SilknetWindow(AppSettings(), services=data_services)

    assert window.windowTitle() == "Alya SILKNET"
    assert window.minimumWidth() >= 900
    assert window._toast.label.text() == ""
    assert window._toast.isHidden()
    assert set(window.page_widgets) == {
        "dashboard",
        "graph",
        "entities",
        "evidence",
        "search",
        "settings",
        "about",
    }
    assert window.current_page == "dashboard"

    window.navigation.buttons["entities"].click()
    assert window.current_page == "entities"
    assert window.page_title.text() == "Entities"
    entity_page = window.page_widgets["entities"]
    assert entity_page.entity_list.count() == 1
    assert entity_page.entity_list.currentItem().data(Qt.ItemDataRole.UserRole) == entity.id
    window.close()
    app.quit()


def test_all_workspace_tabs_transition_cleanly(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(60)
    keys = ("graph", "entities", "evidence", "search", "settings", "about", "dashboard")

    for key in keys:
        window.navigation.buttons[key].click()
        host = window._page_hosts[key]
        assert window.current_page == key
        assert window.pages.currentWidget() is host
        assert window.navigation.buttons[key].isChecked()
        assert window._transition_host is host
        assert window._page_fade is not None
        assert host.graphicsEffect() is not None
        QTest.qWait(240)
        assert window._transition_host is None
        assert window._page_fade is None
        assert host.graphicsEffect() is None

    for key in ("graph", "entities", "evidence", "search", "settings", "about", "dashboard"):
        window.navigate_to(key)
    QTest.qWait(260)
    assert window.current_page == "dashboard"
    assert window._page_fade is None
    assert window._transition_host is None
    assert all(host.graphicsEffect() is None for host in window._page_hosts.values())

    window.toggle_sidebar()
    assert window._sidebar_animation.state() == QAbstractAnimation.State.Running
    QTest.qWait(260)
    assert window.navigation.isHidden()
    assert window.navigation.width() == 0
    window.toggle_sidebar()
    assert window._sidebar_animation.state() == QAbstractAnimation.State.Running
    QTest.qWait(260)
    assert window.navigation.isVisible()
    assert window.navigation.width() == 250
    window.toggle_sidebar()
    QTest.qWait(60)
    window.toggle_sidebar()
    QTest.qWait(280)
    assert window.navigation.isVisible()
    assert window.navigation.width() == 250
    assert window.sidebar_toggle._collapsed is False
    window.close()
    app.quit()


def test_workspace_tab_change_slides_with_navigation_direction(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(30)

    window.navigate_to("graph")
    graph_host = window._page_hosts["graph"]
    assert window._page_slide is not None
    assert graph_host.pos().x() > 0
    QTest.qWait(230)
    assert graph_host.pos() == QPoint(0, 0)
    assert graph_host.graphicsEffect() is None

    window.navigate_to("dashboard")
    dashboard_host = window._page_hosts["dashboard"]
    assert window._page_slide is not None
    assert dashboard_host.pos().x() < 0
    QTest.qWait(230)
    assert dashboard_host.pos() == QPoint(0, 0)
    assert dashboard_host.graphicsEffect() is None

    window.close()
    app.quit()


def test_startup_intro_plays_once_and_can_be_skipped(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(30)
    intro = window._intro
    assert intro is not None
    assert not intro.isVisible()

    completed: list[bool] = []
    intro.finished.connect(lambda: completed.append(True))
    window.play_intro()
    assert intro.isVisible()
    assert intro.is_playing
    assert intro._animation.state() == QAbstractAnimation.State.Running
    QTest.qWait(120)
    assert intro._progress > 0.0
    assert not intro.grab().isNull()

    QTest.mouseClick(
        intro,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        intro.rect().center(),
    )
    QTest.qWait(230)
    assert not intro.isVisible()
    assert not intro.is_playing
    assert completed == [True]

    for expected, key in enumerate(
        (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter),
        start=2,
    ):
        intro.play()
        assert intro.is_playing
        QTest.keyClick(intro, key)
        QTest.qWait(230)
        assert not intro.isVisible()
        assert not intro.is_playing
        assert completed == [True] * expected

    window.play_intro()
    assert not intro.isVisible()
    window.close()
    app.quit()


def test_startup_intro_tracks_theme_changes_and_window_resize(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="dark"), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(30)
    intro = window._intro
    assert intro is not None

    window.play_intro()
    QTest.qWait(80)
    intro._animation.pause()
    assert intro._animation.state() == QAbstractAnimation.State.Paused
    for theme in ("light", "pink", "dark-red", "dark-purple", "dark-green", "dark"):
        window._apply_settings(AppSettings(theme=theme))
        assert intro._colors == theme_colors(window.app_settings)
        assert intro.is_playing

    window.resize(1000, 680)
    QTest.qWait(30)
    assert intro.geometry() == window.centralWidget().rect()
    assert intro.is_playing
    assert not intro.grab().isNull()

    window.close()
    app.quit()


def test_startup_intro_hides_the_pink_pet_and_petals(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(60)
    intro = window._intro
    assert intro is not None
    assert not window.mascot.isHidden()
    assert not window._petal_overlay.isHidden()

    window.play_intro()
    QTest.qWait(30)
    assert intro.isVisible()
    assert window.mascot.isHidden()
    assert window._petal_overlay.isHidden()

    intro.dismiss()
    QTest.qWait(230)
    assert not intro.isVisible()
    assert not window.mascot.isHidden()
    assert not window._petal_overlay.isHidden()

    window.close()
    app.quit()


def test_startup_intro_finishes_naturally_and_cleans_up(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="dark"), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(30)
    intro = window._intro
    assert intro is not None
    assert intro._animation.duration() == INTRO_DURATION
    assert INTRO_DURATION > 1400

    completed: list[bool] = []
    intro.finished.connect(lambda: completed.append(True))
    intro._animation.setDuration(160)
    window.play_intro()
    QTest.qWait(350)

    assert completed == [True]
    assert not intro.isVisible()
    assert not intro.is_playing
    assert intro._progress == 0.0
    assert intro._animation.state() == QAbstractAnimation.State.Stopped
    assert intro._fade_effect.opacity() == 1.0

    window.close()
    app.quit()


def test_startup_intro_stops_silently_when_the_window_closes(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="dark"), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(30)
    intro = window._intro
    assert intro is not None

    completed: list[bool] = []
    intro.finished.connect(lambda: completed.append(True))
    window.play_intro()
    QTest.qWait(80)
    window.close()

    assert completed == []
    assert not intro.isVisible()
    assert not intro.is_playing
    assert intro._animation.state() == QAbstractAnimation.State.Stopped
    app.quit()


def test_toast_fits_short_message_without_awkward_wrapping(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    QTest.qWait(320)
    window._show_status_message("Connection restored")
    QTest.qWait(260)

    assert window._toast.label.text() == "Connection restored"
    assert window._toast.isVisible()
    assert window._toast.width() >= 230
    assert window._toast.height() <= 48
    window.close()
    app.quit()


def test_immersive_state_stretches_chrome_to_the_edges(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.show()
    QTest.qWait(40)
    window.isMaximized = lambda: True
    window._sync_window_state()

    assert window.navigation.property("immersive") is True
    assert window._main_area.property("immersive") is True
    assert window.top_bar.property("immersive") is True
    assert window.maximize_button._maximized is True

    window.isMaximized = lambda: False
    window._sync_window_state()
    assert window.navigation.property("immersive") is False
    assert window.top_bar.property("immersive") is False
    window.close()
    app.quit()


def test_theme_selection_updates_ui_and_persists(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)

    window.navigate_to("settings")
    window._settings_page.light_button.click()

    assert window.app_settings.theme == "light"
    assert load_settings(settings_path).theme == "light"
    assert "#F4F3F7" in window.styleSheet()
    window.close()
    app.quit()


def test_dark_color_themes_update_and_persist(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)

    window.navigate_to("settings")
    window._settings_page.theme_buttons["dark-red"].click()
    assert window.app_settings.theme == "dark-red"
    assert "#A45158" in window.styleSheet()
    assert load_settings(settings_path).theme == "dark-red"

    window._settings_page.theme_buttons["dark-purple"].click()
    assert window.app_settings.theme == "dark-purple"
    assert "#805AA7" in window.styleSheet()
    assert load_settings(settings_path).theme == "dark-purple"
    window.close()
    app.quit()


def test_pink_theme_applies_petals_and_mascot(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)
    window.show()
    QTest.qWait(60)

    window.navigate_to("settings")
    window._settings_page.theme_buttons["pink"].click()

    assert window.app_settings.theme == "pink"
    assert "#FFF4F8" in window.styleSheet()
    assert load_settings(settings_path).theme == "pink"
    assert not window.mascot.isHidden()
    assert window.mascot.isWindow()
    assert not window._petal_overlay.isHidden()
    assert window._toast.isHidden()

    window._settings_page.theme_buttons["dark"].click()
    assert window.mascot.isHidden()
    assert window._petal_overlay.isHidden()
    assert window._toast.isHidden()
    window.close()
    app.quit()


def test_pink_pet_drags_and_chats_above_her_head(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.resize(1100, 720)
    window.show()
    QTest.qWait(100)
    pet = window.mascot

    assert pet.isWindow()
    assert pet.windowFlags() & Qt.WindowType.Tool
    assert not pet.isHidden()
    assert pet.bubble.isHidden()
    # The pet is just Alya's face: no plate, medallion or extra window margin.
    assert pet.size() == pet._avatar.size()
    assert pet.width() == 64
    assert len(_MESSAGES) >= 40

    pet.say("Nyaa~!")
    QTest.qWait(40)
    assert pet.bubble.isVisible()
    assert pet.bubble.label.isVisible()
    assert pet.bubble.label.text() == "Nyaa~!"
    assert pet.bubble.y() < pet.y()
    pet_center = pet.x() + pet.width() / 2
    assert abs(pet.bubble.x() + pet.bubble._tail_x - pet_center) <= 2

    long_message = "Nyaa~! Alya is watching your graph, so remember to source everything."
    pet.say(long_message)
    QTest.qWait(40)
    assert pet.bubble.label.text() == long_message
    assert pet.bubble.label.height() > pet.bubble.label.fontMetrics().height()
    assert pet.bubble.y() < pet.y()

    start = pet.pos()
    press = QPoint(pet.width() // 2, pet.height() // 2)
    press_global = pet.mapToGlobal(press)
    QApplication.sendEvent(
        pet,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(press),
            QPointF(press_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_global = press_global - QPoint(70, 45)
    QApplication.sendEvent(
        pet,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(press - QPoint(70, 45)),
            QPointF(move_global),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        pet,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(press - QPoint(70, 45)),
            QPointF(move_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    assert pet.pos() == start - QPoint(70, 45)

    outside = QPoint(window.frameGeometry().right() + 16, window.frameGeometry().top() + 40)
    pet.move(outside)
    assert pet.pos() == outside
    assert not window.frameGeometry().intersects(pet.frameGeometry())

    window.navigate_to("settings")
    window._settings_page.theme_buttons["dark"].click()
    assert pet.isHidden()
    assert pet.bubble.isHidden()
    window.close()
    app.quit()


def test_pet_stops_bobbing_when_the_window_is_hidden(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.show()
    QTest.qWait(80)
    pet = window.mascot
    animation = pet._avatar._animation

    assert pet.isVisible()
    assert animation.state() == QAbstractAnimation.State.Running

    window.hide()
    QTest.qWait(20)
    assert pet.isHidden()
    assert animation.state() == QAbstractAnimation.State.Stopped

    window.show()
    QTest.qWait(60)
    assert pet.isVisible()
    assert animation.state() == QAbstractAnimation.State.Running
    window.close()
    app.quit()


def test_pet_bubble_flips_below_without_losing_its_tail(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.show()
    QTest.qWait(80)
    pet = window.mascot
    screen = QApplication.primaryScreen().availableGeometry()
    pet.move_to(QPoint(screen.center().x(), screen.top() + 4))

    pet.say("Top of the world")
    QTest.qWait(40)

    assert pet.bubble.isVisible()
    assert pet.bubble.y() > pet.y()
    assert pet.bubble._tail_side == "top"
    assert abs(pet.bubble.x() + pet.bubble._tail_x - (pet.x() + pet.width() / 2)) <= 2
    window.close()
    app.quit()


def test_accent_swatch_choice_updates_ui_and_persists(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)

    window.navigate_to("settings")
    page = window._settings_page
    page.accent_buttons["violet"].click()

    assert window.app_settings.accent_color == "#B69CFF"
    assert "#B69CFF" in window.styleSheet()
    assert load_settings(settings_path).accent_color == "#B69CFF"
    assert page.accent_buttons["violet"].isChecked()
    assert not page.accent_buttons["baby-blue"].isChecked()
    assert page.accent_value_label.text() == "Violet"
    window.close()
    app.quit()


def test_accent_choices_are_limited_and_follow_accent_themes(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)

    window.navigate_to("settings")
    page = window._settings_page
    assert set(page.accent_buttons) == {"baby-blue", "violet", "crimson", "mint", "amber"}
    assert page.accent_block.isVisibleTo(page)

    page.theme_buttons["dark-green"].click()
    assert window.app_settings.theme == "dark-green"
    assert not page.accent_block.isVisibleTo(page)

    page.theme_buttons["light"].click()
    assert window.app_settings.theme == "light"
    assert page.accent_block.isVisibleTo(page)
    window.close()
    app.quit()


def test_display_card_has_only_the_ui_scale_slider(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)

    window.navigate_to("settings")
    page = window._settings_page

    assert not hasattr(page, "text_scale_slider")
    assert not hasattr(page, "motion_check")
    slider = page.ui_scale_slider
    assert (slider.minimum(), slider.maximum()) == (0, 5)
    assert slider.value() == 3
    assert page.ui_scale_value.text() == "90%"

    slider.setValue(5)
    page._save_display_settings()

    assert UI_SCALE_OPTIONS == (0.75, 0.8, 0.85, 0.9, 0.95, 1.0)
    assert window.app_settings.ui_scale == pytest.approx(1.0)
    assert load_settings(settings_path).ui_scale == pytest.approx(1.0)
    assert page.ui_scale_value.text() == "100%"
    window.close()
    app.quit()


def test_ui_scale_slider_keeps_gliding_after_mouse_release(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_path)
    window.resize(1100, 760)
    window.show()
    window.navigate_to("settings")
    QTest.qWait(120)
    page = window._settings_page
    slider = page.ui_scale_slider
    slider.setValue(3)
    assert slider._display_fraction == pytest.approx(0.6)

    QTest.mouseClick(
        slider,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(slider.width() - 12, slider.height() // 2),
    )

    assert slider.isSliderDown() is False
    assert slider._animating is True
    QTest.qWait(60)
    assert 0.6 < slider._display_fraction < 1.0
    QTest.qWait(320)
    assert slider.value() == 5
    assert slider._display_fraction == pytest.approx(1.0)
    assert page.ui_scale_value.text() == "100%"
    window.close()
    app.quit()


def test_ui_scale_slider_keeps_its_handle_inside_the_widget(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), tmp_path / "settings.json")
    slider = window._settings_page.ui_scale_slider
    slider.resize(240, 32)

    for value in (slider.minimum(), slider.maximum()):
        slider.setValue(value)
        center = slider._handle_center_x()
        outline_radius = slider._HANDLE_RADIUS + slider._HANDLE_OUTLINE / 2
        assert center - outline_radius >= 0
        assert center + outline_radius <= slider.width()

    span = slider._track_span()
    assert span[0] >= slider._HANDLE_RADIUS + slider._FOCUS_HALO
    assert span[1] <= slider.width() - slider._HANDLE_RADIUS - slider._FOCUS_HALO
    assert slider.height() >= 2 * (slider._HANDLE_RADIUS + slider._FOCUS_HALO)
    window.close()
    app.quit()


ABOUT_DESCRIPTION = (
    "A modern, lightweight, and easy-to-use OSINT investigation tool designed to help "
    "you organize information, connect the dots, and keep your investigations "
    "structured — all through a clean, interactive interface."
)


def test_about_page_shows_the_requested_introduction() -> None:
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    texts = [label.text() for label in page.findChildren(QLabel)]

    assert "OSINT Investigations, Simplified." in texts
    assert ABOUT_DESCRIPTION in texts
    assert "Version 0.1.2" in texts

    card = page.findChild(QFrame, "surfaceCard")
    description = next(
        label for label in page.findChildren(QLabel) if label.text() == ABOUT_DESCRIPTION
    )
    assert card is not None
    assert description.parentWidget() is card
    app.quit()


def test_about_page_checks_for_updates_once_when_shown(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    monkeypatch.setattr(AboutPage, "auto_check_updates", True)
    checks: list[bool] = []
    monkeypatch.setattr(page, "check_for_updates", lambda: checks.append(True))

    page.show()
    QTest.qWait(20)
    assert checks == [True]

    page.hide()
    page.show()
    QTest.qWait(20)
    assert checks == [True]

    page.close()
    app.quit()


def test_about_page_reports_an_available_update() -> None:
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    page._show_update(ReleaseInfo(version="0.2.0", url="https://example.com/release"))

    assert page.update_status.text() == "Version 0.2.0 is available."
    assert not page.release_button.isHidden()
    assert page.release_button.text() == "Get 0.2.0"
    app.quit()


def test_about_page_reports_up_to_date_and_failed_checks() -> None:
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    page._show_update(ReleaseInfo(version="0.1.2", url="https://example.com/release"))
    assert page.update_status.text() == "You're up to date on version 0.1.2."
    assert page.release_button.isHidden()

    page._show_update_error("offline")
    assert page.update_status.text() == "Could not check for updates. Try again later."
    assert page.update_status.toolTip() == "offline"
    assert page.release_button.isHidden()
    app.quit()


def test_graph_filter_hides_unmatched_nodes_and_claims(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha Person")
    second = data_services.entities.create(entity_type="organization", name="Beta Group")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works with",
    )
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]

    page.filter_field.setText("Beta")

    assert not page._nodes[first.id].isVisible()
    assert page._nodes[second.id].isVisible()
    assert not next(iter(page._edges.values())).isVisible()

    page._nodes[second.id].setSelected(True)
    page.filter_field.setText("Alpha")
    assert not page._nodes[second.id].isVisible()
    assert page.scene.selectedItems() == []
    window.close()
    app.quit()


def test_global_search_opens_the_matching_entity(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(entity_type="person", name="Searchable person")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.search_field.setText("Searchable")
    window._open_search()
    search_page = window.page_widgets["search"]

    assert search_page.results_list.count() == 1
    search_page._open_selected(search_page.results_list.item(0))

    assert window.current_page == "entities"
    assert (
        window.page_widgets["entities"].entity_list.currentItem().data(Qt.ItemDataRole.UserRole)
        == entity.id
    )
    window.close()
    app.quit()


def test_entity_dialog_creates_and_edits_persisted_records(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    service = data_services.entities
    dialog = EntityRecordDialog(service)
    dialog.name_field.setText("Dialog-created person")
    dialog.attributes_field.setPlainText('{"birth_year": 1998}')
    dialog._save()

    created = dialog.saved_entity
    assert created is not None
    assert service.get(created.id).attributes == {"birth_year": 1998}

    edit_dialog = EntityRecordDialog(service, created)
    edit_dialog.name_field.setText("Edited person")
    edit_dialog._save()
    reloaded = service.get(created.id)
    assert reloaded.name == "Edited person"
    assert reloaded.id == created.id
    app.quit()


def test_person_role_field_is_optional_and_person_only(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    service = data_services.entities
    dialog = EntityRecordDialog(service)
    assert dialog.role_field.isVisibleTo(dialog)
    dialog.name_field.setText("Role-aware person")
    dialog.role_field.setText("  analyst  ")
    dialog._save()

    created = dialog.saved_entity
    assert created is not None
    assert service.get(created.id).attributes["role"] == "analyst"

    edit_dialog = EntityRecordDialog(service, created)
    assert edit_dialog.role_field.text() == "analyst"
    assert '"role"' not in edit_dialog.attributes_field.toPlainText()
    edit_dialog.type_field.setCurrentIndex(edit_dialog.type_field.findData("organization"))
    edit_dialog._update_type_fields()
    assert edit_dialog.role_field.isHidden()
    edit_dialog.name_field.setText("Now an organization")
    edit_dialog._save()
    assert "role" not in service.get(created.id).attributes

    window = SilknetWindow(AppSettings(), services=data_services)
    window.navigate_to("entities")
    page = window.page_widgets["entities"]
    item = page.entity_list.currentItem()
    assert item.data(SUBTITLE_ROLE) == "Organization"
    window.close()
    app.quit()


def test_person_role_floats_above_the_graph_card(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(
        entity_type="person",
        name="Alya Haddad",
        attributes={"role": "Lead analyst"},
    )
    _place_on_graph(data_services, entity)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(240)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(240)

    node = page._nodes[entity.id]
    badge = node.role_badge_rect()
    assert node.role == "Lead analyst"
    assert badge is not None
    assert badge.bottom() < 0
    assert badge.top() < 0
    assert badge.width() <= node.width - 2 * node.padding
    assert node.boundingRect().top() == pytest.approx(badge.top())
    assert node.boundingRect().height() > node.height
    assert node.sceneBoundingRect().top() < node.scenePos().y()
    window.close()
    app.quit()


def test_image_files_can_be_dropped_on_photo_controls(data_services, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "drop.png"
    image = QImage(QSize(48, 48), QImage.Format.Format_ARGB32)
    image.fill(0xFF6F9DD8)
    assert image.save(str(source))

    service = data_services.entities
    dialog = EntityRecordDialog(service, image_service=data_services.profile_images)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    drop = QDropEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    dialog.profile_image_preview.dropEvent(drop)

    assert dialog._selected_image_source == source
    assert not dialog.profile_image_preview.pixmap().isNull()
    dialog.name_field.setText("Dropped avatar person")
    dialog._save()
    created = dialog.saved_entity
    assert created is not None
    first_stored = Path(created.attributes["profile_image_path"])
    assert first_stored.is_file()

    window = SilknetWindow(AppSettings(), services=data_services)
    window.navigate_to("entities")
    page = window.page_widgets["entities"]
    page.select_entity(created.id)
    assert page.detail_avatar.isVisibleTo(page)
    page.detail_avatar.dropEvent(drop)

    reloaded = service.get(created.id)
    second_stored = Path(reloaded.attributes["profile_image_path"])
    assert second_stored.is_file()
    assert second_stored != first_stored
    assert not first_stored.exists()
    window.close()
    app.quit()


def test_custom_type_dialog_registers_user_defined_fields(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = CustomEntityTypeDialog(data_services.entities)
    dialog.key_field.setText("vehicle")
    dialog.name_field.setText("Vehicle")
    dialog._save()

    assert dialog.saved_type is not None
    assert data_services.entities.list_custom_types()[0].key == "vehicle"
    app.quit()


def test_entity_changes_refresh_the_other_workspace_pages(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    entity = data_services.entities.create(entity_type="person", name="Fresh record")
    _place_on_graph(data_services, entity)
    window.page_widgets["search"].set_query("Fresh")

    window.page_widgets["entities"].records_changed.emit()

    assert entity.id in window.page_widgets["graph"]._nodes
    assert window.page_widgets["search"].results_list.count() == 1
    window.close()
    app.quit()


def test_photos_and_platform_badges_appear_in_lists_and_graph(data_services, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "avatar.png"
    image = QImage(QSize(48, 48), QImage.Format.Format_ARGB32)
    image.fill(0xFFEF7FA6)
    assert image.save(str(source))
    stored = data_services.profile_images.store(source)
    entity = data_services.entities.create(
        entity_type="social_profile",
        name="Instagram friend",
        attributes={
            "platform": "Instagram",
            "profile_url": "https://instagram.com/sample",
            "profile_image_path": str(stored),
        },
    )
    _place_on_graph(data_services, entity)
    window = SilknetWindow(AppSettings(), services=data_services)

    graph_page = window.page_widgets["graph"]
    node = graph_page._nodes[entity.id]
    assert not node.photo.isNull()
    assert node.platform == "Instagram"

    window.navigate_to("entities")
    entity_page = window.page_widgets["entities"]
    item = entity_page.entity_list.currentItem()
    assert item.data(Qt.ItemDataRole.UserRole) == entity.id
    assert not item.icon().isNull()
    assert entity_page.detail_avatar.isVisibleTo(entity_page)
    window.close()
    app.quit()


def test_entity_page_deletes_records_and_refreshes_the_workspace(
    data_services, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Delete me")
    second = data_services.entities.create(entity_type="organization", name="Keep me")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works with",
    )
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["entities"]
    page.select_entity(first.id)
    monkeypatch.setattr(page, "_confirm_delete", lambda _entity: True)

    page.delete_button.click()

    assert first.id not in {entity.id for entity in data_services.entities.list()}
    assert first.id not in page._entities
    assert second.id in page._entities
    assert data_services.relationships.list() == []
    assert first.id not in window.page_widgets["graph"]._nodes
    window.close()
    app.quit()


def test_ui_scale_changes_typography_without_resizing_the_window(
    tmp_path: Path, data_services
) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(entity_type="person", name="Fixed card")
    _place_on_graph(data_services, entity)
    window = SilknetWindow(AppSettings(), tmp_path / "settings.json", data_services)
    window.resize(1180, 760)
    before = window.size()
    node = next(iter(window.page_widgets["graph"]._nodes.values()))
    before_node_width = node.width

    window.navigate_to("settings")
    slider = window._settings_page.ui_scale_slider
    slider.setValue(0)
    window._settings_page._save_display_settings()

    assert window.app_settings.ui_scale == pytest.approx(0.75)
    assert window.size() == before
    assert next(iter(window.page_widgets["graph"]._nodes.values())).width == before_node_width
    window.close()
    app.quit()


def test_graph_colors_cover_every_painter_key() -> None:
    for theme in ("pink", "light", "dark", "dark-purple"):
        colors = graph_colors(AppSettings(theme=theme))
        assert set(colors) >= {
            "accent",
            "accent_text",
            "accent_soft",
            "border",
            "disputed",
            "inferred",
            "muted",
            "selection",
            "surface",
            "surface_alt",
            "text",
            "verified",
        }


def test_graph_page_renders_edges_and_new_entities(data_services, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="organization", name="Beta")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="works with",
    )
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(theme="pink"), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)

    image = window.grab().toImage()
    assert not image.isNull()
    assert len(page._edges) == 1
    assert all(item.isVisible() for item in page._nodes.values())

    created = data_services.entities.create(entity_type="person", name="From graph")

    class FakeDialog:
        def __init__(self, *_args, **_kwargs):
            self.saved_entity = created

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(graph_view, "EntityRecordDialog", FakeDialog)
    page._add_entity()
    assert created.id in page._nodes
    window.close()
    app.quit()


def test_graph_edge_arrow_stops_visibly_before_the_target(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Arrow source")
    second = data_services.entities.create(entity_type="organization", name="Arrow target")
    data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="advises",
    )
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)

    edge = next(iter(page._edges.values()))
    arrow = edge.arrow_polygon()
    assert len(arrow) == 3
    tip = arrow[0]
    target_rect = edge.target_node.sceneBoundingRect()
    assert not target_rect.contains(tip)
    assert target_rect.adjusted(-8, -8, 8, 8).contains(tip)
    base_center = QPointF(
        (arrow[1].x() + arrow[2].x()) / 2,
        (arrow[1].y() + arrow[2].y()) / 2,
    )
    length = ((tip.x() - base_center.x()) ** 2 + (tip.y() - base_center.y()) ** 2) ** 0.5
    assert length == pytest.approx(10.0, abs=0.5)
    width = ((arrow[1].x() - arrow[2].x()) ** 2 + (arrow[1].y() - arrow[2].y()) ** 2) ** 0.5
    assert width == pytest.approx(8.8, abs=0.5)
    assert graph_view.ARROW_LENGTH < 12.0
    assert graph_view.ARROW_HALF_WIDTH < 5.0
    window.close()
    app.quit()


def test_graph_port_drag_requests_a_relationship(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)
    canvas = page.canvas
    captured: list[tuple[str, str]] = []
    canvas.connection_requested.disconnect()
    canvas.connection_requested.connect(lambda source, target: captured.append((source, target)))

    source = page._nodes[first.id]
    target = page._nodes[second.id]
    source_point = canvas.mapFromScene(source.pos() + source.connection_port_rect().center())
    target_point = canvas.mapFromScene(target.pos() + QPointF(target.width / 2, target.height / 2))
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        source_point,
    )
    QTest.mouseMove(canvas.viewport(), target_point, 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        target_point,
    )

    assert captured == [(first.id, second.id)]
    assert canvas._link_source is None
    assert canvas._link_preview is None
    window.close()
    app.quit()


def test_graph_custom_board_palette_drop_and_remove(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    overview = data_services.graph_layout.ensure_workspace()
    board = data_services.graph_layout.create_board("Curated")
    data_services.graph_layout.add_entity(overview.id, second.id, 40.0, 60.0)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    page._current_board_id = board.id
    page._refresh_boards()
    page.refresh_graph()
    assert page.palette_list.count() == 2
    assert page._nodes == {}

    mime = QMimeData()
    mime.setData(graph_view.ENTITY_MIME_TYPE, first.id.encode("utf-8"))
    drop = QDropEvent(
        QPointF(180, 160),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    page.canvas.dropEvent(drop)

    assert first.id in page._nodes
    assert data_services.graph_layout.board_entity_ids(board.id) == {first.id}
    page._nodes[first.id].setSelected(True)
    page._show_selection()
    assert not page.remove_node_button.isHidden()
    page._remove_selected_node()
    assert first.id not in page._nodes
    assert data_services.graph_layout.board_entity_ids(board.id) == set()

    overview_index = page.board_selector.findData(overview.id)
    page.board_selector.setCurrentIndex(overview_index)
    assert set(page._nodes) == {second.id}
    window.close()
    app.quit()


def test_graph_palette_double_click_places_entity(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    data_services.entities.create(entity_type="person", name="Beta")
    board = data_services.graph_layout.create_board("Curated")
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    page._current_board_id = board.id
    page._refresh_boards()
    page.refresh_graph()
    item = next(
        page.palette_list.item(index)
        for index in range(page.palette_list.count())
        if page.palette_list.item(index).data(Qt.ItemDataRole.UserRole) == first.id
    )

    page.palette_list.itemDoubleClicked.emit(item)

    assert first.id in page._nodes
    assert data_services.graph_layout.board_entity_ids(board.id) == {first.id}

    # Double-clicking a card that is already on the board must also reveal it
    # when the name or type filter currently hides it.
    page.filter_field.setText("Beta")
    page.type_filter.setCurrentIndex(page.type_filter.findData("person"))
    assert page.filter_field.text() == "Beta"
    item = next(
        page.palette_list.item(index)
        for index in range(page.palette_list.count())
        if page.palette_list.item(index).data(Qt.ItemDataRole.UserRole) == first.id
    )
    page.palette_list.itemDoubleClicked.emit(item)
    assert page.filter_field.text() == ""
    assert page.type_filter.currentIndex() == 0
    assert page._nodes[first.id].isSelected()
    window.close()
    app.quit()


def test_graph_empty_hint_disappears_when_a_card_is_added(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    hint = page.canvas._empty_hint

    assert hint.isVisible()
    assert "empty" in hint.text().lower()
    viewport = page.canvas.viewport()
    assert abs(hint.x() - (viewport.width() - hint.width()) // 2) <= 1
    assert abs(hint.y() - (viewport.height() - hint.height()) // 2) <= 1

    entity = data_services.entities.create(entity_type="person", name="First")
    page._add_entity_to_graph(entity.id, QPointF(120, 120), announce=False)

    assert not hint.isVisible()
    assert len(page._nodes) == 1
    window.close()
    app.quit()


def test_graph_palette_lists_every_entity_and_edge_labels_are_clickable(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entities = [
        data_services.entities.create(entity_type="person", name=f"Person {index}")
        for index in range(4)
    ]
    data_services.relationships.create(
        source_entity_id=entities[0].id,
        target_entity_id=entities[1].id,
        relationship_type="knows",
    )
    _place_on_graph(data_services, entities[0], entities[1])
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1280, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)

    assert page.palette_list.count() == 4
    assert page.palette_list.verticalScrollBar().maximum() == 0
    assert not page.details.isVisible()

    edge = next(iter(page._edges.values()))
    midpoint = edge.path().pointAtPercent(0.5)
    label_point = page.canvas.mapFromScene(midpoint + QPointF(0, -20))
    QTest.mouseClick(
        page.canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        label_point,
    )
    QTest.qWait(30)

    assert page.scene.selectedItems() == [edge]
    assert page.details.isVisible()
    assert page.detail_kind.text() == "Relationship claim"
    window.close()
    app.quit()


def test_graph_page_fits_minimum_window_without_page_scrolling(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    for index in range(4):
        data_services.entities.create(entity_type="person", name=f"Person {index}")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(960, 650)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    scroll_area = page.parentWidget()
    while scroll_area is not None and not isinstance(scroll_area, QScrollArea):
        scroll_area = scroll_area.parentWidget()

    assert scroll_area is not None
    assert scroll_area.verticalScrollBar().maximum() == 0
    assert page.canvas.viewport().height() >= 240
    window.close()
    app.quit()


def test_single_entity_fit_graph_keeps_cards_at_natural_size(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(entity_type="person", name="Only")
    _place_on_graph(data_services, entity)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1280, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    page.fit_graph()

    assert page.canvas.transform().m11() <= 1.001
    window.close()
    app.quit()


def test_graph_shift_and_connect_mode_link_gestures(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    canvas = page.canvas
    captured: list[tuple[str, str]] = []
    canvas.connection_requested.disconnect()
    canvas.connection_requested.connect(lambda source, target: captured.append((source, target)))
    source = page._nodes[first.id]
    target = page._nodes[second.id]
    source_point = canvas.mapFromScene(source.pos() + QPointF(source.width / 2, source.height / 2))
    target_point = canvas.mapFromScene(target.pos() + QPointF(target.width / 2, target.height / 2))

    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        source_point,
    )
    QTest.mouseMove(canvas.viewport(), target_point, 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        target_point,
    )
    assert captured == [(first.id, second.id)]

    canvas.set_connection_mode(True)
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        source_point,
    )
    QTest.mouseMove(canvas.viewport(), target_point, 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        target_point,
    )
    assert captured == [(first.id, second.id), (first.id, second.id)]
    assert canvas._link_source is None
    window.close()
    app.quit()


def test_graph_middle_drag_links_entities(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)
    canvas = page.canvas
    captured: list[tuple[str, str]] = []
    canvas.connection_requested.disconnect()
    canvas.connection_requested.connect(lambda source, target: captured.append((source, target)))

    source = page._nodes[first.id]
    target = page._nodes[second.id]
    source_point = canvas.mapFromScene(source.pos() + QPointF(source.width / 2, source.height / 2))
    target_point = canvas.mapFromScene(target.pos() + QPointF(target.width / 2, target.height / 2))

    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        source_point,
    )
    assert canvas._link_source is source
    assert canvas._pan_origin is None
    QTest.mouseMove(canvas.viewport(), target_point, 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        target_point,
    )

    assert captured == [(first.id, second.id)]
    assert canvas._link_source is None
    window.close()
    app.quit()


def test_graph_uses_an_infinite_scene_and_fit_keeps_it(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    data_services.entities.create(entity_type="person", name="Alpha")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    canvas = page.canvas
    expected = graph_view.INFINITE_SCENE_RECT

    assert page.scene.sceneRect() == expected
    assert canvas.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert canvas.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    page.fit_graph()
    QTest.qWait(30)
    assert page.scene.sceneRect() == expected

    canvas.centerOn(8_000, 9_000)
    assert page.scene.sceneRect() == expected
    center = canvas.mapToScene(canvas.viewport().rect().center())
    assert center.x() == pytest.approx(8_000, abs=2.0)
    assert center.y() == pytest.approx(9_000, abs=2.0)
    window.close()
    app.quit()


def test_graph_drag_out_removes_card_from_a_custom_board(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    data_services.entities.create(entity_type="person", name="Beta")
    board = data_services.graph_layout.create_board("Curated")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    page._current_board_id = board.id
    page._refresh_boards()
    page.refresh_graph()
    page._add_entity_to_graph(first.id, QPointF(120, 120), announce=False)
    QTest.qWait(30)
    canvas = page.canvas
    node = page._nodes[first.id]
    start = canvas.mapFromScene(node.sceneBoundingRect().center())
    outside = QPoint(canvas.viewport().width() + 30, canvas.viewport().height() + 30)

    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    assert canvas._drag_node is node
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(outside),
        QPointF(canvas.viewport().mapToGlobal(outside)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas.viewport(), move)
    assert canvas._drag_out
    assert canvas._remove_hint.isVisible()

    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        outside,
    )

    assert first.id not in page._nodes
    assert data_services.graph_layout.board_entity_ids(board.id) == set()
    window.close()
    app.quit()


def test_graph_drag_out_detects_release_outside_without_a_move_event(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    entity = data_services.entities.create(entity_type="person", name="Alpha")
    board = data_services.graph_layout.create_board("Curated")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    page._current_board_id = board.id
    page._refresh_boards()
    page.refresh_graph()
    page._add_entity_to_graph(entity.id, QPointF(120, 120), announce=False)
    QTest.qWait(30)
    canvas = page.canvas
    node = page._nodes[entity.id]
    start = canvas.mapFromScene(node.sceneBoundingRect().center())
    outside = QPoint(canvas.viewport().width() + 30, canvas.viewport().height() + 30)

    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        outside,
    )

    assert entity.id not in page._nodes
    assert data_services.graph_layout.board_entity_ids(board.id) == set()
    window.close()
    app.quit()


def test_graph_drag_out_removes_and_restores_on_a_regular_workspace(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    workspace = _place_on_graph(data_services, first)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    page.fit_graph()
    QTest.qWait(30)
    canvas = page.canvas
    messages: list[str] = []
    page.message.connect(messages.append)
    node = page._nodes[first.id]
    original_position = node.pos()
    start = canvas.mapFromScene(node.sceneBoundingRect().center())
    outside = QPoint(canvas.viewport().width() + 30, canvas.viewport().height() + 30)

    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(outside),
        QPointF(canvas.viewport().mapToGlobal(outside)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas.viewport(), move)
    assert "remove" in canvas._remove_hint.text().lower()

    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        outside,
    )

    assert first.id not in page._nodes
    assert first.id not in data_services.graph_layout.board_entity_ids(workspace.id)
    assert first.id not in data_services.graph_layout.positions(workspace.id)
    assert any("removed from this graph" in message.lower() for message in messages)
    palette_item = next(
        page.palette_list.item(row)
        for row in range(page.palette_list.count())
        if page.palette_list.item(row).data(Qt.ItemDataRole.UserRole) == first.id
    )
    assert not palette_item.data(ON_GRAPH_ROLE)

    page._add_entity_to_graph(first.id, original_position)
    assert first.id in page._nodes
    assert first.id in data_services.graph_layout.board_entity_ids(workspace.id)
    restored = page._nodes[first.id]
    QTest.qWait(260)
    assert restored.opacity() == pytest.approx(1.0)
    assert restored.pos().x() == pytest.approx(original_position.x())
    assert restored.pos().y() == pytest.approx(original_position.y())
    window.close()
    app.quit()


def test_graph_returning_card_can_restore_or_keep_connections_hidden(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    claim = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    workspace = _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(150)
    page = window.page_widgets["graph"]
    assert claim.id in page._edges

    page._remove_entity_from_graph(first.id)
    QTest.qWait(30)
    assert first.id not in page._nodes
    assert data_services.graph_layout.hidden_relationship_ids(workspace.id) == {claim.id}

    prompts: list[int] = []

    def card_only(_name: str, count: int) -> str:
        prompts.append(count)
        return graph_view.RestoreCardDialog.CARD_ONLY

    page._ask_restore_choice = card_only
    page._add_entity_to_graph(first.id, announce=False)
    QTest.qWait(30)
    assert first.id in page._nodes
    assert claim.id not in page._edges
    assert data_services.graph_layout.hidden_relationship_ids(workspace.id) == {claim.id}
    assert prompts == [1]

    page._remove_entity_from_graph(first.id)
    QTest.qWait(30)
    page._ask_restore_choice = lambda _name, _count: graph_view.RestoreCardDialog.WITH_CONNECTIONS
    page._add_entity_to_graph(first.id, announce=False)
    QTest.qWait(30)
    assert first.id in page._nodes
    assert claim.id in page._edges
    assert data_services.graph_layout.hidden_relationship_ids(workspace.id) == set()
    window.close()
    app.quit()


def test_closed_combo_box_ignores_mouse_wheel(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    combo = ComboBox()
    combo.addItems(["One", "Two", "Three"])
    combo.setCurrentIndex(0)
    combo.show()
    QTest.qWait(20)
    wheel = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )

    QApplication.sendEvent(combo, wheel)
    assert combo.currentIndex() == 0
    combo.setFocus()
    QApplication.sendEvent(combo, wheel)
    assert combo.currentIndex() == 0
    combo.close()
    app.quit()


def test_combo_popup_is_owned_themed_and_handles_mouse_and_keys(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(theme="pink", ui_scale=0.9)
    app.setStyleSheet(build_stylesheet(settings))
    combo = ComboBox()
    combo.addItems(["Person", "Organization", "Website or domain"])
    combo.resize(220, 36)
    combo.show()
    QTest.qWait(20)
    assert combo.view().objectName() == "comboPopupFallback"
    assert isinstance(combo.view().itemDelegate(), ComboItemDelegate)
    combo.showPopup()
    QTest.qWait(40)
    popup = combo.popup
    colors = theme_colors(settings)

    assert popup is not None
    assert popup.isVisible()
    assert popup.isWindow()
    assert popup.windowFlags() & Qt.WindowType.Popup
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert isinstance(popup.view.itemDelegate(), ComboItemDelegate)
    assert "QFrame#comboPopupPanel" in popup.styleSheet()
    assert colors["surface_alt"] in popup.styleSheet()
    assert "border-radius: 12px" in popup.styleSheet()
    assert popup.view.itemDelegate()._colors["selection"] == colors["selection"]
    assert popup.view.model() is combo.model()
    assert popup.width() >= combo.width()
    assert not popup.view.verticalScrollBar().isVisible()

    QTest.keyClick(popup.view, Qt.Key.Key_Down)
    QTest.keyClick(popup.view, Qt.Key.Key_Return)
    QTest.qWait(20)
    assert combo.currentIndex() == 1
    assert not popup.isVisible()

    combo.showPopup()
    QTest.qWait(20)
    index = combo.model().index(2, 0)
    QTest.mouseClick(
        popup.view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        popup.view.visualRect(index).center(),
    )
    QTest.qWait(20)
    assert combo.currentIndex() == 2
    assert not popup.isVisible()

    combo.setFocus()
    QTest.keyClick(combo, Qt.Key.Key_F4)
    QTest.qWait(20)
    assert popup.isVisible()
    QTest.mouseClick(
        combo,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        combo.rect().center(),
    )
    QTest.qWait(20)
    assert not popup.isVisible()
    combo.close()
    app.quit()


def test_combo_popup_shrinks_and_clears_stale_scroll(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(theme="light", ui_scale=0.9)
    app.setStyleSheet(build_stylesheet(settings))
    combo = ComboBox()
    combo.addItems([f"Board {index}" for index in range(15)])
    combo.resize(200, 36)
    combo.show()
    QTest.qWait(20)

    combo.showPopup()
    QTest.qWait(60)
    popup = combo.popup
    assert popup is not None
    tall_height = popup.height()
    assert popup.view.verticalScrollBar().maximum() > 0
    popup.hide()
    QTest.qWait(20)

    combo.clear()
    combo.addItems(["Overview", "S"])
    combo.setCurrentIndex(1)
    combo.showPopup()
    QTest.qWait(60)
    assert popup.height() < tall_height
    assert popup.view.verticalScrollBar().maximum() == 0
    assert popup.view.verticalScrollBar().value() == 0
    assert not popup.view.verticalScrollBar().isVisible()
    row_height = popup.view.sizeHintForRow(0)
    assert popup.view.viewport().height() >= row_height * 2
    assert popup.height() - popup.view.height() <= popup._shadow * 2 + 4
    first_row = popup.view.visualRect(combo.model().index(0, 0))
    second_row = popup.view.visualRect(combo.model().index(1, 0))
    viewport_rect = popup.view.viewport().rect()
    assert first_row.top() >= viewport_rect.top()
    assert second_row.bottom() <= viewport_rect.bottom()
    popup.hide()
    QTest.qWait(20)

    combo.clear()
    combo.addItem("S")
    combo.showPopup()
    QTest.qWait(60)
    assert popup.view.verticalScrollBar().maximum() == 0
    assert popup.view.verticalScrollBar().value() == 0
    assert popup.height() < tall_height
    assert popup.view.viewport().height() >= row_height
    combo.close()
    app.quit()


def test_window_uses_the_bundled_taskbar_icon(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    assert ICON_FILE.exists()
    window = SilknetWindow(AppSettings(), services=data_services)
    window.show()
    QTest.qWait(50)

    assert not window.windowIcon().isNull()
    if sys.platform == "win32":
        assert apply_taskbar_icon(window, ICON_FILE)
    window.close()
    app.quit()


def test_social_status_combo_uses_plain_values(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = EntityRecordDialog(data_services.entities)
    assert dialog.profile_status_field.currentData() == "unverified"
    dialog.type_field.setCurrentIndex(dialog.type_field.findData("social_profile"))
    dialog.name_field.setText("Status profile")
    dialog.platform_field.setCurrentIndex(dialog.platform_field.findData("Instagram"))
    dialog.profile_url_field.setText("https://instagram.com/status.profile")
    status_index = dialog.profile_status_field.findData("user_reported")
    assert status_index >= 0
    dialog.profile_status_field.setCurrentIndex(status_index)
    dialog._save()

    created = dialog.saved_entity
    assert created is not None
    assert created.attributes["verification_status"] == "user_reported"

    edit_dialog = EntityRecordDialog(data_services.entities, created)
    assert edit_dialog.profile_status_field.currentData() == "user_reported"
    app.quit()


def test_graph_wheel_zoom_and_middle_or_right_drag_panning(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    for index in range(4):
        data_services.entities.create(entity_type="person", name=f"Person {index}")
    window = SilknetWindow(AppSettings(), services=data_services)
    window.resize(1200, 780)
    window.show()
    window.navigate_to("graph")
    QTest.qWait(250)
    page = window.page_widgets["graph"]
    canvas = page.canvas
    page.fit_graph()
    before = canvas.transform().m11()

    wheel_in = QWheelEvent(
        QPointF(300, 200),
        QPointF(300, 200),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas.viewport(), wheel_in)
    assert canvas.transform().m11() > before
    for _ in range(40):
        QApplication.sendEvent(
            canvas.viewport(),
            QWheelEvent(
                QPointF(300, 200),
                QPointF(300, 200),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            ),
        )
    assert canvas.transform().m11() == pytest.approx(3.0)

    horizontal = canvas.horizontalScrollBar()
    vertical = canvas.verticalScrollBar()
    horizontal.setValue(horizontal.maximum() // 2)
    vertical.setValue(vertical.maximum() // 2)
    start = (horizontal.value(), vertical.value())
    center = canvas.viewport().rect().center()
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        center,
    )
    QTest.mouseMove(canvas.viewport(), center + QPoint(60, 30), 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        center + QPoint(60, 30),
    )
    assert (horizontal.value(), vertical.value()) != start

    start = (horizontal.value(), vertical.value())
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        center,
    )
    QTest.mouseMove(canvas.viewport(), center - QPoint(60, 30), 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        center - QPoint(60, 30),
    )
    assert (horizontal.value(), vertical.value()) != start
    assert canvas._pan_origin is None
    window.close()
    app.quit()


def test_search_opens_relationship_and_restores_its_endpoints(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    relationship = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    board = data_services.graph_layout.create_board("Curated")
    data_services.graph_layout.add_entity(board.id, first.id, 20.0, 30.0)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    page._current_board_id = board.id
    page._refresh_boards()
    page.refresh_graph()

    assert relationship.id not in page._edges
    window._open_search_result("graph", relationship.id)

    assert window.current_page == "graph"
    assert page._current_board_id == board.id
    assert second.id in page._nodes
    assert relationship.id in page._edges
    assert page._edges[relationship.id].isSelected()
    window.close()
    app.quit()


def test_relationship_dialog_saves_dates_and_details_show_them(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="organization", name="Beta")
    dialog = graph_view.RelationshipRecordDialog(
        data_services, source_id=first.id, target_id=second.id
    )
    dialog.type_field.setText("worked at")
    dialog.start_date_field.setText("2019-04-02")
    dialog.end_date_field.setText("2021-08-14")
    dialog.confidence_field.setText(
        "Confirmed by both public posts and an interview note that needs checking."
    )
    dialog._save()

    created = dialog.saved_relationship
    assert created is not None
    assert created.start_date == "2019-04-02"
    assert created.end_date == "2021-08-14"

    edit_dialog = graph_view.RelationshipRecordDialog(data_services, created)
    assert edit_dialog.start_date_field.text() == "2019-04-02"
    assert edit_dialog.end_date_field.text() == "2021-08-14"
    assert edit_dialog.confidence_field.cursorPosition() == 0
    assert edit_dialog.confidence_field.selectedText() == ""
    edit_dialog.end_date_field.setText("2022-01-09")
    edit_dialog._save()
    assert edit_dialog.saved_relationship is not None
    assert data_services.relationships.get(created.id).end_date == "2022-01-09"

    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    page._edges[created.id].setSelected(True)
    page._show_selection()
    detail = page.detail_copy.text()
    assert "2019-04-02" in detail
    assert "2022-01-09" in detail
    assert page.delete_claim_button.isVisibleTo(page)
    window.close()
    app.quit()


def test_graph_delete_claim_keeps_entities_and_sources(data_services, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    source = data_services.sources.create(title="Case file", source_type="note")
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    relationship = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
        source_ids=[source.id],
    )
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    messages: list[str] = []
    page.message.connect(messages.append)
    monkeypatch.setattr(page, "_confirm_delete_relationship", lambda claim: True)
    page._edges[relationship.id].setSelected(True)

    page._delete_selected_relationship()

    assert relationship.id not in page._edges
    with pytest.raises(LookupError):
        data_services.relationships.get(relationship.id)
    assert data_services.entities.get(first.id).name == "Alpha"
    assert data_services.entities.get(second.id).name == "Beta"
    assert data_services.sources.get(source.id).title == "Case file"
    assert any("deleted" in message.lower() for message in messages)
    window.close()
    app.quit()


def test_relationship_dialog_delete_keeps_records(data_services, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    relationship = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    dialog = graph_view.RelationshipRecordDialog(data_services, relationship)
    assert dialog.delete_button is not None
    monkeypatch.setattr(dialog, "_confirm_delete", lambda: True)

    dialog.delete_button.click()

    assert dialog.deleted
    with pytest.raises(LookupError):
        data_services.relationships.get(relationship.id)
    assert data_services.entities.get(first.id).name == "Alpha"
    assert data_services.entities.get(second.id).name == "Beta"
    app.quit()


def test_delete_key_removes_selected_claim(data_services, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    first = data_services.entities.create(entity_type="person", name="Alpha")
    second = data_services.entities.create(entity_type="person", name="Beta")
    relationship = data_services.relationships.create(
        source_entity_id=first.id,
        target_entity_id=second.id,
        relationship_type="knows",
    )
    _place_on_graph(data_services, first, second)
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["graph"]
    monkeypatch.setattr(page, "_confirm_delete_relationship", lambda claim: True)
    page._edges[relationship.id].setSelected(True)

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    page.canvas.keyPressEvent(event)

    assert relationship.id not in page._edges
    with pytest.raises(LookupError):
        data_services.relationships.get(relationship.id)
    window.close()
    app.quit()


def test_settings_page_uses_one_scroll_area(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    page = window.page_widgets["settings"]
    ancestors: list[QScrollArea] = []
    parent = page.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            ancestors.append(parent)
        parent = parent.parentWidget()

    assert len(ancestors) == 1
    window.close()
    app.quit()


def test_closing_flushes_a_pending_scale_change(data_services, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_file = tmp_path / "settings.json"
    window = SilknetWindow(AppSettings(), settings_file=settings_file, services=data_services)
    page = window.page_widgets["settings"]
    page.ui_scale_slider.setValue(UI_SCALE_OPTIONS.index(0.8))

    assert page._settings_timer.isActive()
    window.close()

    assert load_settings(settings_file).ui_scale == pytest.approx(0.8)
    app.quit()


def test_workspace_refresh_updates_search_with_new_custom_types(data_services) -> None:
    app = QApplication.instance() or QApplication([])
    window = SilknetWindow(AppSettings(), services=data_services)
    search_page = window.page_widgets["search"]
    assert search_page.entity_type_filter.findData("vehicle") == -1

    data_services.entities.create_custom_type(key="vehicle", display_name="Vehicle")
    window._refresh_workspace()

    assert search_page.entity_type_filter.findData("vehicle") >= 0
    window.close()
    app.quit()
