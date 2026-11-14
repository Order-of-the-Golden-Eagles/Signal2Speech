# Selection contract

This is the shared contract from [#22](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/22). Every input source and every output builds against it. The code is in [`signal2speech/core/`](../../signal2speech/core): pure Python with no g.Pype or Qt imports. The executable spec is [`contracts/selection-scenarios.json`](../../contracts/selection-scenarios.json). If you change a rule, change the scenario file and the code in the same PR.

**Stack:** Python 3.12, [g.Pype](https://gpype.gtec.at) for acquisition, signal processing, and scopes, and PySide6 for the UI. Everything runs in one process with no bridge. g.Pype runs on Windows, macOS, and Linux.

## Vendor facts vs. app decisions

| | What we know | Status |
| --- | --- | --- |
| **Vendor fact** | g.Pype 4.2 `HybridBlack` source: Bluetooth, 8 EEG channels at 250 Hz. It needs no licence and no Unicorn Suite. Our `pyproject.toml` installs `gpype[gui,devices]`, h5py, and scikit-learn. Pair the headset in the OS first. | Documented, not yet run by us |
| **Vendor fact** | `HybridBlack(enable_oscar=True)` turns on OSCAR artifact removal. It adds processing delay. | Documented |
| **Vendor fact** | g.Pype has **no ready-made P300 or SSVEP classifier**. The `Sklearn` node offers LDA or logistic regression, trained offline on `Epochs`, and outputs a class index online. | Documented |
| **Vendor fact** | `Marker` emits stimulus codes into a pipeline, and `Keyboard` emits key events. `Generator` simulates signals with no hardware. `UDPSender` and `LSLSender` stream out. | Documented |
| **Vendor fact** | The g.tec Paradigm Presenter is separately licensed and Windows-only. The MCP visualizer shown at the workshop isn't in the public docs. | Ask the g.tec mentor |
| **Unknown** | P300 accuracy and trials needed for our wearer ([#46](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/46)), the alpha-switch threshold and false triggers ([#47](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/47)), and whether a late decision can cross rounds ([#23](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/23)). | Verify |
| **App decision** | Everything below. | Implemented in `signal2speech/core/` and covered by `pytest` |

## How a selection is decoded

```
HybridBlack(enable_oscar=True) or Generator → Bandpass 1–30 Hz
  ├→ Epochs (on our tiles' flash Markers) → Sklearn LDA → class 1/2 → Choose round   [#46]
  ├→ FFT → BandPower(alpha) → Threshold → rising edge → Confirm (target-1)          [#47]
  └→ TimeSeriesScope, SpectrumScope, EpochAverage → judge evidence view              [#48]
```

- **Choose** uses P300. Our PySide6 tiles flash and send `Marker` codes, and the LDA picks the attended tile.
- **Confirm** uses a deliberate alpha switch: eyes closed for about 2 seconds. Cancel is the keyboard or judge cancel, or a timeout. P300 and the alpha switch are different brain signals, so a leftover P300 can't count as a confirmation.
- **Fallback** if P300 isn't reliable by 8:15: step through the options one at a time and confirm each with the alpha switch.

## Event shape

All input sources produce the same shape:

```json
{"source":"keyboard","roundId":"r1","eventId":"k1","targetId":"target-2"}
```

| Field | Values | Who sets it |
| --- | --- | --- |
| `source` | `keyboard`, `simulated` (g.Pype `Generator` or injected), `recorded` (g.Pype replay), `live-eeg` | The adapter. Label input honestly in logs and the demo. |
| `roundId` | `r1`, `r2`, … | The app issues it, and the adapter stamps it **when the flash sequence starts**, not when the decision arrives. |
| `eventId` | `k1`, `s2`, `rec3`, `e4`, … | The adapter, from one process-wide counter, so it's unique per run even when two adapters share a source (the P300 chooser and the alpha switch both use `live-eeg`). |
| `targetId` | `target-1`, `target-2` | The adapter maps keys or classifier classes onto it (`EegClassMap.default()`: 1 → `target-1`, 2 → `target-2`). |

In Python, this is `SelectionEvent`. Its field names match the JSON so `SelectionEvent.from_dict()` maps 1:1.

## IDs

**Targets** are on-screen tiles. Their meaning changes with each round.

| Round kind | `target-1` | `target-2` |
| --- | --- | --- |
| Choose (OpenOrbit demo, [`demo-round.json`](../../contracts/demo-round.json)) | `show_satellite` | `compare_air_quality` |
| Choose (AI Answering, #27) | `speak_reply` (reply A) | `speak_reply` (reply B) |
| Confirm (always) | `confirm` (alpha switch or key 1) | `cancel` (key 2, Esc, or timeout) |

**Actions** are stable strings in `ActionIds`. Only these three ever reach output:

| Action | Effect after confirmation |
| --- | --- |
| `show_satellite` | Show the June 28 NASA MODIS image and speak its line. |
| `compare_air_quality` | Show the June 26 and June 28 imagery with the county AQI comparison, then speak "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." |
| `speak_reply` | Speak the exact previewed reply. |

## Round rules (`SelectionHandler`)

```mermaid
stateDiagram-v2
    [*] --> Choose: begin_choice_round(choices)
    Choose --> Confirm: valid target → Previewed (no output)
    Confirm --> [*]: confirm → Confirmed → sink.execute once
    Confirm --> [*]: cancel target / cancel() / disconnect() → no output
    Choose --> [*]: cancel() / disconnect()
```

1. The app opens a round with frozen options. Each round gets a new ID.
2. The first valid event **consumes** the round before any UI update or effect runs.
3. In a Choose round, a valid pick only previews. The handler stores the exact text with the action ID and opens a Confirm round.
4. A fresh Confirm sends a `ConfirmedAction` to the sink exactly once and clears the pending choice. The app then calls `begin_choice_round` for the next question.
5. These are rejected without output. The round stays as it was:

| Outcome | Cause |
| --- | --- |
| `RejectedStaleRound` | The `roundId` doesn't match the open round. This includes a late decision from the Choose round. |
| `RejectedDuplicateEvent` | The `eventId` was already accepted. |
| `RejectedRoundConsumed` | The round already accepted an event. |
| `RejectedNoOpenRound` | Nothing is on screen, for example after a confirm, cancel, or disconnect. |
| `RejectedUnknownTarget` / `RejectedUnknownSource` / `RejectedMalformed` | The input doesn't match the contract. |
| `RejectedLiveConfirmDisarmed` | A `live-eeg` Confirm arrived while `live_eeg_confirm_armed` is False (the default). Keyboard can still confirm. #23 decides when to arm it. |

### Sample events

Use these against [`demo-round.json`](../../contracts/demo-round.json):

| File | Event | Result |
| --- | --- | --- |
| [`preview.json`](../../contracts/events/preview.json) | `keyboard`, `r1`, `k1`, `target-2` | `Previewed` "Compare counties". Opens Confirm round `r2`. No output. |
| [`stale.json`](../../contracts/events/stale.json) | `live-eeg`, `r1`, `e7`, `target-1` | `RejectedStaleRound`. A late `r1` decision can't confirm in `r2`. |
| [`confirm-fresh.json`](../../contracts/events/confirm-fresh.json) | `keyboard`, `r2`, `k2`, `target-1` | `Confirmed`. One `compare_air_quality` effect and one spoken line. |

## Plugging in

```python
from signal2speech.core import SelectionHandler, InputAdapter, InputSources, EegClassMap, TargetIds

handler  = SelectionHandler(sink)                     # sink.execute(action), owned by #25
keyboard = InputAdapter(handler, InputSources.KEYBOARD)
eeg      = InputAdapter(handler, InputSources.LIVE_EEG)   # SIMULATED for Generator, RECORDED for replay
classes  = EegClassMap.default()

handler.on_round_opened.append(ui.show_round)         # #24
handler.on_preview.append(ui.show_preview)            # #24: no audio, no map change
handler.on_cleared.append(ui.reset)
handler.on_handled.append(log.write)                  # #41 diagnostics and judge strip

handler.begin_choice_round(demo_choices)
keyboard.select_now(TargetIds.TARGET_2)               # keys 1 and 2
eeg.arm_capture()                                     # when the tiles start flashing for this round
eeg.select_captured(classes.target_for(lda_class))    # from the g.Pype output, on the Qt main thread
```

- **Threading:** g.Pype runs nodes on worker threads, and `SelectionHandler` isn't thread-safe. Emit a Qt signal from your g.Pype sink and call the adapter in the slot. The custom-node API is in g.Pype examples `s7e1` and `s7e2`.

## Tests

```
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

`pytest` runs the scenario file, the sample events, and the adapter checks in under a second, with no headset or g.Pype hardware needed.

## Repo layout and ownership

Each track owns one folder, so parallel PRs don't conflict. Don't edit another track's folder without telling its owner.

| Path | Owner issue | Notes |
| --- | --- | --- |
| `contracts/`, `signal2speech/core/`, `tests/test_contract.py` | #22 | Shared. Changes need a scenario update and a heads-up to every track. |
| `pyproject.toml`, `docs/dev-setup-docs/` | #19 | Environment and launch path |
| `signal2speech/eeg/` | #21, #46, #47, #23 | Pipelines: simulated input (#21), P300 chooser (#46), alpha confirm (#47), live run (#23). Use one file per issue. |
| `signal2speech/evidence/` | #48 | Judge evidence window and record/replay |
| `signal2speech/ui/` | #24 | PySide6 tiles, preview, judge strip, keys 1 and 2 |
| `data/openorbit/` | #29 | MODIS images, AQI rows, `SOURCES.md` |
| `signal2speech/openorbit/` | #30 | Comparison view. Exposes `show_satellite` and `compare_air_quality`. |
| `signal2speech/speech/`, `signal2speech/app.py` | #25 | Sink implementation, audio, and the one integration entry point |
| `signal2speech/ai/` | #27 | Reply suggestions as `speak_reply` choices |

## Dependency order

```mermaid
flowchart LR
    I22["#22 contract ✅"] --> I21["#21 simulated input"]
    I22 --> I24["#24 keyboard preview UI"]
    I22 --> I27["#27 AI reply choices"]
    I22 --> I46["#46 P300 chooser"]
    I22 --> I47["#47 alpha confirm"]
    I29["#29 NASA/EPA data"] -.->|swap in real data| I30["#30 offline view"]
    I21 --> I25["#25 confirm → map + speech"]
    I24 --> I25
    I30 --> I25
    I46 --> I48["#48 evidence view"]
    I25 --> I26["#26 recovery checks"]
    I26 --> I40["#40 pre-headset checkpoint"]
    I46 --> I23["#23 live Unicorn"]
    I47 --> I23
    I40 --> I23
    I23 --> I36["#36 rehearse reveal"]
    I27 --> I28["#28 speak AI reply"]
```

GitHub tracks the solid edges as **Blocked by** relationships. #19 (environment) blocks nothing: each dev follows the launch path on their own machine. #30 starts with placeholder images, so its link to #29 is soft.
