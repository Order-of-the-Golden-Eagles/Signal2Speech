# Judging build: runbook and rollback (#39, #42)

Part of [DevOps](README.md). Kept in its own file so it doesn't collide with other DevOps edits.

## Judging laptop runbook (#39)

1. Set up from a clean checkout with steps 1 to 5 of the [launch path](../dev-setup-docs/README.md#python-and-gpype-launch-path-19) (`pip install -r requirements-lock.txt` for the exact versions).
2. Run `python tools/release_check.py`. Every check should pass. See [Security and Privacy](../security-privacy/README.md#release-check-10-35) for what the warnings mean. Once #41 lands, also run `python -m signal2speech.app --smoke=judging`.
3. **Turn Wi-Fi off**, then run `python -m signal2speech.app --input keyboard`.
   - Press **2**, then **1**. The county comparison appears and one line is spoken.
   - Wait for the next question. Press **1**, then **1**. The June 28 satellite view appears and one line is spoken.
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
3. **Switch back** if the final build breaks: run `git switch --detach judging-draft`, then `python tools/release_check.py`, then launch. If `requirements-lock.txt` differs between the two tags, run `pip install -r requirements-lock.txt` first.
4. Push the tags once the team agrees: `git push origin judging-draft judging-final`.
5. Record both commits and the result of the switch-back test in #42.
