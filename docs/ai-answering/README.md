# AI Answering

Suggest short replies to a typed question. Keep saved phrases available. Claude `claude-sonnet-5-5`, grounded in the OpenOrbit data (#106).

**Active work** · [#5](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/5)

## Running AI Answering (#5, #27, #28)

```
python -m signal2speech.ai                                  # Claude if ANTHROPIC_API_KEY is in .env, else a labelled Stub
python -m signal2speech.ai --provider slow-stub --deadline 3 # rehearse the timeout fallback
python -m signal2speech.ai --provider saved                 # saved phrases only
```

Type the question and press Enter, then use keys 1/2 and Esc as usual. **Other replies** asks for a new pair and passes the previous pair, so the provider avoids repeating it. **Saved phrases** cycles the offline pairs.

- **Choices:** each reply becomes `Choice(target, ActionIds.SPEAK_REPLY, text, text)`, so the tile shows the exact words. The preview is silent. The #4 `AppSink` speaks the confirmed text once and never touches the map.
- **App actions (#106):** each reply also carries an action: `speak_reply`, `show_satellite`, or `compare_air_quality`. For the two map actions the app ignores the model's words: the tile reads "Compare counties (shows the map)" or "Show the satellite view (shows the map)", and the spoken line comes from `dataset.spoken_comparison()` or `contracts/demo-round.json`, so the spoken numbers always match the map. An unknown action, the same action twice, or the same words twice falls back to saved phrases.
- **Verified facts (#106):** when the provider is built, it adds a "Verified facts" block to the system prompt, computed from `data/openorbit/` (the four EPA AirData AQI rows with dates, categories, and changes; EMU in Washtenaw and Detroit in Wayne; NASA GIBS MODIS imagery). The rules say to state facts only from that block, never invent numbers, dates, or comparisons, and offer an honest "I don't know" or a request for a moment otherwise. The prompt has no timestamps, so it's byte-identical on every call. Prompt caching isn't used: the prompt (about 2,100 characters) is below the minimum cacheable length.
- **Origin label:** the panel always shows where the replies came from: **Claude** (green), **Stub** (amber), or **Saved phrases** (blue), plus the reason for any fallback, such as "timeout after 9 s" or "offline: no connection to provider". The transcript logs the question, the origin, and both replies.
- **Fallback:**
  - **Hard deadline:** `--deadline`, default 9 s. If the provider takes longer, saved phrases appear.
  - **Errors:** timeout, offline, bad key, rate limit, a refusal, or malformed output all fall back to saved phrases.
  - **No late swaps:** a late answer can never replace the choices on screen, because only the newest request can deliver, and only once.
- **Provider:** `claude-sonnet-5-5` (faster than Opus for this short task: about 1.4 to 1.9 s against 2 to 3 s) through the Anthropic SDK, with JSON-schema structured output, low effort, server-side `fallbacks: "default"`, an 8 s timeout, and no retries. The key comes from `.env` (`ANTHROPIC_API_KEY=...`), which is git-ignored. `anthropic` isn't in `pyproject.toml` yet (#19 owns that file), so install it with `pip install anthropic`. Without it, or without a key, the app uses the Stub.
- **Live check (11/14/26, #106):** `claude-sonnet-5-5`, real API calls through `ClaudeProvider` (`fallbacks: "default"`, low effort). Before #106, every model answered "Wayne" to the AQI question, which is wrong.

  | Question | Latency | Reply A | Reply B |
  |---|---|---|---|
  | Which county's AQI rose more when wildfire smoke reached southeast Michigan? | 2.71 s (first call), 1.78 s | `compare_air_quality`: "Compare counties (shows the map)", speaks "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." (model summary: "Washtenaw County's AQI rose more, up 186 points.") | `show_satellite`: speaks the contract's June 28, 2023 MODIS line |
  | Do you want water or juice? | 1.41 s, 1.64 s | "Water, please. Thank you." | "Juice, please. Thank you." / "Juice sounds good to me, thank you." |
  | What was the AQI in Ann Arbor in July 2021? (not in the data) | 1.93 s | "I don't know the Ann Arbor AQI for July 2021." | "Give me a moment, please. I'm not sure about that." |

- **Not verified yet:** the live call inside the full app with a headset. The panel flow is unit-tested with a fake client.

**Map suggestions in the AI demo window.** When Claude suggests `show_satellite` or `compare_air_quality` (#106), `python -m signal2speech.ai` reveals the real OpenOrbit map and speaks its line once, the same as `python -m signal2speech.app`. The demo used to have no map on purpose, and that would have dropped the reveal.
