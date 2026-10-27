"""Unit tests for settings persistence."""

import os
import tempfile
import unittest

from autotyper.settings import DEFAULTS, load_settings, save_settings, settings_path


class Settings(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.previous = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tempdir

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.previous

    def test_path_is_inside_appdata(self):
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

    def test_save_creates_missing_directory(self):
        nested = os.path.join(self.tempdir, "nested")
        os.environ["APPDATA"] = nested
        save_settings({"wpm": 10})
        self.assertTrue(os.path.exists(settings_path()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
