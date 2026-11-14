# Two-minute live run of show (#36)

The table demo, second by second. It follows one judge question from the question card to the spoken answer, then shows the brain evidence behind it.

**Status on 2026-11-14 (commit `4fb717a`, `main`)**

| Piece | Status | What to run today |
| --- | --- | --- |
| Tiles, preview, confirm, cancel, judge strip (#24) | Works with keyboard and simulated input | `python -m signal2speech.app --input keyboard` |
| P300 chooser (#46) | Works on synthetic data. **Live headset not run yet.** | `python -m signal2speech.eeg.p300 --source hybridblack` (standalone, not inside the app yet) |
| Alpha-switch confirm (#47) | **Not on `main`** (PR #58 open). Live confirm stays disarmed until #23. | Confirm with key 1 and say so |
| Live EEG inside the app (#23) | **Blocked.** `--input live` prints "Live EEG is blocked" and exits. | Use `--input keyboard` or `--input simulated` |
| OpenOrbit map (#30) | **Not on `main`** (PR #65 open). The app shows a labelled stand-in panel. | Stand-in panel plus the spoken line |
| Evidence view (#48) | Works with Generator (Simulated) and replay (Recorded). **Live OSCAR on real EEG not checked.** | `python -m signal2speech.evidence --source generator` |
| **Averaged P300 from a real wearer** | **Blocked.** On `hybridblack`, the evidence view's built-in `Flasher` sends flash markers with **no visible flash**, so its target average can't show a real P300. The P300 chooser has real flashes but doesn't feed the evidence scopes or record yet. This needs the #46 ↔ #48 seam: `build_evidence_graph(front_end=p300_front_end)` with the chooser's tiles emitting on `graph.marker`, run with `--no-flasher`. | Live: show OSCAR off/on and the eyes-closed alpha peak. P300 average: Simulated, or Recorded once the seam exists. |

So the run of show has two tracks. **Track L (live)** is the target once #23, #47 and #30 land. **Track K (keyboard today)** is what the `main` branch can do right now. Each beat says which one you're on. Never call Track K "live". The judge strip's `Input:` label must match what you say out loud.

## Roles

Assign the roles at the first rehearsal and write the names here.

| Role | Who | Job |
| --- | --- | --- |
| **N, Narrator** | _____ | Talks to the judge. Owns the clock. Says every input label out loud. |
| **W, Wearer** | _____ | Wears the Unicorn Hybrid Black. Looks at the tiles. Closes their eyes to confirm. Doesn't talk during the flashes. |
| **O, Operator** | _____ | Drives the laptop: launches, switches windows, presses keys. Has the fallback commands typed and ready. |
| **S, Spotter** | _____ | Holds the question card and the stopwatch. Watches the judge strip and the Connection label. Calls "fallback" if the headset drops. |

## Before the judge arrives (not on the clock)

- O: app window open on the Choose round, evidence window open behind it, both labels visible.
- S: question card in hand, stopwatch at 0:00.
- W: seated, headset on, eyes on the screen, impedance or signal quality checked in the evidence view.
- If the headset isn't ready in 30 seconds, switch to Track K before the judge sits down. Don't debug in front of the judge.

## Second by second

| Time | Who | Says | Does |
| --- | --- | --- | --- |
| **0:00–0:08** | N | "Signal2Speech lets someone who can't speak or type answer a question with their brain signals. The app suggests the words. The wearer decides what gets said." | S hands the judge the question card. |
| **0:08–0:15** | Judge, N | Judge reads: *"Which county's AQI rose more when wildfire smoke reached southeast Michigan?"* N: "Two answers are on screen." | O points at the two tiles: **Show the satellite view** and **Compare counties**. |
| **0:15–0:20** | N | "Bottom strip: the input source, the round, and the connection. Right now it says `Input: ____`." Read the real label: Live EEG, Simulated or Keyboard. | S checks the label matches. |
| **0:20–0:35** | W, N | N: "W is looking at **Compare counties**. Each flash makes a small brain response about 300 milliseconds later, called the P300. g.Pype cuts out each flash and an LDA classifier picks the tile." | **Track L:** tiles flash, 10 rounds per tile at 100 ms on and 75 ms off, about 3.5 s per sequence. W silently counts the flashes on the target tile. **Track K:** O presses `2`. N says "I'm pressing key 2 for the wearer." |
| **0:35–0:42** | N | "That's only a preview. *Say this?* Nothing has been spoken or shown yet. One wrong pick costs nothing." | Preview card shows the exact text: "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." |
| **0:42–0:55** | W, N | N: "To confirm, W closes their eyes for two seconds. That raises the alpha rhythm, which is a different signal from the P300, so a leftover flash response can't confirm by accident." | **Track L (needs #47 and #23):** W closes eyes for about 2 s. Confirm lands about 1.2–1.5 s after the eyes close (measured on simulated data). **Track K:** O presses `1`. N: "Confirm by keyboard. Live alpha confirm is waiting on calibration." |
| **0:55–1:15** | App, N | App speaks the line. N: "One confirm gives exactly one map action and one spoken line. Washtenaw rose 186 points, Wayne 168. NASA imagery shows the smoke from orbit. EPA data measures air at ground level." | Map switches to June 28 (**needs #30**; until then the stand-in panel names the `compare_air_quality` action). |
| **1:15–1:20** | O | N: "Here's the proof the brain was responding." | O switches to the g.Pype evidence window. |
| **1:20–1:45** | N | "Top left is raw EEG with every flash marked. Next to it is the filtered signal, OSCAR off and then OSCAR on: that's g.tec's artifact removal cleaning out blinks and movement. The bottom panel averages every target flash against every non-target flash. See the bump around 300 ms on the target trace? That's the P300. The banner says whether this is live, recorded or simulated: right now it says `____`." | O hovers the cursor at about 300 ms on the averaged plot. **Only call the bump a real P300 when the banner says LIVE EEG or RECORDED *and* the markers came from the chooser's visible tiles** (blocked today, see the status table). Otherwise say: "On g.Pype's simulator, this is what the average looks like." **Live alternative that works today:** with the evidence view on `hybridblack`, W blinks (OSCAR off shows the spike, OSCAR on removes it), then closes their eyes for 3 s and the 10 Hz alpha peak rises in the spectrum. N: "That's W's own alpha rhythm, live. It's the same signal the eyes-closed confirm uses." |
| **1:45–2:00** | N | "Every input, whether that's keyboard, simulator, P300, alpha switch or any g.tec device through a g.Pype pipeline, speaks one selection contract. So it's a platform, not a one-off. It runs on Windows, macOS and Linux, and CI tests all three. Questions?" | S stops the clock and notes the time. |

**Spare seconds:** if the judge is engaged and time allows, show cancel. Pick a tile, then at *Say this?* the wearer or O presses `2` or `Esc`. N: "Cancel. Nothing is spoken." That proves preview has no side effects.

## Spoken label lines (use the exact words)

- Keyboard: "I'm pressing the key for the wearer. This is keyboard input."
- Simulated: "This is g.Pype's simulated signal generator, not a real brain."
- Recorded: "This is a recording of our real headset session from earlier tonight, replayed through the same g.Pype pipeline."
- Live: "This is live EEG from the headset, right now." Only say this when the judge strip reads `Live EEG`.
