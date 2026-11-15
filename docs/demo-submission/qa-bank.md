# Q&A bank with suggested answers

Words you can say out loud, written to be spoken in under twenty seconds each. Use your own voice, but keep the facts and the honest labels. Background and sources are in the [team briefing](../TEAM-BRIEFING.md) and the longer [judge Q&A](judge-qa.md).

Three rules that apply to every answer:

1. Say "recorded" unless the pill at the bottom of the screen reads **Live EEG**.
2. Say "the classifier picked", not "the user chose", for a recorded run.
3. If you don't know, say "I'd have to check, it's in our repo." Never guess a number.

## The opening (say this before any question)

> "Signal2Speech is a voice for people who can't speak or type. Someone asks a question. The app suggests two replies. You pick one by looking at it, you see exactly what will be said, and you confirm by closing your eyes for two seconds. Only then does it speak. One honest note up front: our headset didn't arrive in time, so the brain data you'll see is real human EEG that g.tec recorded, running through the same pipeline a live headset would use."

If a headset is on someone and the pill reads Live EEG, replace the last sentence with:

> "This is live EEG from the headset right now. It's the first time we've run it on a person, so we'll see how it does together."

## What it is

**What does it do?**
> "It lets someone answer a question without speaking or typing. Any question in, two suggested replies, one picked by brain signal, previewed, confirmed, and spoken."

**Who is it for?**
> "People who can think clearly but can't speak or use their hands, for example after a stroke or with ALS. We haven't tested with patients. This is a weekend prototype of the interaction."

**What's the main feature and what's the NASA part?**
> "The conversation is the product. The NASA air-quality question is an example inside the same app. It shows the same two-choice control can drive something on screen, here real NASA images and EPA data, not only speech."

**Why only two choices?**
> "Two choices are fast and reliable with very few flashes. The AI turns any open question into two choices, and you can ask for other replies if neither fits."

**What makes it different from a P300 speller?**
> "A speller picks letters one at a time, which is slow. We pick whole replies. And nothing is spoken on the pick alone: there's a preview and a second, different brain signal to confirm."

## Is it real?

**Is this live?**
> "No. It's real human EEG, recorded by g.tec on their amplifier. Our headset didn't arrive. The pipeline and the classifier are the live ones."

**So what exactly is real?**
> "The brain responses are real. The filtering, the cutting-out of each flash and the classifier are real and are ours. The classifier isn't told which card is which. What's scripted is which card counts as the one being looked at, because the recording was made on g.tec's speller, not our cards. The screen says 're-mapped to our tiles'."

**Isn't that just faking the choice?**
> "The choice of which card is 'looked at' is scripted, yes, and we label it. But the classifier still has to find the real brain response among real non-responses, and it can get it wrong. That's the part a live headset would exercise the same way."

**Would it work on a real person?**
> "The same code runs with a Unicorn headset plugged in. We've only tested that path on simulated signals, so we don't claim an accuracy for a live person."

**Did you try any hardware?**
> "Yes. We tried a different EEG board on two people and got no usable brain signal: no eyes-closed rhythm and no response to flicker. We wrote that up as a negative result instead of hiding it."

**What happened to the headset?**
> "It didn't reach us in time. We built and tested everything we could without it and switched the demo to g.tec's published recordings."

## The brain signals

**How does choosing work?**
> "The two cards flash in turn. When the card you're watching flashes, your brain makes a small response about 300 milliseconds later, called the P300. We cut out the EEG around every flash and a classifier scores which card got that response."

**How does confirming work?**
> "When you close your eyes, a rhythm around ten cycles a second gets stronger at the back of the head. Two seconds of that is the confirm."

**Why two different signals?**
> "So one can't trigger the other by accident. A leftover response to a flash can't confirm, and closing your eyes can't pick a card."

**How accurate is it?**
> "On g.tec's recordings, across their five subjects, it picks the right card out of two 94 percent of the time from a single flash and 100 percent from five. That's tested on blocks of data it didn't train on. With scrambled labels it drops to chance. That's offline analysis of recordings, not a live result."

**How long does a reply take?**
> "About five seconds of flashing to pick and two seconds to confirm. After the confirm, the voice starts in well under a second."

**Does it need training?**
> "About a minute of calibration per person, so the classifier learns their response."

**What stops a wrong answer from being spoken?**
> "The pick only opens a preview with the exact words. Nothing is said until the confirm. Cancel, a timeout, or a disconnect all end with nothing spoken, and we have tests for each of those."

