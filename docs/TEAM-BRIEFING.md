# Team briefing: what we built and how to talk about it

Read this before judging. It takes ten minutes. Every claim here links to the place in the repo that backs it, so if a judge pushes, you know where to look.

Updated 2026-11-15 for the judging-day build.

## The thirty-second version

Signal2Speech is a voice for people who can't speak or type. A partner asks a question. The app offers two replies. The wearer picks one by looking at it, sees exactly what will be said, and confirms by closing their eyes for two seconds. Only then does the app speak. It runs offline on one laptop.

**Say this early, every time:** our headset didn't arrive, so today the brain data is real human EEG that g.tec recorded on their own amplifier. It runs through the same pipeline and classifier a live headset would use. Nobody is wearing a headset at our table.

## What is real and what is not

This is the question judges care about most. Learn this table.

| Part | Status today | Say |
| --- | --- | --- |
| The EEG | Real human EEG from g.tec's P300 Speller dataset | "Recorded, not live" |
| The pipeline (filter, cut out each flash, classify) | Real: our g.Pype pipeline and our classifier, the same code as the live path | "The same code a headset would feed" |
| The classifier's decision | Real: it isn't told which card is which | "The classifier picked" |
| Which card counts as looked at | Scripted. The dataset was recorded on g.tec's speller, so we map its "looked at" and "not looked at" responses onto our two cards | "Re-mapped to our tiles" |
| The confirm (eyes closed) | Simulated signal through the real alpha detector | "Simulated" |
| Live EEG from a headset | Built and tested on simulated input. Never run on a person | "Not yet run live" |
| The PiEEG board | Tested on two people, no usable signal. Not in the demo | Only if asked |

The app's bottom row of pills always names the input: **Keyboard**, **Simulated**, **Recorded**, or **Live EEG**. Never say "live". Never say "the user chose" about a recorded run.

## The two demos

Both need about 90 seconds of setup after launch. Start them before the judge arrives. Run one at a time, because both talk.

| Demo | Command | What happens |
| --- | --- | --- |
| NASA question | `python -m signal2speech.app --input recorded --sim 2,1,1,1,2,1,1,1` | Calibration, then four questions by themselves. The cards flash, the recorded data picks, the map plays and one line is spoken. |
| Phrase selection | `python -m signal2speech.ai --input recorded` | Type any question and press Enter. Two replies flash, the recorded data picks one, it is spoken after the confirm. Ctrl+1 or Ctrl+2 sets which reply the scripted wearer looks at next. |
| Fallback, no dataset | `python -m signal2speech.app --input keyboard` | Press 1 or 2 to pick, hold 1 to confirm, hold 2 to cancel. Label: Keyboard. |

On the judging laptop, prefix with `./.venv/Scripts/python.exe` in place of `python`. If anything misbehaves, close the window and start again. Full run of show: [stage script](demo-submission/stage-script.md).

## How it works, in plain words

1. **Choosing (P300).** The two cards flash in turn. When the card you are watching flashes, your brain makes a small response about 300 milliseconds later. We cut out the EEG around each flash (100 ms before to 700 ms after), filter it to 1–30 Hz, and a classifier (linear discriminant analysis) scores which card got the response. We use five flashes per card.
2. **Confirming (alpha).** Close your eyes and a 8–13 Hz rhythm at the back of the head gets stronger. Two seconds of that confirms. It is a different brain signal from the P300, so a leftover flash response can't confirm by accident.
3. **Preview before speech.** The choice only opens a preview. Nothing is spoken until the confirm. Cancel, and nothing is said.
4. **One contract.** Keyboard, simulator, recorded data and live EEG all send the same small "selection" message. Everything after that is the same code.
5. **Calibration.** The classifier learns one person's responses in about a minute before the first question.

Where it lives: [architecture](architecture/README.md), [the g.Pype pipelines](architecture/pipelines.md), [selection contract](architecture/selection-contract.md), [code tour](demo-submission/code-tour.md).

## Numbers to know

