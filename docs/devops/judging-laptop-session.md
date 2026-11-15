# Judging laptop session (#39, #4, #42)

One sitting, about 40 minutes, on the judging laptop (MagicJester2764's). It produces the evidence to close **#39** (clean offline launch) and **#4** (simulated input gives one map change and one audible line with Wi-Fi off). It also rehearses **#42**'s switch-back and spot-checks **#5** and **#48**. The live headset checks (#23) are a separate session.

Commands are for Windows PowerShell. Run them from the repo folder unless a step says otherwise. Note the result of each step as you go, then paste the comments in [Part C](#part-c-wi-fi-on-record-the-results).

**Bring:** charger, the demo speakers or headphones, and about 3 GB of free disk. Have `.env` ready only if you want to try the AI with a real key.

## Part A: Wi-Fi on (about 15 minutes)

| # | Do | Expect |
| --- | --- | --- |
| A1 | `git switch main` and `git pull`. Then, in a Python 3.12 venv: `.venv\Scripts\activate` and `pip install -r requirements-lock.txt`. Add `--resume-retries 30 --timeout 120` if the Wi-Fi is flaky. | Installs with no errors |
| A2 | `python tools/release_check.py` | Every check PASS. The commit-email WARN is known (#33). |
| A3 | `python -m signal2speech.app --smoke=judging` | Exit 0, with no FAIL and no SKIP. Stop here if it fails, and post the output in #41. |
| A4 | `git rev-parse --short HEAD` | Write the hash down. This is the **session commit**. |
| A5 | **Fallback copy for #42.** Use `eecc31a`, the known-good build, until `judging-draft` exists: `git worktree add ..\Signal2Speech-fallback eecc31a`, then `cd ..\Signal2Speech-fallback`, `py -3.12 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements-lock.txt`, `cd ..\Signal2Speech` | A second folder with its own working Python |

## Part B: Wi-Fi off (about 20 minutes)

Turn Wi-Fi **off** (and unplug Ethernet). Activate the main folder's `.venv`. Set the volume to what the judges will hear.

| # | Do | Expect | Closes |
| --- | --- | --- | --- |
| B1 | `python tools/demo_launcher.py --input keyboard` (fullscreen, and it restarts the app if it crashes; F1 shows the keys, F11 leaves fullscreen). Press **2**, then **1**. | The county comparison fills most of the window for 8 s, and **one** line is spoken: "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." | #39 |
| B2 | When the next question appears, press **1**, then **1**. | The June 28 satellite view appears, and **one** line is spoken | #39 |
| B3 | Press **2** (preview), then **2** (cancel). Then press **2**, then **D** (disconnect during preview). | Nothing appears and nothing is spoken, both times. The transcript shows `cleared (cancel)` and `cleared (disconnect)`. | #39, #26 |
| B4 | Close the app. Run `python -m signal2speech.app --input simulated --sim 2,1`. | The bottom strip says **Input: Simulated** and **Connection: g.Pype Generator stream**. If it says "scripted", g.Pype didn't load: stop and note it. The tiles flash, then the preview shows, then the comparison appears with **one** spoken line. | **#4** |
| B5 | Close it. Run `python -m signal2speech.app --input simulated --sim 2,2`. | Preview, then cancel. Nothing appears and nothing is spoken. | #4 |
| B6 | `python -m signal2speech.ai --question "Are you comfortable?"` | Without a key: tiles labelled **Replies: Stub**. With a key in `.env`: **Replies: Saved phrases · offline…** within about 9 s. Press **1**, then **1**: the reply is spoken **once**. | #5 (offline fallback) |
| B7 | `python -m signal2speech.evidence --source generator --seconds 20` | The scopes open and move. The banner says **Simulated**. | #48 |
| B8 | **Switch-back rehearsal.** Start a timer, close everything, then: `cd ..\Signal2Speech-fallback`, `.venv\Scripts\activate`, `python -m signal2speech.app --input keyboard`, and press **2**, then **1**. Stop the timer at the spoken line. Then `cd ..\Signal2Speech`. | One reveal and one spoken line from the fallback build, **under 60 s** | #42 |
| B9 | Stand where the judges will be. Run B1 once more. | The line is clearly audible, and the AQI table is readable from there | #39 |

Turn Wi-Fi back **on**.

## Part C: Wi-Fi on, record the results

Paste each comment into its issue and fill in the blanks. Keep keyboard, simulated, and live EEG results separate. Nothing here is live EEG.

**#39**
```
Judging laptop Wi-Fi-off run: PASS / FAIL — <date, time ET>, commit <session commit>.
- release_check: <PASS / notes>. smoke=judging: <exit code>.
- Keyboard 2,1 → comparison + one spoken line: <yes/no>. 1,1 → satellite + one line: <yes/no>.
- Cancel and disconnect during preview → nothing: <yes/no>.
- Audible and readable from the judge position: <yes/no>.
```

**#4**
```
Simulated input with Wi-Fi off on the judging laptop: PASS / FAIL — commit <session commit>.
- Connection label: "<text>" (should be g.Pype Generator stream).
- --sim 2,1 → one map change + one audible line: <yes/no>. --sim 2,2 → nothing: <yes/no>.
```

**#42**
```
Switch-back rehearsal on the judging laptop: <seconds> s from closing the app to the spoken line, fallback build eecc31a (worktree + its own venv, Wi-Fi off).
```

**#5** and **#48**: add one line each only if something looked wrong.

### Then update the board

Follow [CLAUDE.md](../../CLAUDE.md#project-board-after-every-merge):
- **#39 passes:** close it as completed, and set Done.
- **#4 passes:** close it as completed, and set Done. Its sub-issues are already closed.
- **#42:** stays In Progress until `judging-draft` and `judging-final` are tagged, as described in [judging-build.md](judging-build.md#freeze-and-rollback-42).

## If a step fails

| Symptom | Do |
| --- | --- |
| A3 smoke has a FAIL | Stop. Post the output in #41 and don't tag anything. |
| B4 says "scripted, no g.Pype" | g.Pype didn't import in this venv. Run `pip install -r requirements-lock.txt` again with Wi-Fi on, and post the error in #19. Don't count B4 as a #4 pass. |
| No sound in B1 | Check the Windows output device and the installed voices (Settings → Time & language → Speech). The transcript still shows `speech engine: Speaking` if the app tried. |
| A line is spoken twice, or the map changes twice | That's a real bug. Copy the transcript into #26 and don't freeze. |
| B8 takes over 60 s | Note where the time went (app start, venv activation) in #42. |
