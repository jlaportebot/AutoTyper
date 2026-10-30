"""Unit tests for settings persistence and per-OS config directories."""

import os
import tempfile
import unittest
from unittest import mock

from autotyper.settings import (
    DEFAULTS,
    config_base_dir,
    load_settings,
    save_settings,
    settings_path,
)


class ConfigBaseDir(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        home_env = {"HOME": self.home, "USERPROFILE": self.home}
        patcher = mock.patch.dict(os.environ, home_env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_windows_uses_appdata(self):
        env = {"APPDATA": os.path.join(self.home, "Roaming")}
        with mock.patch("sys.platform", "win32"), mock.patch.dict(os.environ, env):
            self.assertEqual(config_base_dir(), env["APPDATA"])

    def test_windows_falls_back_to_roaming_profile_when_appdata_missing(self):
        with mock.patch("sys.platform", "win32"), mock.patch.dict(os.environ):
            os.environ.pop("APPDATA", None)
            expected = os.path.join(self.home, "AppData", "Roaming")
            self.assertEqual(config_base_dir(), expected)

    def test_macos_uses_application_support(self):
        with mock.patch("sys.platform", "darwin"):
            expected = os.path.join(self.home, "Library", "Application Support")
            self.assertEqual(config_base_dir(), expected)

    def test_macos_ignores_xdg_config_home(self):
        with mock.patch("sys.platform", "darwin"), mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": "/elsewhere"}
        ):
            self.assertNotEqual(config_base_dir(), "/elsewhere")

    def test_linux_uses_xdg_config_home(self):
        xdg = os.path.join(self.home, "xdg")
        with mock.patch("sys.platform", "linux"), mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": xdg}
        ):
            self.assertEqual(config_base_dir(), xdg)

    def test_linux_falls_back_to_dot_config_when_xdg_unset(self):
        with mock.patch("sys.platform", "linux"), mock.patch.dict(os.environ):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(config_base_dir(), os.path.join(self.home, ".config"))

    def test_linux_falls_back_to_dot_config_when_xdg_is_empty(self):
        with mock.patch("sys.platform", "linux"), mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": ""}
        ):
            self.assertEqual(config_base_dir(), os.path.join(self.home, ".config"))

    def test_other_platforms_use_the_linux_layout(self):
        with mock.patch("sys.platform", "freebsd14"), mock.patch.dict(os.environ):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(config_base_dir(), os.path.join(self.home, ".config"))

    def test_settings_path_nests_under_the_app_folder(self):
        with mock.patch("sys.platform", "linux"), mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": self.home}
        ):
            expected = os.path.join(self.home, "AutoTyper", "settings.json")
            self.assertEqual(settings_path(), expected)


class Settings(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        patcher = mock.patch("autotyper.settings.config_base_dir", return_value=self.tempdir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_path_is_inside_the_config_directory(self):
        self.assertTrue(settings_path().startswith(self.tempdir))
        self.assertIn("AutoTyper", settings_path())

    def test_defaults_when_file_missing(self):
        self.assertEqual(load_settings(), DEFAULTS)

    def test_roundtrip(self):
        save_settings({"wpm": 90, "variation": 10, "delay": 5, "text": "hi"})
        loaded = load_settings()
        self.assertEqual(loaded["wpm"], 90)
        self.assertEqual(loaded["text"], "hi")

    def test_missing_keys_fall_back_to_defaults(self):
        save_settings({"wpm": 42})
        loaded = load_settings()
        self.assertEqual(loaded["wpm"], 42)
        self.assertEqual(loaded["delay"], DEFAULTS["delay"])

    def test_corrupt_file_falls_back_to_defaults(self):
        path = settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(load_settings(), DEFAULTS)

    def test_non_object_json_falls_back_to_defaults(self):
        path = settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("[1, 2, 3]")
        self.assertEqual(load_settings(), DEFAULTS)

    def test_save_creates_missing_directory(self):
        nested = os.path.join(self.tempdir, "nested")
        with mock.patch("autotyper.settings.config_base_dir", return_value=nested):
            save_settings({"wpm": 10})
            self.assertTrue(os.path.exists(settings_path()))

    def test_save_does_not_raise_when_the_config_directory_is_unusable(self):
        blocker = os.path.join(self.tempdir, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("a file where a directory is needed")
        with mock.patch("autotyper.settings.config_base_dir", return_value=blocker):
            save_settings({"wpm": 10})
            self.assertEqual(load_settings(), DEFAULTS)

    def test_save_logs_a_warning_when_the_config_directory_is_unusable(self):
        blocker = os.path.join(self.tempdir, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("a file where a directory is needed")
        with mock.patch(
            "autotyper.settings.config_base_dir", return_value=blocker
        ), self.assertLogs("autotyper.settings", level="WARNING") as logged:
            save_settings({"wpm": 10})
        self.assertIn("Could not save settings", logged.output[0])

    def test_save_logs_a_warning_for_unserialisable_settings(self):
        with self.assertLogs("autotyper.settings", level="WARNING") as logged:
            save_settings({"wpm": object()})
        self.assertIn("Could not save settings", logged.output[0])

    def test_failed_save_keeps_the_previously_saved_settings(self):
        save_settings({"wpm": 90})
        with self.assertLogs("autotyper.settings", level="WARNING"):
            save_settings({"wpm": 91, "text": object()})
        self.assertEqual(load_settings()["wpm"], 90)

    def test_save_does_not_raise_for_unserialisable_settings(self):
        save_settings({"wpm": object()})
        self.assertEqual(load_settings()["wpm"], DEFAULTS["wpm"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
