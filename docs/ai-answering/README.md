# AI Answering

Suggest short replies to a typed question. Keep saved phrases available. Model and provider TBD.

**Active work** · [#5](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/5)

## Running AI Answering (#5, #27, #28)

```
python -m signal2speech.ai                                  # Claude if ANTHROPIC_API_KEY is in .env, else a labelled Stub
python -m signal2speech.ai --provider slow-stub --deadline 3 # rehearse the timeout fallback
python -m signal2speech.ai --provider saved                 # saved phrases only
```

Type the question and press Enter, then use keys 1/2 and Esc as usual. **Other replies** asks for a new pair and passes the previous pair, so the provider avoids repeating it. **Saved phrases** cycles the offline pairs.

- **Choices:** each reply becomes `Choice(target, ActionIds.SPEAK_REPLY, text, text)`, so the tile shows the exact words. The preview is silent. The #4 `AppSink` speaks the confirmed text once and never touches the map.
- **Origin label:** the panel always shows where the replies came from: **Claude** (green), **Stub** (amber), or **Saved phrases** (blue), plus the reason for any fallback, such as "timeout after 9 s" or "offline: no connection to provider". The transcript logs the question, the origin, and both replies.
- **Fallback:**
  - **Hard deadline:** `--deadline`, default 9 s. If the provider takes longer, saved phrases appear.
  - **Errors:** timeout, offline, bad key, rate limit, a refusal, or malformed output all fall back to saved phrases.
  - **No late swaps:** a late answer can never replace the choices on screen, because only the newest request can deliver, and only once.
- **Provider:** `claude-opus-5-5` through the Anthropic SDK, with JSON-schema structured output, low effort, server-side `fallbacks: "default"`, an 8 s timeout, and no retries. The key comes from `.env` (`ANTHROPIC_API_KEY=...`), which is git-ignored. `anthropic` isn't in `pyproject.toml` yet (#19 owns that file), so install it with `pip install anthropic`. Without it, or without a key, the app uses the Stub.
- **Not verified yet:** a live Claude call. No key was available while this was built. The request shape is unit-tested with a fake client.

**Map suggestions in the AI demo window.** When Claude suggests `show_satellite` or `compare_air_quality` (#106), `python -m signal2speech.ai` reveals the real OpenOrbit map and speaks its line once, the same as `python -m signal2speech.app`. The demo used to have no map on purpose, and that would have dropped the reveal.

## Live check in the AI demo window (#5, 2026-11-14 8:50 PM ET)

Run on `main` at `d7fe978` with `ANTHROPIC_API_KEY` in `.env` and `claude-opus-5-5`, through `python -m signal2speech.ai` (macOS 12, keyboard input):

| Question | Claude's two replies | Result |
| --- | --- | --- |
| "Would you like to take a short break and get some water?" | "Yes, please. A break and some water sounds good." / "No thanks, I'm fine. Let's keep going." | Replies in about 2 s. Key 1 previewed silently, key 1 confirmed, spoken **once** (OS voice). ✅ |
| "Which county's AQI rose more when wildfire smoke reached southeast Michigan?" | "I think Wayne County's AQI rose more." / "I'm not sure. Can we look it up together?" | ❌ **Factually wrong.** Washtenaw rose +186, Wayne +168. Ungrounded replies can state wrong facts. #116 fixes this by grounding replies in the dataset and offering the Compare counties map action. **Don't ask data questions in the AI demo until #116 is merged.** |

## Editing the saved phrases (#134)

The offline saved phrases live in `data/phrases.json`, one pair per line. Each pair is what the two tiles show and speak:

```json
"pairs": [
  ["Yes.", "No."],
  ["I'd like some water.", "I'm not thirsty."]
]
```

- **Rules:** two different phrases per pair, each under 120 characters. "Saved phrases" in the AI demo cycles through the pairs in order.
- **Fallback:** if the file is missing, can't be read, or breaks a rule, the app uses its built-in list (the same six pairs the file ships with). The transcript says why, for example `saved phrases: built-in (phrases.json pair 3: reply too long)`.
- **Check after editing:** start `python -m signal2speech.ai --provider saved` and read the `saved phrases:` line in the transcript.
