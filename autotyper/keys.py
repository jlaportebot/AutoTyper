"""Platform-neutral key identifiers shared by the engine and the GUI.

Every input backend maps these symbolic names to its own native key codes.
"""

KEY_ESCAPE = "escape"
KEY_F9 = "f9"
KEY_LEFT_BUTTON = "left_button"

# Formatting shortcuts (Ctrl+B/I/U, or Command on macOS). In a typing plan they
# stand in for a key press; they are never single characters, so no text clashes.
FORMAT_BOLD = "format:bold"
FORMAT_ITALIC = "format:italic"
FORMAT_UNDERLINE = "format:underline"
FORMAT_KEYS = (FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE)
