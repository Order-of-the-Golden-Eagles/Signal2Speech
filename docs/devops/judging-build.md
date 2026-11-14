# Judging build: runbook and rollback (#39, #42)

Part of [DevOps](README.md). Kept in its own file so it doesn't collide with other DevOps edits.

## Judging laptop runbook (#39)

1. Set up from a clean checkout with steps 1 to 5 of the [launch path](../dev-setup-docs/README.md#python-and-gpype-launch-path-19) (`pip install -r requirements-lock.txt` for the exact versions).
2. Run `python tools/release_check.py`. Every check should pass. See [Security and Privacy](../security-privacy/README.md#release-check-10-35) for what the warnings mean. Then run `python -m signal2speech.app --smoke=judging` (#41). Any FAIL or SKIP stops the freeze.
3. **Turn Wi-Fi off**, then run `python -m signal2speech.app --input keyboard`.
   - Press **2**, then **1**. The county comparison appears and one line is spoken.
   - The map fills most of the window and stays up for 8 seconds, then the next question appears (#81). Press **1**, then **1**. The June 28 satellite view appears and one line is spoken.
   - Press **2** during a preview to cancel. Nothing changes and nothing is spoken.
   - The transcript shows exactly one `OUTPUT map` and one `OUTPUT speak` per confirm.
4. Turn Wi-Fi back on. Post the date, the laptop, the commit (`git rev-parse --short HEAD`), and the result in #39. That commit is the known-good commit.

**Bundled assets (all offline):** `data/openorbit/` (two NASA MODIS images, the EPA AQI rows, marker places, and `SOURCES.md`) and `contracts/demo-round.json`. The spoken lines use the offline Windows voice (WinRT, with Microsoft David, Zira, and Mark installed). A file at `data/openorbit/audio/<action_id>.wav` plays instead if it exists. None is bundled yet.

**Headset prerequisites (live run, #23):** pair the Unicorn Hybrid Black in Windows Bluetooth settings, then follow step 7 of the launch path. Live input in the app stays blocked until #46, #47, and #23 land.

**Verified on 2026-11-14 (dev laptop, Windows 11, 1920×1080 at 125%):**
- `release_check.py` passes.
- With the real OpenOrbit view, the app fits the screen (1536×864 at that scaling).
- With every network call blocked inside Python, keys 2,1 and 1,1 each give one map action and one spoken line.
- #41's asset and view checks pass on `data/openorbit/`.

A real Wi-Fi-off run on the judging laptop is still pending.

## Freeze and rollback (#42)

1. **Midnight draft:** once the runbook passes, tag the commit with `git tag -a judging-draft -m "Midnight draft, runbook passed" <commit>`.
2. **Sunday final:** after the final rehearsal passes, run `git tag -a judging-final -m "Final, runbook passed" <commit>`. Keep `judging-draft`.
3. **Switch back** if the final build breaks: run `git switch --detach judging-draft`, then launch. Run `python tools/release_check.py --quick` if there's time. This only works offline when `requirements-lock.txt` is the same in both tags. Check with `git diff --quiet judging-draft judging-final -- requirements-lock.txt` (exit 0 means same). If they differ, use the fallback copy below, because `pip install` needs Wi-Fi.
4. Push the tags once the team agrees: `git push origin judging-draft judging-final`.
5. Record both commits and the result of the switch-back test in #42.

**Tag names:** `judging-draft` is the issue's `judging-v1`. Use the two names above, so the draft and the final are both obvious.

### Offline-safe fallback copy

Make this at freeze time, **while Wi-Fi is still on**. It's a second folder with its own Python environment, so switching back needs no git and no downloads.

```
git worktree add ../Signal2Speech-fallback judging-draft
cd ../Signal2Speech-fallback
py -3.12 -m venv .venv                 # macOS/Linux: python3.12 -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements-lock.txt
python tools/release_check.py --quick
```

If AI Answering is in the demo, copy `.env` into that folder too. It's gitignored, so the worktree doesn't get it.

**To switch back at the table:** close the app, open a terminal in `Signal2Speech-fallback`, activate its `.venv`, then run `python -m signal2speech.app --input keyboard`. The input label and transcript work the same, so say "fallback build" out loud.

**After the final is tagged:** if the final passes, leave the fallback folder in place until judging ends. Remove it afterwards with `git worktree remove ../Signal2Speech-fallback`.

### Switch-back rehearsals

| When (ET) | Machine | From → to | Lock file | Time | Result |
| --- | --- | --- | --- | --- | --- |
| 11/14 | InYoung-Song's Windows laptop | `aec013f` → `eecc31a` | Same | — | `release_check.py` passes on both; one map change and one spoken line per action |
| 11/14 6:39 PM | Long Le's Mac (macOS 12, no g.Pype) | `main` → `eecc31a` with `git switch` | Same | 3 s to the first reveal | One `compare_air_quality` reveal (keyboard 2, 1) |
| | **Judging laptop** | `judging-final` → `judging-draft` | | | **Still needed** |