## g.tec and the pipeline

**What did you use from g.tec?**
> "g.Pype for the whole signal pipeline, their P300 Speller dataset for the recorded EEG, and the Unicorn Hybrid Black as the target headset, with their OSCAR artifact removal switched on in the live path."

**What's in the pipeline?**
> "Source, a 1 to 30 hertz band-pass, a trigger that cuts each flash from 100 milliseconds before to 700 after, then a linear discriminant classifier. A separate branch measures alpha band power for the confirm."

**Is it a platform or a one-off?**
> "Every input, keyboard, simulator, recorded data or headset, sends the same small selection message. Everything after that is shared. A new device or a new app plugs into that one contract."

**Does it run on other systems?**
> "The tests run on Windows, macOS and Linux on every change. The headset driver itself is Windows, Linux and Apple-silicon Macs."

## The AI

**What does the AI do?**
> "It suggests two short replies to the typed question. That's all. It never decides and it never speaks. The person previews the exact words and confirms."

**Which model?**
> "Claude, through Anthropic's API."

**Does it work offline?**
> "Partly. The reply suggestions need the internet. Without it, the app offers saved phrases like yes, no, and I need help. The EEG pipeline, the voice and the NASA example all run on the laptop."

**Is the brain decoding AI too?**
> "No. It's a standard statistical classifier in our g.Pype pipeline, trained on that person's calibration data."

**What about privacy?**
> "The typed question goes to Claude to get suggestions. EEG never leaves the laptop, and we only save raw EEG with the wearer's consent."

**Did you use AI to build it?**
> "Yes, we used Claude as a coding assistant, and that's disclosed in the submission."

## The NASA example

**What is the NASA question?**
> "Which county's air quality got worse when wildfire smoke reached southeast Michigan in June 2023. Washtenaw's index rose 186 points and Wayne's rose 168."

**Where is the data from?**
> "The images are NASA MODIS satellite images. The air-quality numbers are EPA's daily county values. The screen credits them separately."

**Does the satellite image measure air quality?**
> "No. It shows how the scene looked from orbit. The numbers come from EPA monitors on the ground."

**Why do the images start June 24 but the numbers compare June 26 and 28?**
> "June 25 to 27 were overcast, so June 24 is the last day you can see the ground. The EPA numbers we hold are for June 26 and 28. The screen says both of those things."

**How do you know it was wildfire smoke?**
> "Michigan declared an air-quality action day for June 28 and the weather service attributed it to Canadian wildfire smoke. NASA's fire data shows the fires in Quebec. We show a correlation during a documented smoke event. We don't claim more than that."

## Hard questions

**What didn't work?**
> "The headset didn't arrive, a second board gave no usable signal, and we've never run the live path on a person. We also had one report of the voice dropping out that we couldn't reproduce."

**What would you do next?**
> "Run it live and measure it on people. Then more than two choices, and stopping the flashes early once the classifier is confident."

**Why should this win?**
> "Because the hard parts are built and tested honestly: a real g.Pype pipeline, a classifier measured on real EEG, a safety step before anything is spoken, and a clear label on screen for what is and isn't live."

**Can I try it?** (no headset)
> "Yes. Type any question. The recorded brain data will pick, or you can pick with the keys 1 and 2 and hold 1 to confirm."

**Can I wear it?** (headset present)
> "Yes. It takes about a minute to calibrate to you. Then look at the reply you want and count its flashes. To confirm, hold key 1." (Say "close your eyes" only if eye-closure confirm was switched on for this wearer.)

## Questions to type into the app

Short questions with a clear two-way answer work best. Have a few ready so nobody has to think at the table.

| Type this | Why it works |
| --- | --- |
| Would you like some water? | Simple yes or no |
| Are you comfortable, or do you need something? | Two different needs |
| Do you want to keep going or take a break? | Either reply is plausible |
| How are you feeling today? | Shows the AI turning an open question into two replies |
| Should we call your family? | A reply that matters |
| Click **Example: NASA air quality** | The built-in question with NASA images and EPA data |

- If the replies don't fit, click **Other replies**.
- If the internet is down, the line under the question box says **Saved phrases**. Say so: "We're offline, so these are the saved phrases."
- With recorded data, Ctrl+1 or Ctrl+2 sets which reply the scripted wearer looks at next.
