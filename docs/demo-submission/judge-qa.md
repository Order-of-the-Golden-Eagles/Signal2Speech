# Likely judge questions (#13)

Short answers, mapped to g.tec's judging criteria. **Must-haves:** stimulus presentation, biosignal amplifier, real-time signal processing pipelines and algorithms, and a real-time application. **Bonus:** cross-platform support, a production-ready prototype, a platform rather than a product, and a low entry barrier.

Answer in one or two sentences, then stop. If something isn't verified, say so.

## Must-haves

**Where's the stimulus presentation?** *(stimulus presentation)*
Our own PySide6 tiles flash for 100 ms with 75 ms between flashes, 10 times per tile, in the app. The standalone P300 chooser that we calibrate with uses 100 ms flashes at a 250 ms SOA, 5 times per tile; the app timing hasn't been validated with the classifier yet. Every flash sends a g.Pype `Marker`, so each epoch is locked to the flash. We didn't use Paradigm Presenter because it's separately licensed and Windows-only.

**What amplifier?** *(biosignal amplifier)*
The g.tec Unicorn Hybrid Black: 8 EEG channels at 250 Hz, read through g.Pype's `HybridBlack` source with OSCAR on.

**What's the real-time pipeline?** *(real-time processing and algorithms)*
`HybridBlack` with OSCAR, then a 1–30 Hz bandpass, then a `Trigger` per tile from −0.1 to 0.7 s, then a shrinkage LDA on 40 ms bin means, then the highest mean score wins. Confirm is a separate alpha-band power switch: eyes closed for about 2 s.

