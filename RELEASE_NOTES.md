# AutoTyper v1.2.0

**AutoTyper now makes mistakes, like a person does, and fixes them.**

![AutoTyper icon](assets/autotyper-logo.png)

## What's new

- **Typos and corrections.** Every so often AutoTyper hits the wrong key, keeps
  typing for a few keys, notices, pauses, backspaces over everything since the
  slip and types it correctly — so the finished text is still exactly yours.
  - **Typos** (0–10%) sets roughly how many words in a hundred get a typo. The
    gap between typos is random, so they never fall on a beat.
  - **Catch within** (0–15 keys) sets how late a typo may be noticed. Each typo
    picks its own distance: most are caught quickly, some run on.
  - Realistic slips: a neighbouring QWERTY key (`hrllo`), a doubled letter
    (`helllo`), two swapped letters (`teh`) or a skipped letter (`hllo`).
  - Human timing: a beat to notice the slip, quick repeated backspaces, then a
    short hesitation before the right keys.
- Backspace is sent as a real key press on Windows, macOS and Linux.
- The time estimate includes the time spent fixing typos.
- The "Stopped · N of M characters typed" message counts what is really in the
  field, not keystrokes.
- A damaged `settings.json` value (for example a word where a number belongs)
  falls back to its default instead of stopping the app from opening.

Typos default to **2%** with **Catch within 8 keys**. Set **Typos** to 0% to
type perfectly, as before.

## Download

| System | File |
| --- | --- |
| Windows (64-bit) | `AutoTyper.exe` or `AutoTyper-windows-x64.zip` |
| macOS, Apple Silicon | `AutoTyper-1.2.0-macos-arm64.dmg` |
| macOS, Intel | `AutoTyper-1.2.0-macos-x64.dmg` |
| Linux, x86_64 | `AutoTyper-1.2.0-linux-x86_64.AppImage` |
| Linux, ARM64 | `AutoTyper-1.2.0-linux-aarch64.AppImage` |

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
text, set the speed and how many mistakes to make, and press **Go**. `F9`
pauses and resumes, `Esc` stops. If you click another window while typing,
AutoTyper pauses so it never types into the wrong app.

Full documentation: [README.md](https://github.com/jlaportebot/AutoTyper#readme)

## License

MIT
