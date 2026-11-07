# AutoTyper v1.3.0

**Paste formatted text and AutoTyper keeps the bold, italic, underline and spacing.**

![AutoTyper icon](assets/autotyper-logo.png)

## What's new

- **Formatting.** Copy text from Google Docs, Word, LibreOffice, Pages or a web
  page and paste it into AutoTyper: **bold**, *italic* and underline are kept,
  shown in the editor and typed with the target app's own shortcuts
  (`Ctrl+B`/`I`/`U`, `⌘B`/`I`/`U` on macOS).
  - Paragraphs, blank lines, tabs and spacing come through exactly.
  - Lists are typed as `•` bullets and `1.` numbers.
  - Select text in the editor and press `Ctrl+B`/`I`/`U` to format it yourself.
  - **Formatting on / off** switches to plain text for plain-text boxes.
  - Formatting is saved with your text between sessions.
  - Typos still work with formatting, and a fix never erases back across a
    style change.
- **Open** also loads saved web pages (`.html`) with their formatting.
- Fonts, sizes and colours are not typed: no shortcut sets them in every app,
  so choose them in your document before pressing **Go**.

Everything from v1.2.0 (realistic typos fixed with real backspaces) is still
here.

## Download

| System | File |
| --- | --- |
| Windows (64-bit) | `AutoTyper.exe` or `AutoTyper-windows-x64.zip` |
| macOS, Apple Silicon | `AutoTyper-1.3.0-macos-arm64.dmg` |
| macOS, Intel | `AutoTyper-1.3.0-macos-x64.dmg` |
| Linux, x86_64 | `AutoTyper-1.3.0-linux-x86_64.AppImage` |
| Linux, ARM64 | `AutoTyper-1.3.0-linux-aarch64.AppImage` |

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
