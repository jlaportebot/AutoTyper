"""Tests for the macOS Quartz backend.

Quartz is replaced by a recording fake, so none of this needs macOS or pyobjc.
"""

import sys
import types
import unittest
from unittest import mock

from autotyper import mac_input
from autotyper.errors import InputBackendError
from autotyper.keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON
from autotyper.mac_input import (
    AccessibilityPermissionError,
    MacInput,
    accessibility_trusted,
    utf16_length,
)

KEYCODE_RETURN = 36
KEYCODE_TAB = 48
KEYCODE_ESCAPE = 53
KEYCODE_F9 = 101
FRONT_WINDOW = 42
BACK_WINDOW = 43
MENU_BAR_WINDOW = 7
FRONT_PID = 501
BACK_PID = 502


def window(number, layer=0, name=None, owner="App", pid=1, bounds=(0, 0, 100, 100)):
    """One entry of a CGWindowListCopyWindowInfo result."""
    left, top, width, height = bounds
    entry = {
        "kCGWindowNumber": number,
        "kCGWindowLayer": layer,
        "kCGWindowOwnerName": owner,
        "kCGWindowOwnerPID": pid,
        "kCGWindowBounds": {"X": left, "Y": top, "Width": width, "Height": height},
    }
    if name is not None:
        entry["kCGWindowName"] = name
    return entry


def front_to_back_windows():
    """Menu bar, a text editor in front of a browser."""
    return [
        window(MENU_BAR_WINDOW, layer=25, owner="Window Server", bounds=(0, 0, 1440, 24)),
        window(
            FRONT_WINDOW,
            name="notes.txt",
            owner="TextEdit",
            pid=FRONT_PID,
            bounds=(100, 100, 400, 300),
        ),
        window(BACK_WINDOW, owner="Safari", pid=BACK_PID, bounds=(300, 200, 600, 500)),
    ]


class FakeQuartz:
    """Records Quartz calls and answers from fixtures."""

    kCGHIDEventTap = "hid-tap"
    kCGEventSourceStateHIDSystemState = "hid-state"
    kCGMouseButtonLeft = 0
    kCGEventMouseMoved = "mouse-moved"
    kCGEventLeftMouseDown = "left-down"
    kCGEventLeftMouseUp = "left-up"
    kCGWindowListOptionOnScreenOnly = 1
    kCGWindowListExcludeDesktopElements = 16
    kCGNullWindowID = 0

    def __init__(
        self, trusted=True, windows=None, held_keys=(), left_held=False, pointer=(120.0, 240.0)
    ):
        self.trusted = trusted
        self.windows = front_to_back_windows() if windows is None else windows
        self.held_keys = set(held_keys)
        self.left_held = left_held
        self.pointer = pointer
        self.posted = []
        self.prompts = []
        self.window_list_requests = []
        self.fail_event_creation = False

    def CGPoint(self, x, y):
        return types.SimpleNamespace(x=x, y=y)

    def AXIsProcessTrusted(self):
        return self.trusted

    def AXIsProcessTrustedWithOptions(self, options):
        self.prompts.append(options)
        return self.trusted

    def CGEventCreateKeyboardEvent(self, source, keycode, key_down):
        if self.fail_event_creation:
            return None
        return {
            "kind": "key",
            "source": source,
            "keycode": keycode,
            "down": key_down,
            "unicode": None,
        }

    def CGEventKeyboardSetUnicodeString(self, event, length, text):
        event["unicode"] = (length, text)

    def CGEventCreateMouseEvent(self, source, mouse_type, point, button):
        if self.fail_event_creation:
            return None
        return {
            "kind": "mouse",
            "source": source,
            "type": mouse_type,
            "point": (point.x, point.y),
            "button": button,
        }

    def CGEventPost(self, tap, event):
        self.posted.append((tap, event))

    def CGEventSourceKeyState(self, state, keycode):
        assert state == self.kCGEventSourceStateHIDSystemState
        return keycode in self.held_keys

    def CGEventSourceButtonState(self, state, button):
        assert state == self.kCGEventSourceStateHIDSystemState
        return self.left_held and button == self.kCGMouseButtonLeft

    def CGWindowListCopyWindowInfo(self, option, relative_to):
        self.window_list_requests.append((option, relative_to))
        return self.windows

    def CGEventCreate(self, source):
        return {"kind": "probe", "source": source}

    def CGEventGetLocation(self, _event):
        return self.CGPoint(*self.pointer)

    def posted_events(self):
        return [event for _tap, event in self.posted]


