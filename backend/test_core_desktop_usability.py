"""Responsive desktop usability checks for the production PySide6 shell."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap


def test_desktop_responsive_visibility_and_icon_usability():
    script = textwrap.dedent(
        r"""
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.main import LinguaFusionWindow

        app = QApplication([])
        window = LinguaFusionWindow()
        window.show()

        def settle(milliseconds=120):
            app.processEvents()
            QTest.qWait(milliseconds)
            app.processEvents()

        def resize(width, height):
            window.resize(width, height)
            window._responsive_mode = None
            window.update_responsive_layout()
            settle()

        def assert_combo_inside(combo):
            parent = combo.parentWidget()
            geometry = combo.geometry()
            assert geometry.x() >= 0
            assert geometry.right() < parent.width(), (
                geometry.getRect(), parent.geometry().getRect()
            )
            assert combo.width() >= 140
            assert combo.height() >= 34

        def assert_translation_workspace(minimum_pane_width):
            assert window.translate_input.isVisible()
            assert window.translate_output.isVisible()
            assert window.translate_source_pane.width() >= minimum_pane_width
            assert window.translate_target_pane.width() >= minimum_pane_width
            assert window.translate_input.height() >= 160
            assert window.translate_output.height() >= 160
            if window.translate_source_pane.geometry().left() < window.translate_target_pane.geometry().left():
                assert window.translate_source_pane.geometry().right() <= window.translate_target_pane.geometry().left()
            assert_combo_inside(window.translate_source)
            assert_combo_inside(window.translate_target)
            assert window.page_scroll.horizontalScrollBar().maximum() == 0

        # Minimum supported window: workspace wins space automatically.
        resize(1180, 720)
        assert window.sidebar_collapsed
        assert window.sidebar.width() == 72
        assert not window.right_panel.isVisible()
        assert_translation_workspace(470)
        assert window.translate_action_host.isVisible()
        assert window.page_scroll.isVisible()

        for name, button in window.nav_buttons.items():
            assert button.text() == ""
            assert button.toolTip() == name
            assert button.accessibleName() == name
            assert not button.icon().isNull()
            assert button.width() >= 44 and button.height() >= 44

        # A user override can reopen navigation even at the compact breakpoint.
        window.sidebar_toggle_btn.click()
        settle()
        assert not window.sidebar_collapsed
        assert window.sidebar.width() == 238
        assert window.nav_buttons["Translate"].text() == "Translate"
        assert window.sidebar_toggle_btn.toolTip() == "Collapse navigation"

        # Standard mode keeps the inspector closed but leaves full nav labels.
        window.sidebar_user_override = None
        window.inspector_user_override = None
        resize(1440, 900)
        assert window.sidebar.width() == 238
        assert not window.right_panel.isVisible()
        assert_translation_workspace(530)

        # The inspector can be explicitly opened at standard size.
        window.inspector_toggle_btn.click()
        settle()
        assert window.right_panel.isVisible()
        assert window.right_panel.width() == 278
        assert window.inspector_toggle_btn.toolTip() == "Hide details panel"
        assert_translation_workspace(390)

        # Expanded mode shows the information rail by default.
        window.sidebar_user_override = None
        window.inspector_user_override = None
        resize(1800, 1050)
        assert window.sidebar.width() == 238
        assert window.right_panel.isVisible()
        assert_translation_workspace(570)

        # Both rails can collapse for a distraction-free canvas.
        window.sidebar_toggle_btn.click()
        window.inspector_toggle_btn.click()
        settle()
        assert window.sidebar.width() == 72
        assert not window.right_panel.isVisible()
        assert_translation_workspace(760)

        icon_controls = [
            *window.nav_buttons.values(),
            *window.translate_action_buttons,
            *window.responsive_playback_buttons,
            window.translate_swap_btn,
            window.sidebar_toggle_btn,
            window.inspector_toggle_btn,
        ]
        icon_buttons = [control for control in icon_controls if hasattr(control, "icon")]
        assert all(not button.icon().isNull() for button in icon_buttons)
        assert window.translate_input.accessibleName() == "Text to translate"
        assert window.translate_output.accessibleName() == "Translated text"
        assert all(button.parentWidget() is window.translate_action_host for button in window.translate_action_buttons)
        assert all(button.window() is window for button in window.translate_action_buttons)

        # Exercise both responsive breakpoints repeatedly. Rearranged controls
        # must never become temporary top-level windows while resizing.
        for resize_width in (1348, 1352, 1278, 1282, 1518, 1522, 1180, 1800):
            resize(resize_width, 900)
            assert all(button.parentWidget() is window.translate_action_host for button in window.translate_action_buttons)
            assert all(button.window() is window for button in window.translate_action_buttons)

        # A dark PC look must retain the same icon and control visibility contract.
        window.set_theme("aurora-glass")
        settle(280)
        assert all(not button.icon().isNull() for button in icon_buttons)
        assert window.translate_input.isVisible() and window.translate_output.isVisible()
        assert window.pages.currentWidget().graphicsEffect() is None
        assert window.page_scroll.viewport().autoFillBackground()
        assert window.pages.autoFillBackground()

        # Page transitions must release their full-page graphics cache before
        # scrolling. A retained opacity effect causes paint trails on Windows.
        for page_name in ("OCR", "Speech", "Translate"):
            window.switch_page(page_name)
            settle(280)
            assert window.pages.currentWidget().graphicsEffect() is None
            window.page_scroll.viewport().repaint()
            assert window.pages.currentWidget().graphicsEffect() is None

        # Look and typography are independent, keyboard-accessible settings.
        window.switch_page("Settings")
        resize(1180, 720)
        settle()
        assert window.theme_combo.count() == 9
        assert window.font_combo.count() == 6
        assert window.motion_combo.count() == 3
        assert set(window.DESKTOP_THEME_IDS) == {
            "broadsheet", "editorial-split", "reading-room", "gallery",
            "editorial-luxe", "glass-dark", "aurora-glass", "blueprint",
            "zen",
        }
        assert "Aurora Glass" in window.theme_status_label.text()

        # Task Center remains usable at the minimum supported window size.
        window.switch_page("Tasks")
        resize(1180, 720)
        settle()
        assert "Tasks" in window.nav_buttons
        assert window.agent_request_text.isVisible()
        assert window.agent_natural_request.isVisible()
        assert window.agent_plan_button.isVisible()
        assert window.agent_confirm_plan_button.isVisible()
        assert not window.agent_confirm_plan_button.isEnabled()
        assert "Nothing has run yet" in window._format_agent_plan({
            "title": "Preview",
            "summary": "Safe plan",
            "can_execute": True,
            "steps": [{"tool": "translate_text"}],
            "model": "test-model",
        })
        assert window.agent_task_output.isVisible()
        assert window.agent_task_selector.isVisible()
        assert window.agent_poll_timer.isActive()
        assert window.page_scroll.horizontalScrollBar().maximum() == 0

        # Rapid wheel ticks must accumulate instead of repeatedly restarting
        # from the scrollbar's partially animated position.
        window.set_motion("full")
        scroll_bar = window.page_scroll.verticalScrollBar()
        scroll_bar.setValue(0)
        assert scroll_bar.maximum() > 0
        wheel_step = min(100, max(1, scroll_bar.maximum() // 5))
        for _ in range(4):
            assert window.page_scroll._queue_scroll(wheel_step)
        accumulated_target = wheel_step * 4
        assert window.page_scroll._scroll_target == accumulated_target
        settle(300)
        assert abs(scroll_bar.value() - accumulated_target) <= 2

        # Reversing direction should react from the visible position, and
        # queued movement must remain inside both scrollbar bounds.
        assert window.page_scroll._queue_scroll(-wheel_step)
        assert window.page_scroll._queue_scroll(-wheel_step)
        reversed_target = wheel_step * 2
        assert window.page_scroll._scroll_target == reversed_target
        settle(300)
        assert abs(scroll_bar.value() - reversed_target) <= 2
        assert window.page_scroll._queue_scroll(scroll_bar.maximum() * 2)
        assert window.page_scroll._scroll_target == scroll_bar.maximum()
        assert window.page_scroll._queue_scroll(-scroll_bar.maximum() * 2)
        assert window.page_scroll._scroll_target == scroll_bar.minimum()

        # A closed dropdown ignores the wheel so the surrounding page scrolls
        # and language/theme choices cannot change by accident.
        class FakeWheelEvent:
            def __init__(self):
                self.ignored = False

            def ignore(self):
                self.ignored = True

        combo_index = window.theme_combo.currentIndex()
        fake_wheel = FakeWheelEvent()
        window.theme_combo.wheelEvent(fake_wheel)
        assert fake_wheel.ignored
        assert window.theme_combo.currentIndex() == combo_index

        window.set_font("editorial")
        settle()
        assert window.current_theme == "aurora-glass"
        assert window.current_font == "editorial"
        assert "Editorial Serif" in window.font_status_label.text()
        assert "Georgia" in window.styleSheet()

        rendered_theme_styles = {}
        for theme_id in window.DESKTOP_THEME_IDS:
            window.set_theme(theme_id)
            settle(25)
            assert window.current_theme == theme_id
            assert window.current_font == "editorial"
            theme_spec = window.DESKTOP_THEME_SPECS[theme_id]
            rendered_theme_styles[theme_id] = window.styleSheet()
            assert theme_spec["bg"] in window.styleSheet()
            assert theme_spec["accent"] in window.styleSheet()
            assert all(not button.icon().isNull() for button in icon_buttons)
        assert len(set(rendered_theme_styles.values())) == len(window.DESKTOP_THEME_IDS)
        assert "#00DCEB" not in rendered_theme_styles["broadsheet"]
        assert "font-family: 'Georgia'" in rendered_theme_styles["broadsheet"]

        for font_id, font_spec in window.DESKTOP_FONT_SPECS.items():
            window.set_font(font_id)
            settle(25)
            assert window.current_font == font_id
            assert window.current_theme == "zen"
            assert font_spec["body"] in window.styleSheet()

        for motion_id in ("full", "reduced", "off"):
            window.set_motion(motion_id)
            assert window.current_motion == motion_id
            assert window.motion_combo.currentData() == motion_id
        assert window.motion_duration(300) == 0

        window.switch_page("Speech")
        settle()
        assert set(window.speech_stage_labels) == {
            "listening", "processing", "translating", "complete"
        }
        window.speech_is_recording = True
        window.set_speech_stage("listening", "Listening")
        assert window.speech_stage_labels["listening"].property("stageState") == "active"
        assert window.speech_record_button.property("recording") is True
        assert window.speech_pause_button.isEnabled()
        assert window.speech_stop_button.isEnabled()
        window.speech_is_recording = False
        window.set_speech_stage("processing", "Processing")
        assert window.speech_stage_labels["listening"].property("stageState") == "complete"
        assert window.speech_stage_labels["processing"].property("stageState") == "active"
        assert not window.speech_record_button.isEnabled()
        window.set_speech_stage("complete", "Complete")
        assert window.speech_record_button.isEnabled()

        window.close()
        window.executor.shutdown(wait=True, cancel_futures=True)
        """
    )
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LF_TEST_MODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, (
        f"Responsive UI checks failed.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