**How do I know the brain is actually responding?** *(evidence)*
Two ways. Live, close your eyes and the 10 Hz alpha peak jumps in the spectrum, which is the confirm signal. And the evidence view averages target flashes against non-target flashes with g.Pype's `EpochAverage`, so the P300 shows as a bump around 300 ms on the target trace only. *Status: the P300 average is shown on simulated data only. A real-wearer P300 average needs the chooser's visible tiles to drive the evidence markers (the #46 ↔ #48 seam), and that isn't wired yet.*

**What does OSCAR do here?**
It's g.tec's artifact removal for blinks and movement. The evidence view shows the filtered signal with OSCAR off and on, side by side. *Status: OSCAR runs on our Generator data. Its effect on real EEG and on P300 epochs hasn't been measured yet.*

**Is it real time?** *(real-time application)*
Yes. One Python process, with g.Pype on worker threads and Qt on the main thread. A decision reaches the UI through a Qt signal, and one confirm gives exactly one map action and one spoken line, with no network needed.

**How accurate is it?**
On synthetic data, with the chooser's settings (250 ms SOA, 5 flashes per tile): 6 out of 6 online picks, and 95–100% offline. That shows the plumbing works, not that a person can use it. *Live accuracy is unmeasured until the headset calibration. We'll report it in #23.*

**What stops a wrong answer from being spoken?**
Every pick is only a preview. Speech needs a second, different brain signal (alpha, not P300). Cancel, a timeout, a disconnect or a late decision from an old round all produce no output. Tests check this.

**How do you know it never speaks twice, or speaks without a confirm?**
We fuzz it. `tests/test_contract_fuzz.py` throws random sequences of picks, confirms, cancels, disconnects, late and stale decisions, duplicates, malformed events, and every input source at the selection handler. An independent checker asserts after every step: one output per confirm, never an output without a fresh preview, the exact previewed words, no event accepted twice, no live-EEG confirm while it's disarmed, and no old-round decision acting in a newer round. **3,000,000 operations (50,000 sequences) found 0 violations**, reaching 61,779 confirms. CI runs 180,000 operations on every PR. We also break the handler on purpose (double output, a cancel that keeps the preview, ignored round IDs), and the fuzzer catches each one. *These are software guarantees with keyboard and simulated input, not live-EEG accuracy.*

**How fast does it respond?**
Once the wearer confirms, the app reacts in milliseconds. Every confirm is timed and logged (#130): **confirm → map change 2–30 ms**, and **confirm → speech starting about 15 ms** for the bundled clips or **about 50 ms** with the computer's own voice. Each rehearsal writes these to a session report in `logs/` (#131), so we can show the numbers from the run the judges just watched. The slow part is the brain signal itself, by design: a P300 choice takes one flash sequence (about 2.5–3.5 s), and the alpha confirm lands about 1.2–1.5 s after the eyes close. *Measured with keyboard input on a dev Mac. The EEG timings come from simulated data until the live headset run (#23).*

## Bonus criteria

**Is it a platform or a product?** *(platform, not a product)*
A platform. Every input source emits the same small selection event: source, round ID, event ID and target. Keyboard, the g.Pype simulator, P300, the alpha switch, or any g.tec device through a g.Pype pipeline can feed it without touching the app. Signal2Speech and OpenOrbit are two apps on the same contract. See [selection-contract.md](../architecture/selection-contract.md).

**Does it run cross-platform?** *(cross-platform support)*
Yes. Python, g.Pype and Qt only. GitHub Actions runs the full `pytest` suite on Windows, macOS and Linux for every PR (#37). The live headset path has only been planned on Windows so far.

**How production-ready is it?** *(production-ready prototype)*
A versioned event contract, a pinned lock file, a full `pytest` suite (124 passing at the time of writing) on three operating systems, honest input labels on screen, an offline demo, and raw EEG kept out of git. Not production: there's no clinical validation, live accuracy is unmeasured, and calibration is per wearer.

**How hard is it to get started?** *(low entry barrier)*
Clone, install the lock file, and run `python -m signal2speech.app --input simulated`. There's no headset, licence or internet needed to try the full flow. g.Pype's `Generator` stands in for the brain.

## The questions we will get on 11/15 (no headset)

**Is this live?**
No. The headset was lost in transit. The brain data is real human EEG that g.tec recorded on their amplifier, and the strip says Recorded. The eye-closure confirm at the table is simulated, and the strip says that too.

**Then what is actually happening when the tiles flash?**
Each flash is answered with one real single-flash brain response from g.tec's dataset: a response to an attended stimulus if the flashed tile is the scripted "wanted" one, a response to an ignored stimulus otherwise. The g.Pype pipeline and our classifier see only the EEG and have to work out which tile got the attended responses. `signal2speech/eeg/p300.py` (`RecordedP300`), `signal2speech/eeg/app_live.py` (`RecordedEegInput`).

**So the user's choice is faked?**
Which tile counts as "wanted" is scripted, and we say so: the recorded person was using g.tec's speller, not our app. What isn't scripted is the classification. It runs on noisy single responses and can pick wrong. If it misses in front of you, that's a real miss.

**How good is the classifier on real data?**
On g.tec's five recorded subjects, picking the attended item out of two: 94 % from one flash, 97 % from two, 99 % from three, 100 % from five. Tested on a separate stretch of each recording from the one it trained on. With the labels scrambled, the same code scores 42–46 %, which is chance. `python -m signal2speech.evidence.dataset <folder> --curve` reproduces it.

**Why should we believe it would work on a live headset?**
The live path is the same code: `RecordedEegInput` is `LiveEegInput` with a different sample source. It has never run on a Unicorn, and we don't claim it has. The recorded data uses a different electrode layout from the Unicorn's, so the classifier calibrates on whatever it's given.

**Did you try any real hardware?**
Yes. We borrowed a PiEEG Octopus 16 and tested it on two people overnight. It connected and recorded well, but with clean contact it showed no eyes-closed alpha and no response to a flickering square. Our best explanation is that its reference pin sits within 2 cm of its signal pins, which cancels a brain rhythm before it's measured. We kept ten recordings and wrote up the numbers in `docs/eeg-hardware/README.md`. We'd rather show you that than a shaky live trick.

**Why didn't you use a blink or a jaw clench as the switch?**
Because those are eye and muscle signals, not EEG, and we didn't want to call them brain control. We did measure them at the back of the head: both were too faint to use as a switch there.

## Other questions

**What about the MCP visualizer?**
We asked the g.tec mentor for access. It isn't in the public g.Pype docs, so we haven't integrated it. *Status: not built.* If we get access, it can read the same evidence stream.

**Where does AI come in?**
Claude suggests short replies to the partner's question. Without a key, a labelled Stub uses saved phrases. The AI suggests, and the wearer decides what's said. Code was written with Claude's help, which is disclosed in the submission.

**Why two signals?**
P300 is good for choosing among flashing options. The alpha switch is a deliberate on/off that a leftover P300 can't trigger by accident.

**What if the headset disconnects?**
The handler drops the pending preview and speaks nothing. We switch to the keyboard, and the strip says Keyboard.

**Why OpenOrbit?**
It shows the same controls driving something other than speech: a NASA satellite image and EPA air-quality data for a real event, June 26 to 28, 2023 in southeast Michigan. *Status: on `main`.*

## Science questions (Beyond the Horizon, #153)

Full detail in the [science note](../openorbit-data/science-note.md).

**"Does the satellite image show the air quality?"**
No. The image is MODIS Terra true color (bands 1-4-3, 250 m), a late-morning snapshot of how the scene looked from orbit. The gray haze on June 28 matches the PM2.5 peak, but the image doesn't measure PM2.5. The AQI numbers come from EPA's ground monitors and cover the whole day. That's why the screen credits NASA and EPA separately.

**"Is Washtenaw's +186 a fair comparison with Wayne's +168?"**
On the AQI scale, yes. Those are EPA's daily county values. But Washtenaw's June 26 value of 32 came from a single reporting site and was set by ozone, and the file doesn't give a June 26 PM2.5 value for Washtenaw. So its +186 isn't PM2.5 to PM2.5. Wayne is: PM2.5 on both days, 58 to 226. The app also shows the other answer: Wayne was worse on June 28 (226 vs 218).

**"How do you know it was wildfire smoke, and not local pollution?"**
Three independent sources agree:
- Michigan's EGLE declared a PM2.5 Air Quality Action Day on June 28, and the National Weather Service attributed it to Canadian wildfire smoke held down by an inversion.
- NASA FIRMS shows 9,457 vegetation-fire detections on June 26 and 28, 86% of them in Quebec at a median of about 1,340 km, and none in the demo area.
- PM2.5 set both counties' AQI on June 28 at Very Unhealthy. Wayne's PM2.5 went from Moderate (58) to Very Unhealthy (226), and Wayne had 10 sites reporting (all pollutants).

We show a correlation during a documented smoke event. We don't claim to attribute each AQI point to smoke.