class QuartzWithoutAccessibility(FakeQuartz):
    """Quartz as pyobjc ships it: the Accessibility functions are not in it."""

    def __getattribute__(self, name):
        if name.startswith("AX"):
            raise AttributeError(f"module 'Quartz' has no attribute {name!r}")
        return super().__getattribute__(name)


class FakeApplicationServices:
    """Stands in for ApplicationServices, which re-exports the HIServices functions."""

    def __init__(self, trusted=True):
        self.trusted = trusted
        self.prompts = []

    def AXIsProcessTrusted(self):
        return self.trusted

    def AXIsProcessTrustedWithOptions(self, options):
        self.prompts.append(options)
        return self.trusted


class FakeAppKit:
    """Stands in for AppKit; records which processes get activated."""

    NSApplicationActivateIgnoringOtherApps = 2

    def __init__(self, running_pids=(FRONT_PID, BACK_PID)):
        self.activations = []
        appkit = self

        class Application:
            def __init__(self, pid):
                self.pid = pid

            def activateWithOptions_(self, options):
                appkit.activations.append((self.pid, options))

        self.running = {pid: Application(pid) for pid in running_pids}
        self.NSRunningApplication = types.SimpleNamespace(
            runningApplicationWithProcessIdentifier_=self.running.get
        )


class Utf16Length(unittest.TestCase):
    def test_ascii_character_is_one_unit(self):
        self.assertEqual(utf16_length("a"), 1)

    def test_accented_character_is_one_unit(self):
        self.assertEqual(utf16_length("é"), 1)

    def test_cjk_character_is_one_unit(self):
        self.assertEqual(utf16_length("中"), 1)

    def test_emoji_is_a_surrogate_pair(self):
        self.assertEqual(utf16_length("😀"), 2)

    def test_empty_text_has_no_units(self):
        self.assertEqual(utf16_length(""), 0)


class Accessibility(unittest.TestCase):
    def test_helper_reports_a_trusted_process(self):
        self.assertTrue(accessibility_trusted(FakeQuartz(trusted=True)))

    def test_helper_reports_an_untrusted_process(self):
        self.assertFalse(accessibility_trusted(FakeQuartz(trusted=False)))

    def test_init_raises_an_actionable_error_when_not_trusted(self):
        with self.assertRaises(AccessibilityPermissionError) as caught:
            MacInput(quartz=FakeQuartz(trusted=False))
        message = str(caught.exception)
        self.assertIn("Accessibility permission", message)
        self.assertIn("System Settings", message)
        self.assertIn("Privacy & Security", message)
        self.assertIn("restart", message)

    def test_init_asks_macos_to_show_the_permission_prompt(self):
        quartz = FakeQuartz(trusted=False)
        with self.assertRaises(AccessibilityPermissionError):
            MacInput(quartz=quartz)
        self.assertEqual(quartz.prompts, [{"AXTrustedCheckOptionPrompt": True}])

    def test_init_does_not_prompt_when_already_trusted(self):
        quartz = FakeQuartz(trusted=True)
        MacInput(quartz=quartz)
        self.assertEqual(quartz.prompts, [])

    def test_permission_error_is_an_input_backend_error(self):
        self.assertTrue(issubclass(AccessibilityPermissionError, InputBackendError))

    def test_missing_pyobjc_raises_an_input_backend_error(self):
        with mock.patch.dict(sys.modules, {"Quartz": None}), self.assertRaisesRegex(
            InputBackendError, "pyobjc"
        ):
            MacInput()


