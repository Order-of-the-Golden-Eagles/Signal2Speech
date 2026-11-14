# Pre-flight for the 8:15 PM headset slot (#13, #23)

Goal for the slot: calibrate one wearer, get two deliberate EEG choices, and leave with a **Recorded** backup. The slot is short, so do everything below that doesn't need the headset **before 8:15**.

## By 8:00 PM, without the headset

- [ ] Judging laptop on mains power. Sleep, notifications and Windows Update paused.
- [ ] Repo at the frozen judging commit: `git rev-parse --short HEAD` = `________`.
- [ ] `.venv` active. `pytest -q` is green. Write the summary line here: `________`.
- [ ] `python -m signal2speech.app --input keyboard` runs both options plus cancel, with audio on.
- [ ] `python -m signal2speech.evidence --source generator --seconds 60` shows a separated target average (Simulated).
- [ ] `recordings/` exists and is gitignored: `git check-ignore recordings/x` prints the path.
- [ ] Bluetooth on. Unicorn dongle or pairing ready. Headset charged, with the charger at the table.
- [ ] Electrode gel or water, towel, comb, and a mirror for the wearer.
- [ ] Phone stopwatch and this checklist printed or on a second screen.
- [ ] Screen recorder ready (OBS or the OS recorder) at 1920×1080 with system audio, for the backup take.
- [ ] Quiet seat facing the screen, with the room lights steady (no flicker behind the screen).
- [ ] Questions for the g.tec mentor ready: MCP visualizer access, and whether one headset can stream to two apps at once.

## 8:15 PM: headset on (target 20 minutes)

| Min | Step | Command or action | Pass |
| --- | --- | --- | --- |
| 0–5 | Fit and pair | Put the headset on. Wet or gel the electrodes. Pair over Bluetooth. | ☐ |
| 5–8 | Signal check | `python -m signal2speech.evidence --source hybridblack --oscar on`. Look for 8 live traces, no railed channels, and blinks visible with OSCAR off but reduced with OSCAR on. | ☐ |
| 8–12 | Record the backup | Close that window, then run `python -m signal2speech.evidence --source hybridblack --record`. The wearer blinks 5 times, then does 3 cycles of 10 s eyes open and 10 s eyes closed. About 2 minutes. This is the **Recorded** backup for OSCAR and alpha. It is **not** P300 evidence: the built-in flasher sends markers with no visible flash. | ☐ |
| 12–16 | P300 calibrate and select | Close the evidence view so the headset is free. Run `python -m signal2speech.eeg.p300 --source hybridblack` (10 calibration sequences, then 6 online picks). Write down the online hits out of 6. | ☐ |
| 16–18 | Alpha calibrate | `python -m signal2speech.eeg.alpha_confirm --source hybrid-black` (note the hyphen; p300 and evidence use `hybridblack`). 10 s eyes open, then 10 s eyes closed. Optional: add `--demo` for keyboard preview then alpha confirm. Live confirm inside the app is still blocked on #23. Write down whether it refused or passed, and any false triggers in 30 s of eyes-open rest. | ☐ |
| 18–20 | Replay check | `python -m signal2speech.evidence --source replay recordings/evidence_<timestamp>`. Banner says RECORDED. Blinks are reduced with OSCAR on, and the alpha peak rises during eyes closed. | ☐ |

The P300 and evidence commands above haven't been run on a real headset yet. If a command fails, write down the exact error and move on to the next step. Don't spend the slot debugging.

## Write down (post results in #23, not in git)

- Wearer: ________ · Time: ________ · Channels OK: __ / 8
- P300 online hits: __ / 6 · Flashes per tile: __ · Did OSCAR help or hurt?
- Alpha confirm: passed / refused / not tested · False triggers: __
- Recording folder name: `recordings/evidence_________` (stays local and gitignored)
- Live end-to-end in the app: **not possible on `main` until #23**. Note it if it lands before the slot.

## After the slot

- [ ] Recording copied to a second local drive. **Never commit it, never upload it.**
- [ ] Results posted in #23. Then MEMORY.md and the EEG doc get updated by their owners.
- [ ] Decide which demo track to use (live or keyboard) and tell the Narrator which label lines to use.
