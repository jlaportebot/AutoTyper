"""Persisted user settings (speed, rhythm, start delay, typos, last text and its styles)."""

import copy
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
    "typos": 2,
    "catch": 8,
    "rest_every": 0,
    "rest_for": 3,
    "formatting": True,
    "text": "",
    "styles": [],
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


def _is_valid(value, default):
    """True if a saved value has the same kind as its default (whole numbers for numbers)."""
    if isinstance(default, (bool, str, list)):
        return isinstance(value, type(default))
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return value.is_integer()
    return isinstance(value, int)


def _merge_with_defaults(saved):
    """Known keys from ``saved`` where valid, defaults everywhere else."""
    merged = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in saved:
            continue
        value = saved[key]
        if not _is_valid(value, default):
            logger.warning("Ignoring saved %s=%r; using %r", key, value, default)
            continue
        merged[key] = int(value) if isinstance(value, float) else value
    return merged


def load_settings():
    """Load saved settings, falling back to defaults on any problem."""
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            saved = json.load(handle)
    except (OSError, ValueError, TypeError):
        return copy.deepcopy(DEFAULTS)
    if not isinstance(saved, dict):
        return copy.deepcopy(DEFAULTS)
    return _merge_with_defaults(saved)


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
