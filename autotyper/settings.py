"""Persisted user settings (speed, rhythm, start delay, last text)."""

import json
import logging
import os
import sys

APP_NAME = "AutoTyper"

logger = logging.getLogger(__name__)

DEFAULTS = {
    "wpm": 65,
    "variation": 25,
    "delay": 3,
    "text": "",
}


def config_base_dir():
    """Per-user configuration directory of the running operating system."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        return os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support")
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")


def settings_path():
    """Absolute path of the settings file inside the user's config directory."""
    return os.path.join(config_base_dir(), APP_NAME, "settings.json")


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
    path = settings_path()
    try:
        payload = json.dumps(settings)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except (OSError, TypeError) as exc:
        logger.warning("Could not save settings to %s: %s", path, exc)
