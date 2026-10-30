"""Tests for the command-line entry point and its ``--smoke-test`` health check."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from autotyper import __main__ as entry
from autotyper.errors import InputBackendError
from tests.test_gui import FakeBackend

HAS_DISPLAY = bool(os.environ.get("DISPLAY")) or sys.platform in ("win32", "darwin")
OK_MARKER = "AUTOTYPER_SMOKE_OK"
FAIL_MARKER = "AUTOTYPER_SMOKE_FAIL"


def run_smoke():
    """Run the smoke test and return ``(exit_code, printed_text)``."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = entry.smoke_test()
    return code, out.getvalue()


@unittest.skipUnless(HAS_DISPLAY, "needs a display (run under xvfb-run)")
class SmokeTestWithDisplay(unittest.TestCase):
    def test_reports_ok_with_platform_and_backend(self):
        with mock.patch.object(entry, "_smoke_backend", return_value=(FakeBackend(), "")):
            code, text = run_smoke()
        self.assertEqual(code, 0)
        self.assertIn(OK_MARKER, text)
        self.assertIn("platform=", text)
        self.assertIn("backend=", text)

    def test_reports_the_missing_macos_permission_without_failing(self):
        with mock.patch.object(
            entry, "_smoke_backend", return_value=(FakeBackend(), "accessibility=missing")
        ):
            code, text = run_smoke()
        self.assertEqual(code, 0)
        self.assertIn("accessibility=missing", text)

    def test_types_nothing(self):
        backend = FakeBackend()
        with mock.patch.object(entry, "_smoke_backend", return_value=(backend, "")):
            run_smoke()
        self.assertEqual(backend.out, [])
        self.assertEqual(backend.clicks, [])


class SmokeTestFailures(unittest.TestCase):
    def test_fails_when_the_display_cannot_be_opened(self):
        import tkinter

        with mock.patch.object(
            entry, "_smoke_backend", return_value=(FakeBackend(), "")
        ), mock.patch("tkinter.Tk", side_effect=tkinter.TclError("no display name")):
            code, text = run_smoke()
        self.assertEqual(code, 1)
        self.assertIn(FAIL_MARKER, text)
        self.assertIn("no display name", text)
        self.assertNotIn(OK_MARKER, text)

    def test_fails_when_the_input_backend_cannot_start(self):
        with mock.patch.object(
            entry, "_smoke_backend", side_effect=InputBackendError("X server missing")
        ):
            code, text = run_smoke()
        self.assertEqual(code, 1)
        self.assertIn(f"{FAIL_MARKER}: X server missing", text)

    def test_fails_when_a_bundled_dependency_is_missing(self):
        with mock.patch.object(
            entry, "_smoke_backend", side_effect=ImportError("No module named 'Xlib'")
        ):
            code, text = run_smoke()
        self.assertEqual(code, 1)
        self.assertIn("Xlib", text)


class SmokeBackend(unittest.TestCase):
    def test_uses_the_factory_backend_on_non_mac_platforms(self):
        fake = object()
        with mock.patch.object(entry, "backend_name", return_value="linux"), mock.patch.object(
            entry, "create_backend", return_value=fake
        ):
            backend, note = entry._smoke_backend()
        self.assertIs(backend, fake)
        self.assertEqual(note, "")

    def test_macos_without_permission_skips_the_prompting_backend(self):
        created = mock.Mock()
        with mock.patch.object(entry, "backend_name", return_value="macos"), mock.patch.object(
            entry, "create_backend", created
        ), mock.patch.object(entry, "_accessibility_trusted", return_value=False):
            backend, note = entry._smoke_backend()
        created.assert_not_called()
        self.assertIsNotNone(backend)
        self.assertEqual(note, "accessibility=missing")

    def test_macos_with_permission_uses_the_real_backend(self):
        fake = object()
        with mock.patch.object(entry, "backend_name", return_value="macos"), mock.patch.object(
            entry, "create_backend", return_value=fake
        ), mock.patch.object(entry, "_accessibility_trusted", return_value=True):
            backend, note = entry._smoke_backend()
        self.assertIs(backend, fake)
        self.assertEqual(note, "accessibility=granted")


class MainDispatch(unittest.TestCase):
    def test_smoke_flag_runs_the_smoke_test_and_not_the_gui(self):
        with mock.patch.object(entry, "smoke_test", return_value=0) as smoke, mock.patch(
            "autotyper.gui.run"
        ) as run_gui:
            code = entry.main(["--smoke-test"])
        self.assertEqual(code, 0)
        smoke.assert_called_once_with()
        run_gui.assert_not_called()

    def test_smoke_failure_exit_code_is_propagated(self):
        with mock.patch.object(entry, "smoke_test", return_value=1):
            self.assertEqual(entry.main(["--smoke-test"]), 1)

    def test_no_flag_launches_the_gui(self):
        with mock.patch("autotyper.gui.run", return_value=0) as run_gui:
            self.assertEqual(entry.main([]), 0)
        run_gui.assert_called_once_with()

    def test_unknown_arguments_are_ignored(self):
        with mock.patch("autotyper.gui.run", return_value=0) as run_gui:
            self.assertEqual(entry.main(["-psn_0_12345"]), 0)
        run_gui.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
