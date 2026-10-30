"""Unit tests for choosing the input backend of the running platform."""

import sys
import types
import unittest
from unittest import mock

from autotyper.errors import InputBackendError
from autotyper.input_factory import backend_name, create_backend


def stub_backend_module(module, class_name, **class_kwargs):
    """Patch a backend module out of ``sys.modules`` so no real input API is touched."""
    backend_class = mock.Mock(**class_kwargs)
    stub = types.SimpleNamespace(**{class_name: backend_class})
    patcher = mock.patch.dict(sys.modules, {f"autotyper.{module}": stub})
    return patcher, backend_class


class BackendName(unittest.TestCase):
    def test_returns_windows_on_win32(self):
        with mock.patch("sys.platform", "win32"):
            self.assertEqual(backend_name(), "windows")

    def test_returns_macos_on_darwin(self):
        with mock.patch("sys.platform", "darwin"):
            self.assertEqual(backend_name(), "macos")

    def test_returns_linux_on_linux_variants(self):
        for platform in ("linux", "linux2"):
            with mock.patch("sys.platform", platform):
                self.assertEqual(backend_name(), "linux")

    def test_returns_unsupported_for_other_platforms(self):
        with mock.patch("sys.platform", "freebsd14"):
            self.assertEqual(backend_name(), "unsupported")


class CreateBackend(unittest.TestCase):
    def assert_picks(self, platform, module, class_name):
        patcher, backend_class = stub_backend_module(module, class_name)
        with mock.patch("sys.platform", platform), patcher:
            self.assertIs(create_backend(), backend_class.return_value)
        backend_class.assert_called_once_with()

    def test_picks_the_windows_backend_on_win32(self):
        self.assert_picks("win32", "win_input", "WindowsInput")

    def test_picks_the_mac_backend_on_darwin(self):
        self.assert_picks("darwin", "mac_input", "MacInput")

    def test_picks_the_linux_backend_on_linux(self):
        self.assert_picks("linux", "linux_input", "LinuxInput")

    def test_raises_naming_supported_systems_on_unsupported_platform(self):
        with mock.patch("sys.platform", "freebsd14"), self.assertRaises(RuntimeError) as caught:
            create_backend()
        message = str(caught.exception)
        for system in ("Windows", "macOS", "Linux"):
            self.assertIn(system, message)
        self.assertIn("freebsd14", message)

    def test_unsupported_platform_error_is_an_input_backend_error(self):
        with mock.patch("sys.platform", "freebsd14"), self.assertRaises(InputBackendError):
            create_backend()

    def test_missing_python_xlib_raises_an_input_backend_error(self):
        with mock.patch.dict(sys.modules, {"Xlib": None}), mock.patch("sys.platform", "linux"):
            sys.modules.pop("autotyper.linux_input", None)
            with self.assertRaisesRegex(InputBackendError, "python-xlib"):
                create_backend()

    def test_propagates_backend_start_up_errors(self):
        patcher, backend_class = stub_backend_module("linux_input", "LinuxInput")
        backend_class.side_effect = RuntimeError("no X")
        with mock.patch("sys.platform", "linux"), patcher, self.assertRaisesRegex(
            RuntimeError, "no X"
        ):
            create_backend()


if __name__ == "__main__":
    unittest.main(verbosity=2)
