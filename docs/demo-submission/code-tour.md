# Code tour: five minutes from flash to speech (#107)

Judges may ask anyone on the team to walk through the code. This page is that walk, in the order a judge's questions usually come. Each stop has one sentence to say out loud, then the lines to open. The links point at `main` as of `6c273bb` (11/14, 9:00 PM), so line numbers can drift as `main` moves.

**Judging runs on simulation.** There's no headset at the event. The demo command is `python -m signal2speech.app --input simulated --p300`, and the screen labels it Simulated. Say that up front.

**The 30-second picture.** It's one Python process with no bridge. A g.Pype pipeline turns EEG into a decision. An `InputAdapter` turns that decision into a `SelectionEvent`. `SelectionHandler` is the only gate, and `AppSink` is the only thing that changes the map or speaks. Keyboard, simulated, recorded, and live input all go through the same path, and every event is labelled with its source.

## 1. A flash becomes a P300 decision

> "Each tile flash stamps a marker into the EEG stream. We cut the EEG after each marker, score it with a shrinkage LDA, and the tile with the highest score wins."

- **The flash.** [`ui/flash.py:72`](../../signal2speech/ui/flash.py#L72) `FlashScheduler._tick` lights the next tile and calls `on_flash` ([:87](../../signal2speech/ui/flash.py#L87)) in the same event-loop turn as the repaint.
- **The marker.** [`eeg/p300.py:601`](../../signal2speech/eeg/p300.py#L601) `P300Chooser.on_flash` emits the g.Pype `Marker` ([:607](../../signal2speech/eeg/p300.py#L607)): code 1 or 2 per tile, and 101 or 100 during calibration.
- **The pipeline.** [`p300.py:436`](../../signal2speech/eeg/p300.py#L436) `build_pipeline`: 1–30 Hz bandpass, then one `gp.Trigger` per tile cutting −0.1 to 0.7 s around each flash. Each epoch goes to `P300Scorer` ([:77](../../signal2speech/eeg/p300.py#L77)), a `gp.Sklearn` shrinkage LDA on 40 ms bin means. `SequenceAggregator.finish` ([:202](../../signal2speech/eeg/p300.py#L202)) picks the tile with the highest mean score.
- **Into the app.** [`p300.py:539`](../../signal2speech/eeg/p300.py#L539) `_on_decided` runs on the Qt main thread. It maps the class to a tile with `EegClassMap.target_for` ([`core/adapter.py:68`](../../signal2speech/core/adapter.py#L68)) and calls `InputAdapter.select_captured` ([:43](../../signal2speech/core/adapter.py#L43)).
- **Why a late decision can't confirm.** The round ID is stamped **when flashing starts**, not when the decision arrives. `begin_sequence` ([`p300.py:586`](../../signal2speech/eeg/p300.py#L586)) calls `arm_capture` ([`adapter.py:38`](../../signal2speech/core/adapter.py#L38)). A slow decision still carries its old round, and the handler rejects it as stale.

**In the app.** `LiveEegInput` ([`eeg/app_live.py:112`](../../signal2speech/eeg/app_live.py#L112), #103) puts this same pipeline behind the demo tiles. Each tile flash calls `P300Chooser.on_flash` ([:165](../../signal2speech/eeg/app_live.py#L165)), and a short calibration ([`calibrate`, :258](../../signal2speech/eeg/app_live.py#L258)) runs before the first question. With `--input simulated --p300`, the source is a g.Pype Generator with a synthetic P300 and alpha bursts. `--input live` runs the same code on the Unicorn, and eye-closure confirm stays disarmed there unless `--arm-live-confirm` is given.

## 2. The alpha switch confirms

> "To confirm, the wearer closes their eyes for about two seconds. Alpha power over the back of the head jumps, and one closure sends exactly one Confirm."

- **The pipeline.** [`eeg/alpha_confirm.py:248`](../../signal2speech/eeg/alpha_confirm.py#L248): PO7, Oz, and PO8, then a 1 s FFT, alpha band power, and a channel mean into `gp.Threshold`. The threshold starts at 10¹² ([:51](../../signal2speech/eeg/alpha_confirm.py#L51)), so nothing can fire before calibration.
- **Calibration.** [`:166`](../../signal2speech/eeg/alpha_confirm.py#L166) `Calibration.from_samples` refuses unless eyes-closed power is at least 2× eyes-open. The trigger sits at the geometric midpoint.
- **It only listens during a preview.** [`:365`](../../signal2speech/eeg/alpha_confirm.py#L365) `_on_round_opened` arms only when a Confirm round opens.
- **One closure, one event.** [`:381`](../../signal2speech/eeg/alpha_confirm.py#L381) `_on_rising` ignores the edge unless the eyes were open for at least 1 s first ([:389](../../signal2speech/eeg/alpha_confirm.py#L389)). It then disarms and sends a single confirm ([:393](../../signal2speech/eeg/alpha_confirm.py#L393)). A blink, or eyes already closed, can't confirm.

## 3. Nothing is spoken twice, or by mistake

> "Every input goes through one handler that consumes the round before anything happens, so a repeated or late event can never produce output."

- [`core/handler.py:64`](../../signal2speech/core/handler.py#L64) `_apply` rejects, in order: a malformed event, an unknown source, no open round, a stale round ([:71](../../signal2speech/core/handler.py#L71)), an already-seen event ID ([:73](../../signal2speech/core/handler.py#L73)), a consumed round ([:75](../../signal2speech/core/handler.py#L75)), an unknown tile, and a live-EEG confirm while live confirm is disarmed ([:80](../../signal2speech/core/handler.py#L80); off by default at [:28](../../signal2speech/core/handler.py#L28)).
- [`:85`](../../signal2speech/core/handler.py#L85) records the event ID and consumes the round **before** any callback or output.
- A choice only **previews** ([:88](../../signal2speech/core/handler.py#L88)). Confirming needs a fresh round. Then [`:102`](../../signal2speech/core/handler.py#L102) clears the pending choice and calls the sink exactly once. Cancel and disconnect ([`_close`, :116](../../signal2speech/core/handler.py#L116)) produce nothing.
- The rules are executable: `contracts/selection-scenarios.json` runs in `tests/test_contract.py`.

## 4. Where the map and the speech happen

> "There's exactly one output path: the sink changes the map, then speaks the line the wearer previewed, once."

- [`app.py:83`](../../signal2speech/app.py#L83) `AppSink.execute` calls `show_satellite()` ([:87](../../signal2speech/app.py#L87)) or `compare_air_quality()` ([:90](../../signal2speech/app.py#L90)), then `speaker.say` once ([:98](../../signal2speech/app.py#L98)).
- **The map.** [`app.py:128`](../../signal2speech/app.py#L128) `load_view` loads `OpenOrbitView` ([`openorbit/view.py:360`](../../signal2speech/openorbit/view.py#L360), [:364](../../signal2speech/openorbit/view.py#L364)). The AQI changes are computed from EPA's rows, and a test checks them against the spoken line. After a confirm, `_set_reveal` ([`app.py:334`](../../signal2speech/app.py#L334)) hides the tiles and widens the map for 8 s.
- **The voice.** [`speech/speaker.py:80`](../../signal2speech/speech/speaker.py#L80) `OfflineSpeaker.say` tries a bundled clip, then Qt TextToSpeech (the offline OS voice), then pyttsx3. No clip is bundled, so it uses the OS voice, which works with Wi-Fi off.

## 5. CI and the git hooks

> "Every PR runs the tests on Windows, macOS, and Linux, and the hooks stop keys and raw EEG from ever being committed."

- [`.github/workflows/tests.yml:26`](../../.github/workflows/tests.yml#L26): Windows, Ubuntu, and macOS on Python 3.12, plus Ubuntu on 3.13 ([:35](../../.github/workflows/tests.yml#L35)). Pushes to `main` run the full suite everywhere. PRs run the full suite on Windows and Ubuntu 3.12 and skip slow tests elsewhere ([:88](../../.github/workflows/tests.yml#L88)). The smoke step ([:106](../../.github/workflows/tests.yml#L106)) runs `python -m signal2speech.app --smoke`.
- [`.githooks/pre-commit:9`](../../.githooks/pre-commit#L9) blocks raw EEG files, `.env`, and recording folders, and [:23](../../.githooks/pre-commit#L23) blocks key-like strings. [`.githooks/pre-push:27`](../../.githooks/pre-push#L27) runs `pytest` before anything leaves the laptop. Enable them once with `git config core.hooksPath .githooks`.
- `python tools/release_check.py` re-checks a whole revision: secrets in history, raw EEG, the data, and two offline app runs.

## 6. Proof the brain is responding

> "The evidence view shows raw and filtered EEG, OSCAR off versus on, the spectrum, and the averaged response to target versus non-target flashes."

`python -m signal2speech.evidence --source generator|hybridblack|replay DIR [--p300]` ([`evidence/run.py:13`](../../signal2speech/evidence/run.py#L13)). [`evidence/pipeline.py:131`](../../signal2speech/evidence/pipeline.py#L131) builds it: filters, an OSCAR branch for the headset ([:209](../../signal2speech/evidence/pipeline.py#L209)), and target versus non-target `EpochAverage` ([:220](../../signal2speech/evidence/pipeline.py#L220)). The scopes are in [`evidence/app.py:45`](../../signal2speech/evidence/app.py#L45). A replay is labelled Recorded ([`run.py:17`](../../signal2speech/evidence/run.py#L17)).

## 7. Honest input labels

`InputSources` ([`core/contract.py:9`](../../signal2speech/core/contract.py#L9)) defines keyboard, simulated, recorded, and live-eeg. The judge strip always shows the current one ([`ui/window.py:202`](../../signal2speech/ui/window.py#L202)), and so does the window title ([`app.py:268`](../../signal2speech/app.py#L268)). Never call a simulated or recorded run live.

## 8. PiEEG's simulator

> "PiEEG's own simulator streams over Lab Streaming Layer into the same alpha confirm. The keyboard picks, and PiEEG's alpha burst confirms it."

`python -m signal2speech.eeg.pieeg_lsl --demo` (#138), with PiEEG's starter `python python_quickstart.py --sim --lsl` running in another terminal. [`find_local_stream`](../../signal2speech/eeg/pieeg_lsl.py#L60) takes only this laptop's `Octopus16` stream, and [`PiEEGRelay`](../../signal2speech/eeg/pieeg_lsl.py#L77) republishes it under a unique name, so another team's simulator can't drive our app. `gp.LslReceiver` ([:109](../../signal2speech/eeg/pieeg_lsl.py#L109)) feeds it into `AlphaConfirm` ([:180](../../signal2speech/eeg/pieeg_lsl.py#L180)). PiEEG's simulators have no P300, so this path never drives the P300 chooser. It's labelled Simulated (PiEEG). The setup is in [pieeg.md](../eeg-hardware/pieeg.md).

## The three hardest judge questions

From [judge-qa.md](judge-qa.md). Answer only with what's been measured.

1. **"How accurate is it?"** On simulated EEG, the P300 LDA cross-validates around 95%, and the guided run went 3/3 with 0 false confirms. **There's no headset at this event, so live accuracy isn't measured.** Say exactly that.
2. **"How do I know the brain is actually responding?"** Open the evidence view (section 6): the averaged target versus non-target response, and alpha power jumping when the eyes close. Say whether the run is live, recorded, or simulated. The strip and the banner show it.
3. **"Where's the stimulus presentation, and is the timing good enough?"** It's our own PySide6 tiles (section 1), with a g.Pype marker on the frame each tile lights. The flash-timing tool from #77 measures marker-to-frame jitter. The app's own tiles send these markers through `LiveEegInput` (section 1).
