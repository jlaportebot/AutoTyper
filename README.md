# AutoTyper

**Types your text into any field on Windows, macOS or Linux — one key at a
time, at a pace that looks human.**

![AutoTyper icon](assets/autotyper-logo.png)

AutoTyper is a small desktop app for Windows, macOS and Linux. You pick the
spot on screen you want to write into, paste the text you want written, choose
how fast it should be typed, and press **Go**. AutoTyper clicks the spot,
focuses it and types the text character by character with natural rhythm — variable speed, a pause at
commas, a longer pause at full stops, a beat between sentences.

It is meant for writing into anything that monitors how you type: timed
writing platforms, prose trainers, typing tutors, form fillers you have to
"write" yourself, and any app that accepts real keyboard input.

[![CI](https://github.com/jlaportebot/AutoTyper/actions/workflows/ci.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/ci.yml)
[![Windows build](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-windows.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-windows.yml)
[![macOS build](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-macos.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-macos.yml)
[![Linux build](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-linux.yml/badge.svg)](https://github.com/jlaportebot/AutoTyper/actions/workflows/build-linux.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c8f560.svg)](LICENSE)

---

## Download

### Ready-made apps (recommended)

Grab the file for your system from the
[Releases page](https://github.com/jlaportebot/AutoTyper/releases/latest). Each
one is self-contained — no Python installation required. In the names below,
`<version>` is the release number, for example `1.1.0`.

| System | File |
| --- | --- |
| Windows (64-bit) | `AutoTyper.exe` (or `AutoTyper-windows-x64.zip`) |
| macOS, Apple Silicon | `AutoTyper-<version>-macos-arm64.dmg` |
| macOS, Intel | `AutoTyper-<version>-macos-x64.dmg` |
| Linux, x86_64 | `AutoTyper-<version>-linux-x86_64.AppImage` |
| Linux, ARM64 | `AutoTyper-<version>-linux-aarch64.AppImage` |

**Windows.** Double-click `AutoTyper.exe`. SmartScreen may warn about an
unrecognised app — choose **More info → Run anyway**.

**macOS.** Intel (x64) and Apple Silicon (arm64) builds are separate
downloads — pick the one that matches your Mac.

1. Open the DMG and drag **AutoTyper** to **Applications**.
2. The first launch is blocked because the app is not notarized. On macOS 14
   and earlier, right-click the app, choose **Open**, then **Open** again. On
   macOS 15 (Sequoia) and later, try to open it once, then go to **System
   Settings → Privacy & Security** and click **Open Anyway**. From a terminal,
   `xattr -dr com.apple.quarantine /Applications/AutoTyper.app` clears the
   block. `spctl --assess --type execute --verbose /Applications/AutoTyper.app`
   reports "rejected" for this app because it is ad-hoc signed and not
   notarized; that is expected, and `codesign --verify --deep --strict` should
   still pass.
3. AutoTyper asks for **Accessibility** permission. Open **System Settings →
   Privacy & Security → Accessibility**, enable **AutoTyper**, and restart the
   app. macOS only lets apps with this permission send keystrokes.

**Linux.** Make the AppImage executable, then double-click it or run it from a
terminal:

```bash
chmod +x AutoTyper-<version>-linux-x86_64.AppImage
./AutoTyper-<version>-linux-x86_64.AppImage
```

AutoTyper needs an **X11** session (XWayland works). A native Wayland session
cannot receive synthetic input — log in with an X11 session, or start the apps
you want to type into through XWayland. If your system has no FUSE, run the
AppImage with `--appimage-extract-and-run`.

### Run from source

You need **Python 3.8+** (the tkinter GUI ships with the standard python.org
installer; on Linux install your distribution's `python3-tk` package).

```bash
git clone https://github.com/jlaportebot/AutoTyper.git
cd AutoTyper
python main.pyw          # on Windows you can also double-click "Start AutoTyper.bat"
```

The GUI uses only the standard library. The platform input layer needs one
package on two systems; the packaged apps above already include it:

| System | Needs | Install |
| --- | --- | --- |
| Windows | nothing extra | — |
| macOS | pyobjc (Quartz, Cocoa, ApplicationServices) | `pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices` |
| Linux | python-xlib | `pip install python-xlib` |

Check that an install works without typing anything:

```bash
python -m autotyper --smoke-test      # prints AUTOTYPER_SMOKE_OK and exits
```

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
in `settings.json` inside the AutoTyper settings folder:

| System | Path |
| --- | --- |
| Windows | `%APPDATA%\AutoTyper\settings.json` |
| macOS | `~/Library/Application Support/AutoTyper/settings.json` |
| Linux | `~/.config/AutoTyper/settings.json` |

---

## What makes it look human

AutoTyper does not paste text — it sends real keystrokes through the
operating system's own input layer, one Unicode code point at a time, so the
target app sees a genuine keyboard user:

| System | Input mechanism |
| --- | --- |
| Windows | Win32 `SendInput` |
| Linux | X11 `XTEST` extension (python-xlib) |
| macOS | Quartz `CGEvent` (pyobjc) |

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
│   ├── __main__.py     # entry point and --smoke-test health check
│   ├── engine.py       # typing engine: pause, resume, stop, focus guard
│   ├── errors.py       # InputBackendError shared by all backends
│   ├── gui.py          # Tkinter desktop UI
│   ├── gui_colors.py   # colour palette
│   ├── input_factory.py# picks the input backend for the running OS
│   ├── keys.py         # key names shared by all backends
│   ├── linux_input.py  # Linux X11 / XTEST layer
│   ├── mac_input.py    # macOS Quartz CGEvent layer
│   ├── pacing.py       # human-like timing maths (pure functions)
│   ├── settings.py     # persisted preferences (per-OS config folder)
│   ├── widgets.py      # flat button + slider widgets
│   └── win_input.py    # Windows SendInput / mouse / window API layer
├── tests/              # unit, UI and packaging tests (no real OS input needed)
├── assets/             # icons (.ico, .icns, .png) and logo
├── packaging/linux/    # AppImage desktop entry and AppRun launcher
├── tools/
│   ├── make_icon.py    # the icon artwork
│   ├── make_icons.py   # regenerates every icon format in assets/
│   ├── build_appimage.sh  # Linux AppImage
│   ├── build_dmg.sh    # macOS app signing + DMG
│   └── smoke_check.sh  # runs --smoke-test and checks the result
├── main.pyw            # launcher
├── AutoTyper.spec      # PyInstaller spec for all three systems
└── .github/workflows/
    ├── ci.yml              # lint + tests on Linux, macOS and Windows
    ├── build-windows.yml   # AutoTyper.exe
    ├── build-macos.yml     # arm64 + x64 DMGs
    ├── build-linux.yml     # x86_64 + aarch64 AppImages
    └── release.yml         # a v* tag publishes every platform
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
suite runs on any OS with a fake backend. Only `win_input.py`, `linux_input.py`
and `mac_input.py` talk to the operating system.

### Build the apps yourself

PyInstaller cannot cross-compile: build on the system you are targeting (or use
the GitHub Actions workflows). One spec, `AutoTyper.spec`, handles all three
systems.

```bash
python -m pip install pyinstaller
pyinstaller --clean --noconfirm AutoTyper.spec
```

| System | Extra packages | Result |
| --- | --- | --- |
| Windows | — | `dist\AutoTyper.exe` |
| macOS | `pyobjc-framework-Quartz`, `pyobjc-framework-Cocoa`, `pyobjc-framework-ApplicationServices` | `dist/AutoTyper.app` |
| Linux | `python-xlib` | `dist/AutoTyper` |

Then package it:

```bash
tools/build_appimage.sh x86_64      # or aarch64; needs curl and file
tools/build_dmg.sh                  # macOS only: build, ad-hoc sign, create the DMG
python tools/make_icons.py          # only if you change the artwork (needs Pillow)
```

Every build can check itself without typing anything:
`dist/AutoTyper --smoke-test` prints `AUTOTYPER_SMOKE_OK`.

### Release

Pushing a tag such as `v1.1.0` runs `release.yml`: it builds, smoke-tests and
publishes the Windows, macOS and Linux files in one release.

---

## Troubleshooting

**Windows: nothing is typed into the target app.** Windows blocks synthetic input from
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

**macOS: "AutoTyper can't be opened" or nothing is typed.** The app is not
notarized, so the first launch needs right-click → **Open** → **Open** (macOS 15 and
later: **Open Anyway** in Privacy & Security, see the install steps). Typing
only works once **System Settings → Privacy & Security → Accessibility** lists
AutoTyper as enabled; restart the app after enabling it. If you moved or
re-downloaded the app and the switch is already on, toggle it off and on again.

**Linux: "could not connect to an X11 display".** AutoTyper needs an X11
session. On Wayland, apps that run through XWayland can be typed into, but
native Wayland windows cannot receive synthetic input — choose an X11 session
at the login screen, or run the target app with its XWayland/X11 option.

**Linux: the AppImage will not start.** Run `chmod +x` on it first. Without
FUSE, start it with `--appimage-extract-and-run`.

---

## License

MIT — see [LICENSE](LICENSE).

© 2026 jlaportebot