class KeyDown(unittest.TestCase):
    def backend(self, **kwargs):
        return MacInput(quartz=FakeQuartz(**kwargs))

    def test_escape_checks_keycode_53(self):
        self.assertTrue(self.backend(held_keys={KEYCODE_ESCAPE}).key_down(KEY_ESCAPE))

    def test_f9_checks_keycode_101(self):
        self.assertTrue(self.backend(held_keys={KEYCODE_F9}).key_down(KEY_F9))

    def test_keys_are_released_by_default(self):
        backend = self.backend()
        self.assertFalse(backend.key_down(KEY_ESCAPE))
        self.assertFalse(backend.key_down(KEY_F9))

    def test_escape_ignores_other_held_keys(self):
        self.assertFalse(self.backend(held_keys={KEYCODE_F9}).key_down(KEY_ESCAPE))

    def test_left_button_uses_the_button_state(self):
        self.assertTrue(self.backend(left_held=True).key_down(KEY_LEFT_BUTTON))
        self.assertFalse(self.backend(left_held=False).key_down(KEY_LEFT_BUTTON))

    def test_unknown_key_name_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "enter"):
            self.backend().key_down("enter")

    def test_legacy_integer_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            self.backend().key_down(0x78)


class AccessibilityModules(unittest.TestCase):
    def frameworks(self, application_services, quartz):
        return mock.patch.dict(
            sys.modules, {"ApplicationServices": application_services, "Quartz": quartz}
        )

    def test_helper_prefers_application_services_over_quartz(self):
        with self.frameworks(FakeApplicationServices(trusted=True), FakeQuartz(trusted=False)):
            self.assertTrue(accessibility_trusted())

    def test_helper_falls_back_to_quartz_without_application_services(self):
        with self.frameworks(None, FakeQuartz(trusted=True)):
            self.assertTrue(accessibility_trusted())

    def test_helper_skips_a_quartz_without_the_accessibility_functions(self):
        with self.frameworks(None, QuartzWithoutAccessibility()), self.assertRaisesRegex(
            InputBackendError, "pyobjc-framework-ApplicationServices"
        ):
            accessibility_trusted()

    def test_helper_skips_an_application_services_without_the_functions(self):
        with self.frameworks(types.SimpleNamespace(), FakeQuartz(trusted=True)):
            self.assertTrue(accessibility_trusted())

    def test_backend_loaded_from_real_modules_checks_application_services(self):
        quartz = QuartzWithoutAccessibility()
        services = FakeApplicationServices(trusted=False)
        with self.frameworks(services, quartz), self.assertRaises(AccessibilityPermissionError):
            MacInput()
        self.assertEqual(services.prompts, [{"AXTrustedCheckOptionPrompt": True}])

    def test_injected_accessibility_module_is_used_for_the_check_and_the_prompt(self):
        services = FakeApplicationServices(trusted=False)
        with self.assertRaises(AccessibilityPermissionError):
            MacInput(quartz=QuartzWithoutAccessibility(), accessibility=services)
        self.assertEqual(services.prompts, [{"AXTrustedCheckOptionPrompt": True}])

    def test_injected_trusted_accessibility_module_lets_the_backend_start(self):
        services = FakeApplicationServices(trusted=True)
        MacInput(quartz=QuartzWithoutAccessibility(), accessibility=services)
        self.assertEqual(services.prompts, [])


class TypeChar(unittest.TestCase):
    def setUp(self):
        self.quartz = FakeQuartz()
        self.backend = MacInput(quartz=self.quartz)

    def keystrokes(self):
        return [(event["keycode"], event["down"]) for event in self.quartz.posted_events()]

    def test_carriage_return_is_ignored(self):
        self.backend.type_char("\r")
        self.assertEqual(self.quartz.posted, [])

    def test_newline_presses_return(self):
        self.backend.type_char("\n")
        self.assertEqual(self.keystrokes(), [(KEYCODE_RETURN, True), (KEYCODE_RETURN, False)])

    def test_tab_presses_tab(self):
        self.backend.type_char("\t")
        self.assertEqual(self.keystrokes(), [(KEYCODE_TAB, True), (KEYCODE_TAB, False)])

    def test_regular_character_posts_key_down_then_key_up_with_keycode_zero(self):
        self.backend.type_char("a")
        self.assertEqual(self.keystrokes(), [(0, True), (0, False)])

    def test_regular_character_carries_the_literal_text(self):
        self.backend.type_char("a")
        for event in self.quartz.posted_events():
            self.assertEqual(event["unicode"], (1, "a"))

    def test_emoji_sets_the_utf16_length(self):
        self.backend.type_char("😀")
        for event in self.quartz.posted_events():
            self.assertEqual(event["unicode"], (2, "😀"))

    def test_accented_character_is_typed_literally(self):
        self.backend.type_char("é")
        self.assertEqual(self.quartz.posted_events()[0]["unicode"], (1, "é"))

    def test_space_is_typed_literally(self):
        self.backend.type_char(" ")
        self.assertEqual(self.quartz.posted_events()[0]["unicode"], (1, " "))

    def test_events_are_posted_to_the_hid_tap(self):
        self.backend.type_char("x")
        self.assertEqual({tap for tap, _event in self.quartz.posted}, {"hid-tap"})

    def test_newline_does_not_set_a_unicode_string(self):
        self.backend.type_char("\n")
        self.assertEqual({event["unicode"] for event in self.quartz.posted_events()}, {None})

    def test_failed_event_creation_raises_instead_of_posting_nothing(self):
        self.quartz.fail_event_creation = True
        with self.assertRaisesRegex(OSError, "keyboard event"):
            self.backend.type_char("a")
        self.assertEqual(self.quartz.posted, [])


