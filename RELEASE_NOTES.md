# AutoTyper v1.1.0

**AutoTyper now runs on Windows, macOS and Linux.** It types your text into any
field one key at a time, at a pace that looks human.

![AutoTyper icon](assets/autotyper-logo.png)

## What's new

- **macOS app** — an `.app` in a DMG (ad-hoc signed, not notarized), with separate downloads
  for Apple Silicon and Intel Macs.
- **Linux app** — a single AppImage for x86_64 and ARM64.
- Real keystrokes on every system: Win32 `SendInput` on Windows, X11 `XTEST` on
  Linux, Quartz `CGEvent` on macOS.
- Settings are saved in each system's usual folder.
- Windows is unchanged.

## Download

| System | File |
| --- | --- |
| Windows (64-bit) | `AutoTyper.exe` or `AutoTyper-windows-x64.zip` |
| macOS, Apple Silicon | `AutoTyper-1.1.0-macos-arm64.dmg` |
| macOS, Intel | `AutoTyper-1.1.0-macos-x64.dmg` |
| Linux, x86_64 | `AutoTyper-1.1.0-linux-x86_64.AppImage` |
| Linux, ARM64 | `AutoTyper-1.1.0-linux-aarch64.AppImage` |

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
text, set the speed, and press **Go**. `F9` pauses and resumes, `Esc` stops.
If you click another window while typing, AutoTyper pauses so it never types
into the wrong app.

Full documentation: [README.md](https://github.com/jlaportebot/AutoTyper#readme)

## License

MIT
