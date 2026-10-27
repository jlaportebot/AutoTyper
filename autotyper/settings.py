"""Persisted user settings (speed, rhythm, start delay, last text)."""

import json
import os

APP_NAME = "AutoTyper"

DEFAULTS = {
    "wpm": 65,
    "variation": 25,
    "delay": 3,
    "text": "",
}


def settings_path():
    """Absolute path of the settings file inside the user profile."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME, "settings.json")


def load_settings():
    """Load saved settings, falling back to defaults on any problem."""
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            saved = json.load(handle)
        if not isinstance(saved, dict):
            return dict(DEFAULTS)
        return {**DEFAULTS, **saved}
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)


def save_settings(settings):
    """Persist settings; never raises so the UI can always close cleanly."""
    try:
        directory = os.path.dirname(settings_path())
        os.makedirs(directory, exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as handle:
            json.dump(settings, handle)
    except (OSError, TypeError):
        pass
