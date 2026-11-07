# AutoTyper v1.4.0

**Timed breaks: type for a while, rest, repeat.**

![AutoTyper icon](assets/autotyper-logo.png)

## What's new

- **Break every / Break for.** AutoTyper now rests for a few seconds every so
  often. For example, *every 10 seconds, rest 2 seconds*, or *every 15 seconds,
  rest 3 seconds*. Both are sliders (0 seconds = no breaks).
  - Neither number is exact: the interval varies by 15% and each rest by 25%,
    so it never looks mechanical.
  - Time spent paused with `F9` does not count towards the next break.
  - The time estimate includes the breaks, and the settings are remembered.
- Works together with typos and formatting.

Breaks are off by default. Everything from v1.2.0 (typos) and v1.3.0 (kept
formatting) is still here.

## Download

| System | File |
| --- | --- |
| Windows (64-bit) | `AutoTyper.exe` or `AutoTyper-windows-x64.zip` |
| macOS, Apple Silicon | `AutoTyper-1.4.0-macos-arm64.dmg` |
| macOS, Intel | `AutoTyper-1.4.0-macos-x64.dmg` |
| Linux, x86_64 | `AutoTyper-1.4.0-linux-x86_64.AppImage` |
| Linux, ARM64 | `AutoTyper-1.4.0-linux-aarch64.AppImage` |

No Python installation is needed for any of them.

### First run

- **Windows** — SmartScreen may warn about an unrecognised app: choose
  **More info → Run anyway**.
- **macOS** — open the DMG and drag AutoTyper to Applications. The first launch
  is blocked: right-click the app → **Open** → **Open** (on macOS 15 and later,
  use **Open Anyway** in **System Settings → Privacy & Security**). Then enable AutoTyper
  in **System Settings → Privacy & Security → Accessibility** (macOS will ask)
  and restart the app, otherwise it cannot type.
- **Linux** — `chmod +x` the AppImage, then double-click it or run it from a
  terminal. AutoTyper needs an **X11** session (XWayland works); native Wayland
  windows cannot receive synthetic input.

## How to use it

Press **Pick spot** and click the text box you want to write into, paste your
text (formatted or plain), set the speed and how many mistakes to make, and
press **Go**. `F9` pauses and resumes, `Esc` stops. If you click another window while typing,
AutoTyper pauses so it never types into the wrong app.

Full documentation: [README.md](https://github.com/jlaportebot/AutoTyper#readme)

## License

MIT
