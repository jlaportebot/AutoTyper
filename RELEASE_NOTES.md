# AutoTyper v1.0.0

**Types your text into any field on Windows — one key at a time, at a pace that
looks human.**

![AutoTyper icon](assets/autotyper-logo.png)

AutoTyper is a small desktop app for Windows. Pick the spot on screen you want
to write into, paste the text you want written, choose how fast it should be
typed, and press **Go**. AutoTyper clicks the spot, focuses it and types the
text character by character with a natural rhythm — variable speed, a pause at
commas, a longer pause at full stops, a beat between sentences.

It is built for writing into anything that monitors how you type: timed
writing platforms, prose trainers, typing tutors, and any app that accepts
real keyboard input.

## Download

Grab **AutoTyper.exe** from this release. It is a single self-contained file —
no Python installation required.

1. Download `AutoTyper-windows-x64.zip` and extract it.
2. Double-click `AutoTyper.exe`.
3. Windows SmartScreen may warn about an unrecognised app — choose
   **More info → Run anyway**.

If you prefer to run from source, clone the repo and use `Start AutoTyper.bat`.
Python 3.8+ is required and there are no third-party dependencies.

## How to use it

**01 · Target** — press **Pick spot**, then click the text box you want to
write into. AutoTyper hides itself while you do this and shows you the target
window's title so you can confirm it. Press `Esc` while picking to cancel.

**02 · Text** — type or paste your text, or press **Open .txt** to load a
file. The counter shows characters, words and a live ETA.

**03 · Speed & timing**

- **Words / minute** — 10 to 200. The base typing speed.
- **Rhythm** — 0% to 60%. How much the delay between keystrokes varies.
  0% is a metronome; 25–40% looks convincingly human.
- **Start delay** — 1 to 10 seconds before AutoTyper clicks the target.

Press **Go**. The window collapses into a small floating control bar, a
countdown runs, and AutoTyper clicks the target and starts typing.

## Controls

| Control | Action |
| --- | --- |
| `F9` | Pause / resume — continues from the exact character. |
| `Esc` | Stop. |
| **Pause** / **Stop** buttons | Same as the keys above. |

If you click another window while typing, AutoTyper pauses itself so it can
never type into the wrong app. On resume it counts down two seconds and brings
your target window back to the front.

## What makes it look human

AutoTyper sends real keystrokes through the Windows `SendInput` API one Unicode
code point at a time — it never pastes. On top of the base speed it adds
randomised inter-key delays, a slight stretch after spaces, short pauses after
commas, longer pauses after full stops, the longest pause after newlines, and
a natural resume that preserves the remaining delay so there is no visible jump.

Unicode (accents, emoji, CJK) and tabs/newlines are handled properly.

Full documentation: [README.md](https://github.com/jlaportebot/AutoTyper#readme)

## License

MIT
