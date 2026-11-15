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