| Number | Meaning | Source |
| --- | --- | --- |
| 94 % / 100 % | Right card out of two from one flash / from five flashes, on g.tec's recordings, tested on data it didn't train on | [EEG docs](eeg-hardware/README.md#how-many-flashes-the-chooser-needs-151), `python -m signal2speech.evidence.dataset <folder> --curve` |
| 5 flashes, 0.5 s apart | What the app uses per choice | same |
| 2 seconds | Eyes closed to confirm | [EEG docs](eeg-hardware/README.md) |
| +186 / +168 | AQI rise in Washtenaw / Wayne, June 26 to June 28, 2023 | [data sources](../data/openorbit/SOURCES.md) |
| 32→218, 58→226 | The AQI values behind those | same |
| June 24–28, 2023 | The NASA images shown day by day | [OpenOrbit docs](openorbit-data/README.md#day-by-day-june-24-to-june-28-2026-11-15) |
| 500+ tests | Run on Windows, macOS and Linux on every change | [DevOps](devops/README.md) |

Two honest caveats on the data. June 25, 26 and 27 were overcast, and the screen says "mostly cloud". The images start June 24, but the air-quality numbers compare June 26 with June 28, because those are the days we hold EPA data for. The screen says that too. Why the smoke claim holds: [science note](openorbit-data/science-note.md).

## Questions you should expect

Longer answers are in [judge Q&A](demo-submission/judge-qa.md). The short ones:

- **"Is this live?"** No. It is real recorded human EEG from g.tec, run through our live pipeline. Our headset didn't arrive.
- **"So is it faked?"** The brain responses and the classification are real. What is scripted is which card counts as the one being looked at, and the screen says so.
- **"Would it work on a real person?"** The same code runs with a Unicorn headset plugged in (`--input live`). We have tested that path on simulated signals only. We haven't measured it on a person, so we don't claim an accuracy for it.
- **"Why only two choices?"** Two choices are fast and reliable with few flashes. A yes/no or A/B answer covers a lot of real conversation, and the AI step turns any question into two choices.
- **"What does the AI do?"** It suggests two replies to a typed question (Claude, with saved phrases as the offline fallback). It never decides. The wearer previews and confirms the exact words. The EEG decoding is not AI-generated: it is a standard classifier in our g.Pype pipeline. Details: [AI answering](ai-answering/README.md).
- **"How fast is it?"** About five seconds of flashing to choose, two seconds to confirm. After the confirm the map and voice respond in well under a second.
- **"What about privacy?"** Everything runs offline except the optional reply suggestions. Raw EEG is saved only with the wearer's consent and never leaves the laptop or goes in the repo. Details: [security and privacy](security-privacy/README.md).
- **"Why NASA data?"** It is a concrete question with a checkable answer, and it shows the app doing something, not only speaking. NASA imagery shows the smoke from orbit. EPA data measures it on the ground.
- **"What did you use from g.tec?"** g.Pype for the whole signal pipeline, their P300 Speller dataset for the recorded EEG, and the Unicorn Hybrid Black as the target device.
- **"What didn't work?"** The headset didn't arrive. A second board we tried gave no usable EEG on two people, and we wrote that up as a negative result ([findings](eeg-hardware/README.md#pieeg-octopus-16-on-real-people-no-usable-eeg-2026-11-15)). One reported audio dropout was never reproduced.
- **"What's next?"** Run it live on a headset and measure it on people. Then more than two choices, and stopping the flashes early once the classifier is sure.

If you don't know an answer, say "I'd have to check, it's in our repo" and point to the README. Don't guess a number.

## Where everything is

| You want | Go to |
| --- | --- |
| The overview and commands | [README](../README.md) |
| What to say at the table, minute by minute | [stage script](demo-submission/stage-script.md) |
| Judge questions with full answers | [judge Q&A](demo-submission/judge-qa.md) |
| The video plan | [shot list](demo-submission/shot-list.md) |
| Devpost text, deadlines, AI disclosure | [submission checklist](demo-submission/submission-checklist.md) |
| EEG, classifier, accuracy, hardware findings | [EEG hardware](eeg-hardware/README.md) |
| NASA and EPA data, sources, limits | [OpenOrbit and data](openorbit-data/README.md), [sources](../data/openorbit/SOURCES.md) |
| The voice | [text to speech](text-to-speech/README.md) |
| Screen layout and accessibility choices | [accessibility and UI](accessibility-ui/README.md) |
| How the pieces connect | [integration](integration/README.md) |
| What changed and when, in plain words | [DEVLOG](../DEVLOG.md) |
| Current facts in one page | [living memory](MEMORY.md) |
| Setting up the judging laptop | [judging build](devops/judging-build.md) |

Code, if a judge asks to see it: `signal2speech/eeg/p300.py` (chooser and recorded responses), `signal2speech/eeg/alpha_confirm.py` (eye-closure confirm), `signal2speech/core/` (the selection contract), `signal2speech/app.py` (the one place that changes the map and speaks), `signal2speech/ai/` (reply suggestions), `signal2speech/openorbit/` (map and data).
