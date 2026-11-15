# Two-minute stage script with roles (#36)

The table demo, second by second. It follows one judge question from the question card to the spoken answer, then shows the brain evidence behind it.

## Judging day, 11/15: no headset (use this, not the tracks below)

**What changed.** The g.tec Unicorn was lost in transit, and the PiEEG board we borrowed gave no usable EEG on two people ([findings](../eeg-hardware/README.md#pieeg-octopus-16-on-real-people-no-usable-eeg-2026-11-15)). Nobody wears a headset at the table. The brain signal we show is **g.tec's recorded human EEG**, driving the app through the same pipeline a live headset would use. Everything below this section was written for a live wearer and is kept for reference.

**The one sentence.** "Our headset was lost, so we run g.tec's real brain recordings through the exact pipeline a live headset would use. Plug in a Unicorn and the same code runs."

### Start it before the judge arrives

Setup takes about 70 seconds and is silent, so do it between judges, never in front of one.

```
python -m signal2speech.app --input recorded --sim 2,1,1,1,2,1,1,1 --fullscreen
```

- `--sim` is the script: pick tile 2 and confirm, pick tile 1 and confirm, and so on. Eight numbers give four exchanges, about 15 seconds each.
- Wait for `Calibration done: P300 ready · eye-closure confirm ready`, then the first question appears.
- **It opens with the two cards alone,** which then settle on the left while the map panel fades in. `--no-intro` skips that.
- **It runs as a walkthrough.** The card the wearer would be looking at is outlined and marked "The wearer looks here", and three guidance lines are spoken during setup, starting with "This is a walkthrough on recorded brain data. Nobody is wearing a headset." Decide before the judge arrives whether you want them: `--no-gaze-mark` and `--no-narration` turn them off. With the mark on, say out loud that it shows the scripted attention, not the classifier's answer.
- **Don't touch keys 1 or 2 while the tiles flash.** A key press picks at once and beats the recorded data to it.
- After the script runs out, keys take over (1 or 2 to choose, hold 1 to confirm, hold 2 to cancel). Restart the app for the next judge.
- One launch has enough recorded responses for 20 choices before any is replayed. Restarting resets that.
- On the judging laptop the dataset is found by itself. Elsewhere add `--recording path/to/S4.mat`.

**If recorded mode won't start** (dataset missing, a crash): `python -m signal2speech.app --input simulated --p300 --sim 2,1 --fullscreen`, and say "simulated" instead of "recorded" everywhere below. **If that fails too:** `--input keyboard`, and say so.

### Two minutes, second by second

| Time | Says | On screen |
| --- | --- | --- |
| **0:00–0:10** | "Signal2Speech is a voice for someone who can't speak or move. They pick a reply by looking at it, confirm by closing their eyes, and the app says it for them." | Two tiles: **Show the satellite view** and **Compare counties** |
| **0:10–0:25** | "Our headset was lost in transit. So the brain data you're about to see is real human EEG that g.tec recorded on their own amplifier. Look at the strip: it says Recorded, re-mapped to our tiles." Point at the strip. | Strip: `Choose: Recorded (g.tec dataset, re-mapped to our tiles) · Confirm: Simulated` |
| **0:25–0:40** | "Each time a tile flashes, we play in one real brain response. If it's the tile the user wants, it's a response recorded while that person was paying attention. Our classifier isn't told which is which. It has to work it out." | Tiles flash for about 5 seconds, then one is picked |
| **0:40–0:50** | "It picked Compare counties. That's only a preview. Nothing has been said yet, so a wrong pick costs nothing." | *Say this?* with the exact words and the confirm ring |
| **0:50–1:00** | "Confirming uses a second, different signal: closing your eyes for two seconds. Here that part is simulated, and the screen says so." | Ring fills, map appears |
| **1:00–1:20** | Let the app speak. Then: "One confirm, one map change, one spoken line. NASA satellite imagery and EPA air-quality data, and the numbers in the sentence come from the data." | Before-and-after smoke images, county table |
| **1:20–1:45** | "How do we know the classifier is really reading brain signals? On g.tec's recordings it picks the right tile 94 % of the time from a single flash and 100 % from five, tested on data it never saw. Scramble the labels and it drops to chance." | Optional: the chart in `docs/eeg-hardware/README.md`, or `python -m signal2speech.evidence --source dataset <S4.mat>` |
| **1:45–2:00** | "What's real: the EEG, the g.Pype pipeline, the classifier. What's scripted: which tile counts as looked-at, because that person was using g.tec's speller, not our app. Questions?" | |

### Say it straight

- **Never say "live"** about anything at the table. Say "recorded" for the brain data and "simulated" for the eye closure.
- **Never say "the user chose".** Say "the classifier picked", because the intent is scripted.
- If the classifier picks the wrong tile, say so: "That's a real miss. It works from noisy single responses." Then hold 2 to cancel and let it go again. A miss is honest evidence the data isn't faked.
- If a judge asks to try it: they can use the keys. They can't drive it with their brain, and we say that.

---

## The original plan, for a live wearer (reference only)

**Status on 2026-11-14 (`main` after #47 and #37 merged)**

| Piece | Status | What to run today |
| --- | --- | --- |
| Tiles, preview, confirm, cancel, judge strip (#24) | Works with keyboard and simulated input | `python -m signal2speech.app --input keyboard` |
| P300 chooser (#46) | Works on synthetic data. **Live headset not run yet.** | `python -m signal2speech.eeg.p300 --source hybridblack` (standalone, not inside the app yet) |
| Alpha-switch confirm (#47) | **Merged** (PR #58). Works standalone on Generator (Simulated); **live headset not run yet.** Live confirm inside the app stays disarmed until #23. | `python -m signal2speech.eeg.alpha_confirm --source hybrid-black` (standalone; `--demo` for keyboard preview then alpha confirm). In the app, confirm with key 1 and say so. |
| Live EEG inside the app (#23, #103) | **Runs, not yet on a wearer.** `--input live` calibrates on the app's tiles (10 P300 sequences, then 10 s eyes open and 10 s eyes closed), then the P300 chooser picks and key 1 confirms. Eye-closure confirm stays off until #23 (`--arm-live-confirm`). | Rehearse with `--input simulated --p300`. If the headset fails, use `--input keyboard` or `--input simulated` |
| OpenOrbit map (#30) | **On `main`** (#65). A confirm reveals June 26 vs. June 28 with the county AQI. The map takes most of the window and stays up for 8 s (#81). | `python -m signal2speech.app --input keyboard --fullscreen` |
| Operator aids (#94, #96) | Fits 1280×720. `--fullscreen` with F11 to toggle, F1 for a key-help overlay, and "No answer cancels in N s" under the preview (#26's timeout). | F1 at the table if anyone forgets a key |
| Evidence view (#48) | Works with Generator (Simulated) and replay (Recorded). **Live OSCAR on real EEG not checked.** | `python -m signal2speech.evidence --source generator` |
| **Averaged P300 from a real wearer** | **Blocked.** On `hybridblack`, the evidence view's built-in `Flasher` sends flash markers with **no visible flash**, so its target average can't show a real P300. The P300 chooser has real flashes but doesn't feed the evidence scopes or record yet. This needs the #46 ↔ #48 seam: `build_evidence_graph(front_end=p300_front_end)` with the chooser's tiles emitting on `graph.marker`, run with `--no-flasher`. | Live: show OSCAR off/on and the eyes-closed alpha peak. P300 average: Simulated, or Recorded once the seam exists. |

So the run of show has two tracks. **Track L (live)** is the target once #23 lands (#30 and #47 are merged; the alpha switch only runs standalone until #23). **Track K (keyboard today)** is what the `main` branch can do right now. Each beat says which one you're on. Never call Track K "live". The judge strip's `Input:` label must match what you say out loud.

## Roles

Assign the roles at the first rehearsal and write the names here.

| Role | Who | Job |
| --- | --- | --- |
| **N, Narrator** | _____ | Talks to the judge. Owns the clock. Says every input label out loud. |
| **W, Wearer** | _____ | Wears the Unicorn Hybrid Black. Looks at the tiles. Closes their eyes to confirm. Doesn't talk during the flashes. |
| **O, Operator** | _____ | Drives the laptop: launches, switches windows, presses keys. Has the fallback commands typed and ready. |
| **S, Spotter** | _____ | Holds the question card and the stopwatch. Watches the judge strip and the Connection label. Calls "fallback" if the headset drops. |

## Before the judge arrives (not on the clock)

- O: app started with `python tools/demo_launcher.py --input <keyboard|simulated|live>`, so a crash restarts it in about 1 s. The Choose round is open, the evidence window is behind it, and both labels are visible.
- S: question card in hand, stopwatch at 0:00.
- W: seated, headset on, eyes on the screen, impedance or signal quality checked in the evidence view.
- If the headset isn't ready in 30 seconds, switch to Track K before the judge sits down. Don't debug in front of the judge.
- O: the build is the frozen `judging-final` (or `judging-draft`), `python -m signal2speech.app --smoke=judging` passed, Wi-Fi is off, and the fallback folder from [judging-build.md](../devops/judging-build.md#offline-safe-fallback-copy) is ready.

## Second by second

| Time | Who | Says | Does |
| --- | --- | --- | --- |
| **0:00–0:08** | N | "Signal2Speech lets someone who can't speak or type answer a question with their brain signals. The app suggests the words. The wearer decides what gets said." | S hands the judge the question card. |
| **0:08–0:15** | Judge, N | Judge reads: *"Which county's AQI rose more when wildfire smoke reached southeast Michigan?"* N: "Two answers are on screen." | O points at the two tiles: **Show the satellite view** and **Compare counties**. |
| **0:15–0:20** | N | "Bottom strip: the input source, the round, and the connection. Right now it says `Input: ____`." Read the real label: Live EEG, Simulated or Keyboard. | S checks the label matches. |
| **0:20–0:35** | W, N | N: "W is looking at **Compare counties**. Each flash makes a small brain response about 300 milliseconds later, called the P300. g.Pype cuts out each flash and an LDA classifier picks the tile." | **Track L:** the app tiles flash 10 rounds per tile at 100 ms on and 75 ms off (175 ms SOA), about 3.5 s per sequence. *That app timing has not been validated with the classifier:* the P300 chooser and its synthetic accuracy use 100 ms on, 250 ms SOA, 5 flashes per tile, about 2.5 s per sequence. W silently counts the flashes on the target tile. **Track K:** O presses `2`. N says "I'm pressing key 2 for the wearer." |
| **0:35–0:42** | N | "That's only a preview. *Say this?* Nothing has been spoken or shown yet. One wrong pick costs nothing." | Preview card shows the exact text: "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." |
| **0:42–0:55** | W, N | N: "To confirm, W closes their eyes for two seconds. That raises the alpha rhythm, which is a different signal from the P300, so a leftover flash response can't confirm by accident." | **Track L (#47 merged; in-app needs #23):** W closes eyes for about 2 s. Confirm lands about 1.2–1.5 s after the eyes close (measured on simulated data). **Track K:** O holds `1` for 2 s. N: "Confirm by keyboard. Live alpha confirm is waiting on calibration." |
| **0:55–1:15** | App, N | App speaks the line. N: "One confirm gives exactly one map action and one spoken line. Washtenaw rose 186 points, Wayne 168. NASA imagery shows the smoke from orbit. EPA data measures air at ground level." | The map reveal fills most of the window for 8 s: June 26 vs. June 28 and the county AQI table (#30, #81). |
| **1:15–1:20** | O | N: "Here's the proof the brain was responding." | O switches to the g.Pype evidence window. |
| **1:20–1:45** | N | "Top left is raw EEG with every flash marked. Next to it is the filtered signal, OSCAR off and then OSCAR on: that's g.tec's artifact removal cleaning out blinks and movement. The bottom panel averages every target flash against every non-target flash. See the bump around 300 ms on the target trace? That's the P300. The banner says whether this is live, recorded or simulated: right now it says `____`." | O hovers the cursor at about 300 ms on the averaged plot. **Only call the bump a real P300 when the banner says LIVE EEG or RECORDED *and* the markers came from the chooser's visible tiles** (blocked today, see the status table). Otherwise say: "On g.Pype's simulator, this is what the average looks like." **Live alternative that works today:** with the evidence view on `hybridblack`, W blinks (OSCAR off shows the spike, OSCAR on removes it), then closes their eyes for 3 s and the 10 Hz alpha peak rises in the spectrum. N: "That's W's own alpha rhythm, live. It's the same signal the eyes-closed confirm uses." |
| **1:45–2:00** | N | "Every input, whether that's keyboard, simulator, P300, alpha switch or any g.tec device through a g.Pype pipeline, speaks one selection contract. So it's a platform, not a one-off. It runs on Windows, macOS and Linux, and CI tests all three. Questions?" | S stops the clock and notes the time. |

**Spare seconds:** if the judge is engaged and time allows, show cancel. Pick a tile, then at *Say this?* the wearer or O presses `2` or `Esc`. N: "Cancel. Nothing is spoken." That proves preview has no side effects. **Between judges:** press `R` for a fresh first question. Nothing is said, and the map goes blank. Not during a headset calibration: R waits for it.

## If a beat fails

Switch, say which input you're on now, and keep the clock running. Don't retry live more than once in front of the judge.

| Beat | If it fails | Switch to | Say |
| --- | --- | --- | --- |
| Evidence window (1:15) | No signal, or the headset dropped | `python -m signal2speech.evidence --source replay recordings/evidence_<timestamp>` (the banner says **Recorded**) | "This is a recording of our headset session, replayed through the same pipeline." |
| App input (0:15) | Live isn't ready or is noisy | `python -m signal2speech.app --input simulated --sim 2,1` (**Simulated**) or `--input keyboard` | The matching spoken label line below |
| P300 choose (0:20) | Wrong tile, or no decision | Key **2** (Keyboard), or the step-through fallback: options one at a time, each confirmed with the alpha switch | "I'm pressing the key for the wearer." |
| Alpha confirm (0:42) | No confirm within the countdown | Key **1** (Keyboard). If the preview times out, nothing is spoken, so pick again. | "Confirm by keyboard." |
| Map or speech (0:55) | No sound, or the map doesn't change | Point at the transcript (`OUTPUT map` / `OUTPUT speak`). Check the volume after the demo. | "The transcript shows the one confirmed action." |
| The whole build | It crashes, or the smoke check fails on the day | The fallback folder from [judging-build.md](../devops/judging-build.md#offline-safe-fallback-copy) | "Fallback build." |

## Spoken label lines (use the exact words)

- Keyboard: "I'm pressing the key for the wearer. This is keyboard input."
- Simulated: "This is g.Pype's simulated signal generator, not a real brain."
- Recorded: "This is a recording of our real headset session from earlier tonight, replayed through the same g.Pype pipeline."
- Live: "This is live EEG from the headset, right now." Only say this when the judge strip reads `Live EEG`.
