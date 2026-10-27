# AutoTyper

**Types your text into any field on Windows — one key at a time, at a pace that
looks human.**

![AutoTyper icon](assets/autotyper-logo.png)

AutoTyper is a small desktop app for Windows. You pick the spot on screen you
want to write into, paste the text you want written, choose how fast it should
be typed, and press **Go**. AutoTyper clicks the spot, focuses it and types the
text character by character with natural rhythm — variable speed, a pause at
commas, a longer pause at full stops, a beat between sentences.

It is meant for writing into anything that monitors how you type: timed
writing platforms, prose trainers, typing tutors, form fillers you have to
"write" yourself, and any app that accepts real keyboard input.

[![CI](https://github.com/jlaportebot/AutoTyper/actions/workflows/ci.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/ci.yml)
[![Build](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-windows.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c8f560.svg)](LICENSE)

---

## Download

### Ready-made executable (recommended)

Grab **AutoTyper.exe** from the [Releases page](https://github.com/jlaportebot/AutoTyper/releases/latest).
It is a single self-contained file — no Python installation required.

1. Download `AutoTyper.exe` (or the `AutoTyper-windows-x64.zip` bundle).
2. Windows SmartScreen may warn about an unrecognised app — choose
   **More info → Run anyway**.
3. Double-click `AutoTyper.exe`.

### Run from source

You need **Python 3.8+** on Windows (the tkinter GUI ships with the standard
python.org installer).

```bat
git clone https://github.com/jlaportebot/AutoTyper.git
cd AutoTyper
Start AutoTyper.bat
```

or manually:

```bat
python main.pyw
```

There are **no third-party Python dependencies** — only the standard library.

---

## How to use it

The app is a three-step flow.

### 01 · Target

Press **Pick spot**, then click the text box you want to write into. AutoTyper
hides itself while you do this, records the window and the exact pixel
position, and shows you the target window's title so you can confirm it.

Press `Esc` while picking to cancel.

### 02 · Text

Type or paste your text, or press **Open .txt** to load a `.txt`/`.md` file.
The counter shows characters, words and a live **ETA** for the current speed
settings.

### 03 · Speed & timing

- **Words / minute** — 10 to 200. The base typing speed (1 word = 5
  characters, the standard WPM convention).
- **Rhythm** — 0% to 60%. How much the delay between keystrokes varies.
  0% is a metronome; 25–40% looks convincingly human.
- **Start delay** — 1 to 10 seconds. A countdown before AutoTyper clicks the
  target, so you can get your hands off the mouse.

Press **Go**. The full window collapses into a small floating control bar in
the corner (it moves itself if it would cover your target), a countdown runs,
AutoTyper clicks the target and starts typing.

---

## Controls while typing

| Control | Action |
| --- | --- |
| `F9` | Pause / resume. Resumes from the exact character it stopped on. |
| `Esc` | Stop the session. |
| **Pause** button | Same as `F9`. |
| **Stop** button | Same as `Esc`. |

**Focus protection:** if you click another window while AutoTyper is typing, it
pauses itself automatically so it can never type into the wrong app. When you
resume, it counts down two seconds and brings the target window back to the
front by itself.

Your text, speed, rhythm and delay are remembered between sessions
(`%APPDATA%\AutoTyper\settings.json`).

---

## What makes it look human

AutoTyper does not paste text — it sends real keystrokes through the Windows
`SendInput` API, one Unicode code point at a time, so the target app sees a
genuine keyboard user.

On top of the base WPM speed it adds:

- **Randomised inter-key delays** — every keystroke is delayed by a random
  amount within the Rhythm percentage.
- **Word rhythm** — a space stretches the next keystroke slightly.
- **Comma / colon / semicolon pause** — a short randomised pause.
- **Full stop / exclamation / question mark pause** — a longer randomised
  pause.
- **Newline pause** — the longest pause, because humans lift the keyboard
  between lines.
- **Natural resume** — resuming restarts from the exact character, with the
  remaining delay preserved, so there is no visible jump.

Unicode (accents, emoji, CJK) and tabs/newlines are handled properly:
emoji are sent as UTF-16 surrogate pairs, newlines as `Enter`, tabs as `Tab`.

---

## Project layout

```
AutoTyper/
├── autotyper/
│   ├── engine.py       # typing engine: pause, resume, stop, focus guard
│   ├── gui.py          # Tkinter desktop UI
│   ├── gui_colors.py   # colour palette
│   ├── pacing.py       # human-like timing maths (pure functions)
│   ├── settings.py     # persisted preferences
│   ├── widgets.py      # flat button + slider widgets
│   └── win_input.py    # Windows SendInput / mouse / window API layer
├── tests/              # unit + UI tests (44 tests, no Windows needed)
├── assets/             # application icon and logo
├── tools/make_icon.py  # regenerates the icon artwork
├── main.pyw            # launcher
├── AutoTyper.spec      # PyInstaller build spec
└── .github/workflows/  # CI, Windows build and release automation
```

---

## Development

```bash
# tests (Linux CI runs them under xvfb for the Tk UI)
python -m unittest discover -s tests -t . -v

# lint
ruff check .
```

The engine is deliberately platform independent: it talks to a small backend
interface (`type_char`, `key_down`, `foreground`, `focus`), so the whole test
suite runs on any OS with a fake backend. Only `win_input.py` talks to Win32.

### Build the Windows executable yourself

On a Windows machine (or use the included GitHub Actions workflow):

```bat
python -m pip install pyinstaller
pyinstaller --clean --noconfirm AutoTyper.spec
```

The result is `dist\AutoTyper.exe`.

---

## Troubleshooting

**Nothing is typed into the target app.** Windows blocks synthetic input from
a lower-privilege process into an elevated one. If the target app runs as
Administrator, run AutoTyper as Administrator too.

**The cursor moved while paused.** Do not click inside the target text box
while paused — that repositions the caret, and typing resumes wherever the
caret now is.

**Text is typed into the wrong place.** AutoTyper pauses when you switch
windows, but if you move the target window after picking, the stored pixel
position is stale. Pick the spot again.

**SmartScreen blocks the download.** The executable is unsigned. Use
**More info → Run anyway**, or build it from source.

---

## License

MIT — see [LICENSE](LICENSE).

© 2026 jlaportebot
