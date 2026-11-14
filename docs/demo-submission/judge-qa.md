# Likely judge questions (#13)

Short answers, mapped to g.tec's judging criteria. **Must-haves:** stimulus presentation, biosignal amplifier, real-time signal processing pipelines and algorithms, and a real-time application. **Bonus:** cross-platform support, a production-ready prototype, a platform rather than a product, and a low entry barrier.

Answer in one or two sentences, then stop. If something isn't verified, say so.

## Must-haves

**Where's the stimulus presentation?** *(stimulus presentation)*
Our own PySide6 tiles flash for 100 ms with 75 ms between flashes, 10 times per tile. Every flash sends a g.Pype `Marker`, so each epoch is locked to the flash. We didn't use Paradigm Presenter because it's separately licensed and Windows-only.

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
On synthetic data: 6 out of 6 online picks, and 95–100% offline. That shows the plumbing works, not that a person can use it. *Live accuracy is unmeasured until the headset calibration. We'll report it in #23.*

**What stops a wrong answer from being spoken?**
Every pick is only a preview. Speech needs a second, different brain signal (alpha, not P300). Cancel, a timeout, a disconnect or a late decision from an old round all produce no output. Tests check this.

## Bonus criteria

**Is it a platform or a product?** *(platform, not a product)*
A platform. Every input source emits the same small selection event: source, round ID, event ID and target. Keyboard, the g.Pype simulator, P300, the alpha switch, or any g.tec device through a g.Pype pipeline can feed it without touching the app. Signal2Speech and OpenOrbit are two apps on the same contract. See [selection-contract.md](../architecture/selection-contract.md).

**Does it run cross-platform?** *(cross-platform support)*
Yes. Python, g.Pype and Qt only. GitHub Actions runs the full `pytest` suite on Windows, macOS and Linux for every PR (#37). The live headset path has only been planned on Windows so far.

**How production-ready is it?** *(production-ready prototype)*
A versioned event contract, a pinned lock file, 89 tests on three operating systems, honest input labels on screen, an offline demo, and raw EEG kept out of git. Not production: there's no clinical validation, live accuracy is unmeasured, and calibration is per wearer.

**How hard is it to get started?** *(low entry barrier)*
Clone, install the lock file, and run `python -m signal2speech.app --input simulated`. There's no headset, licence or internet needed to try the full flow. g.Pype's `Generator` stands in for the brain.

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
It shows the same controls driving something other than speech: a NASA satellite image and EPA air-quality data for a real event, June 26 to 28, 2023 in southeast Michigan. *Status: the map view is in PR #65. Until it merges, `main` shows a labelled stand-in.*
