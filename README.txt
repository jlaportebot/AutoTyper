autotyper_  -  types text into any field, one key at a time
==========================================================

SETUP (one time)
1. Install Python from https://www.python.org/downloads/
   During install, tick "Add python.exe to PATH".
2. Unzip this folder anywhere (e.g. Documents\AutoTyper).

USE
1. Double-click "Start AutoTyper.bat".
2. 01 TARGET - click "Pick spot", then click the text box to type into.
3. 02 TEXT   - paste your text, or "Open .txt" to load a file.
4. 03 SPEED  - words per minute, rhythm variation, and start delay.
5. Click "Go". The window shrinks to a small floating bar, counts down,
   clicks your spot and starts typing.

CONTROLS WHILE TYPING
  F9 or Pause button   pause / resume - continues from the exact character
  Esc or Stop button   stop
  Clicking another window auto-pauses, so it never types in the wrong place.
  On resume it counts down 2 seconds and switches back to your window by itself.

TIPS
- Your text and settings are remembered between sessions.
- Don't click inside the target text box while paused - that moves the
  cursor, and typing resumes wherever the cursor is.
- If nothing types into an app running as Administrator, run AutoTyper as
  Administrator too.
- Self-test: open a command prompt in this folder and run
     python test_autotyper.py