class WindowQueries(unittest.TestCase):
    def setUp(self):
        self.quartz = FakeQuartz()
        self.backend = MacInput(quartz=self.quartz)

    def test_foreground_is_the_frontmost_normal_window(self):
        self.assertEqual(self.backend.foreground(), FRONT_WINDOW)

    def test_foreground_asks_for_on_screen_windows_without_desktop_elements(self):
        self.backend.foreground()
        option, relative_to = self.quartz.window_list_requests[0]
        self.assertTrue(option & FakeQuartz.kCGWindowListOptionOnScreenOnly)
        self.assertTrue(option & FakeQuartz.kCGWindowListExcludeDesktopElements)
        self.assertEqual(relative_to, FakeQuartz.kCGNullWindowID)

    def test_foreground_accepts_windows_without_a_layer_key(self):
        entry = window(9)
        del entry["kCGWindowLayer"]
        self.quartz.windows = [entry]
        self.assertEqual(self.backend.foreground(), 9)

    def test_foreground_is_none_for_an_empty_window_list(self):
        self.quartz.windows = []
        self.assertIsNone(self.backend.foreground())

    def test_foreground_is_none_when_the_window_list_is_unavailable(self):
        self.quartz.windows = None
        self.assertIsNone(self.backend.foreground())

    def test_root_window_at_returns_the_frontmost_window_containing_the_point(self):
        self.assertEqual(self.backend.root_window_at(350, 250), FRONT_WINDOW)

    def test_root_window_at_returns_a_window_behind_when_the_front_one_misses(self):
        self.assertEqual(self.backend.root_window_at(800, 600), BACK_WINDOW)

    def test_root_window_at_is_none_outside_every_window(self):
        self.assertIsNone(self.backend.root_window_at(1000, 900))

    def test_root_window_at_skips_the_menu_bar(self):
        self.assertIsNone(self.backend.root_window_at(5, 5))

    def test_root_window_at_includes_the_near_edge_and_excludes_the_far_edge(self):
        self.assertEqual(self.backend.root_window_at(100, 100), FRONT_WINDOW)
        self.assertEqual(self.backend.root_window_at(499, 399), FRONT_WINDOW)
        self.assertEqual(self.backend.root_window_at(500, 400), BACK_WINDOW)

    def test_root_window_at_understands_rect_style_bounds(self):
        entry = window(9)
        origin = types.SimpleNamespace(x=10, y=10)
        size = types.SimpleNamespace(width=50, height=50)
        entry["kCGWindowBounds"] = types.SimpleNamespace(origin=origin, size=size)
        self.quartz.windows = [entry]
        self.assertEqual(self.backend.root_window_at(20, 20), 9)
        self.assertIsNone(self.backend.root_window_at(200, 200))

    def test_root_window_at_ignores_windows_without_bounds(self):
        entry = window(9)
        del entry["kCGWindowBounds"]
        self.quartz.windows = [entry]
        self.assertIsNone(self.backend.root_window_at(20, 20))

    def test_window_title_prefers_the_window_name(self):
        self.assertEqual(self.backend.window_title(FRONT_WINDOW), "notes.txt")

    def test_window_title_falls_back_to_the_owner_name(self):
        self.assertEqual(self.backend.window_title(BACK_WINDOW), "Safari")

    def test_window_title_falls_back_to_the_owner_when_the_name_is_empty(self):
        self.quartz.windows = [window(9, name="", owner="Finder")]
        self.assertEqual(self.backend.window_title(9), "Finder")

    def test_window_title_is_empty_for_an_unknown_window(self):
        self.assertEqual(self.backend.window_title(99999), "")

    def test_window_title_is_empty_for_none(self):
        self.assertEqual(self.backend.window_title(None), "")

    def test_window_title_is_empty_when_nothing_is_named(self):
        self.quartz.windows = [{"kCGWindowNumber": 9}]
        self.assertEqual(self.backend.window_title(9), "")

    def test_cursor_pos_reads_the_current_mouse_location(self):
        self.assertEqual(self.backend.cursor_pos(), (120, 240))

    def test_cursor_pos_rounds_fractional_coordinates(self):
        self.quartz.pointer = (120.6, 240.4)
        self.assertEqual(self.backend.cursor_pos(), (121, 240))


