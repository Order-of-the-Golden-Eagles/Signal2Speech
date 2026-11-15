# PiEEG's simulator through our pipeline (#138)

PiEEG's starter code can publish simulated EEG over Lab Streaming Layer (LSL). Our g.Pype pipeline reads that stream and uses it for the eye-closure confirm (#47). Everything from this source is labelled **Simulated (PiEEG Octopus 16 simulator)**. Never call it live.

PiEEG Cloud (cloud.pieeg.com) can't be used for this. It runs only in the browser and has no stream out.

## Setup: two terminals

Once, in the team venv:

```
pip install pylsl
```

`pylsl` isn't in `pyproject.toml` yet. Adding it is the environment owner's call (#19). Then download PiEEG's starter `python_quickstart.py` from <https://github.com/pieeg-club/hello_world_octopus_16>. We don't copy PiEEG's code into this repo.

1. **Terminal 1:** `python python_quickstart.py --sim --lsl`. Leave it running. It publishes a stream named `Octopus16`: 16 channels at 250 Hz. Its 10.2 Hz alpha switches between weak and strong every 6 s, like eyes opening and closing.
2. **Terminal 2:**
   - `python -m signal2speech.eeg.pieeg_lsl --check` reads the stream for 12 s and reports its rate and the alpha switching.
   - `python -m signal2speech.eeg.pieeg_lsl --demo` runs a keyboard preview, then PiEEG's next "eyes closed" burst confirms it. The map changes and the line is spoken once.

If the stream isn't running, both commands print these steps and exit with code 3.

## What you should see

```
[Simulated (PiEEG Octopus 16 simulator)] found 'Octopus16' on <this laptop>: 16 ch at 250 Hz
3000 samples in 12 s = 250.0 Hz
alpha/beta per second: 1.0 0.9 1.0 0.7 1.0 9.0 22.5 14.3 20.2 17.5 16.0 8.6
```

```
alpha switch calibrated: ratio 26.2
Previewed: keyboard k1 r1->target-2
waiting for PiEEG's next 'eyes closed' alpha burst to confirm
OUTPUT map: compare_air_quality()  [simulated]
OUTPUT speak: "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."
Confirmed: simulated s2 r2->target-1
```

## How it works

- **Only this laptop's stream.** A venue can have several PiEEG simulators on one network, all named `Octopus16`. `PiEEGRelay` takes the one running on this computer and republishes it as `S2S-PiEEG-<computer name>`, so another team's simulator can't drive our app. `--any-host` turns this off, which isn't recommended at the venue.
- **The real confirm path.** g.Pype's `LslReceiver` reads the relayed stream into the same `AlphaConfirm` pipeline the app uses. The confirm goes through `SelectionHandler` and the sink like any other input.
- **Calibration from the stream itself.** The demo reads 13 s of alpha power and treats the lowest 40% as eyes open and the highest 40% as eyes closed. `AlphaConfirm` still refuses unless closed is at least 2× open.

## Limits (say these to judges)

- **No P300.** None of PiEEG's simulators produce a P300 or take markers. So the choice here is made by keyboard, and the P300 chooser stays on g.Pype's synthetic P300 (`python -m signal2speech.app --input simulated --p300`).
- **Not in the app window or the evidence view yet.** The evidence view is #48's folder. Adding a PiEEG source there is proposed on #138.
- `pieeg-server --mock --lsl` publishes a stream named `PiEEG`, not `Octopus16`. We haven't tried it.
- `tests/test_pieeg_lsl.py` uses a fake stream, not PiEEG's code. It skips when `pylsl` isn't installed, so CI skips it for now.

## Verified

11/14, 9:17 PM, Windows 11, with PiEEG's real starter (read in full before running): 250.0 Hz, an alpha-to-beta ratio near 1 with eyes "open" and 14–23 "closed", calibration ratio 26.2, and one confirm with one spoken line. Not tried on the judging laptop.

PiEEG lists the starter and `pieeg-server` as MIT. Avoid their AGPL packages `pieeg-core` and `pifeat`.