class Focus(unittest.TestCase):
    def setUp(self):
        self.quartz = FakeQuartz()
        self.appkit = FakeAppKit()
        self.backend = MacInput(quartz=self.quartz, appkit=self.appkit)

    def test_focus_activates_the_owning_application(self):
        self.backend.focus(BACK_WINDOW)
        self.assertEqual(self.appkit.activations, [(BACK_PID, 2)])

    def test_focus_ignores_an_empty_handle(self):
        self.backend.focus(None)
        self.assertEqual(self.appkit.activations, [])

    def test_focus_ignores_an_unknown_window(self):
        self.backend.focus(99999)
        self.assertEqual(self.appkit.activations, [])

    def test_focus_ignores_an_application_that_has_quit(self):
        self.appkit.running.clear()
        self.backend.focus(FRONT_WINDOW)
        self.assertEqual(self.appkit.activations, [])

    def test_focus_without_appkit_raises_an_input_backend_error(self):
        backend = MacInput(quartz=self.quartz)
        with mock.patch.dict(sys.modules, {"AppKit": None}), self.assertRaisesRegex(
            InputBackendError, "pyobjc"
        ):
            backend.focus(FRONT_WINDOW)


class SameApplication(unittest.TestCase):
    TEXT_PANEL = 44

    def setUp(self):
        windows = front_to_back_windows()
        windows.insert(2, window(self.TEXT_PANEL, owner="TextEdit", pid=FRONT_PID))
        self.backend = MacInput(quartz=FakeQuartz(windows=windows))

    def test_two_windows_of_one_application_match(self):
        self.assertTrue(self.backend.same_application(FRONT_WINDOW, self.TEXT_PANEL))

    def test_windows_of_different_applications_do_not_match(self):
        self.assertFalse(self.backend.same_application(FRONT_WINDOW, BACK_WINDOW))

    def test_an_unknown_window_never_matches(self):
        self.assertFalse(self.backend.same_application(FRONT_WINDOW, 999))
        self.assertFalse(self.backend.same_application(None, None))


class Click(unittest.TestCase):
    def setUp(self):
        self.quartz = FakeQuartz()
        self.backend = MacInput(quartz=self.quartz)
        sleeper = mock.patch.object(mac_input.time, "sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_click_moves_then_presses_and_releases_the_left_button(self):
        self.backend.click(30, 40)
        self.assertEqual(
            [
                (event["type"], event["point"], event["button"])
                for event in self.quartz.posted_events()
            ],
            [("mouse-moved", (30, 40), 0), ("left-down", (30, 40), 0), ("left-up", (30, 40), 0)],
        )

    def test_click_pauses_between_press_and_release(self):
        self.backend.click(30, 40)
        self.sleep.assert_called()

    def test_click_releases_the_button_if_interrupted_while_held(self):
        self.sleep.side_effect = [None, RuntimeError("interrupted")]
        with self.assertRaises(RuntimeError):
            self.backend.click(30, 40)
        self.assertEqual(self.quartz.posted_events()[-1]["type"], "left-up")

    def test_failed_event_creation_raises_instead_of_posting_nothing(self):
        self.quartz.fail_event_creation = True
        with self.assertRaisesRegex(OSError, "mouse event"):
            self.backend.click(30, 40)
        self.assertEqual(self.quartz.posted, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
