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

## AI assistant reads the pipeline (MCP server, #110)

`python -m signal2speech.mcp` is a local Model Context Protocol server. An assistant such as Claude Desktop or Claude Code can ask it about the running g.Pype pipeline and get answers from real pipeline numbers, for example "Is the wearer's P300 visible?". This is the sponsor's AI-integration demonstrator.

```
pip install -e ".[dev,mcp]"                      # adds the official MCP Python SDK (mcp 2.x)
python -m signal2speech.mcp                      # Generator (Simulated): calibrates, then decides every 6 s
python -m signal2speech.mcp --source hybridblack # Unicorn (Live EEG): signal quality and alpha only
```

**Tools.** All are read-only except `evidence_view`, and every result carries `"input": "Simulated" | "Recorded" | "Live EEG"`.

| Tool | Answers |
| --- | --- |
| `signal_quality()` | Per channel over the last 10 s: 1–30 Hz RMS, 50/60 Hz line noise, and ok, flat, or noisy |
| `pipeline_graph()` | The source, front end, P300 choose and evidence branches, alpha branch, OSCAR state, and whether the P300 is calibrated |
| `latest_decisions(n)` | The classifier's recent picks with their mean scores. On the Generator, it also gives the tile really attended, plus accuracy so far. |
| `p300_average(channel)` | Target vs non-target averaged response in 20 ms bins, the peak difference and latency in 250–500 ms, pre-flash noise, and a `p300_visible` verdict |
| `alpha_state()` | Occipital (PO7, Oz, PO8) 8–13 Hz power: the latest value and the 30 s spread |
| `evidence_view(action)` | `start` or `stop` the g.Pype evidence window. On the Generator, it opens a separate window. Live, it refuses, because this server holds the headset. |
| Resource `signal2speech://selection-contract` | The selection contract |

**How it works.** `signal2speech/mcp/monitor.py` runs the same P300 evidence pipeline as `python -m signal2speech.evidence --p300` (#76), headless, with no Qt.
- **Generator:** a session thread flashes the two tiles itself. First come 6 cued calibration sequences, which fill the averages and train the LDA. Then it runs one online sequence every 6 s with a random attended tile, so decisions can be checked against a known answer.
- **Live:** there are no tiles to look at in a headless process, so it doesn't flash. The P300 tools say so, and quality and alpha stay live.
- **Data shape:** results are summaries. The last 10 s of signal stays in the process, and no list in a result is longer than 64 values. A test checks this.
- **Transport:** stdio only, with no network listener.

**Connect it**
- **Claude Code:** `claude mcp add signal2speech -- /path/to/Signal2Speech/.venv/bin/python -m signal2speech.mcp`.
- **Claude Desktop:** add the block from [`mcp.example.json`](mcp.example.json) to `claude_desktop_config.json`, with your absolute path. On Windows the command is `...\.venv\Scripts\python.exe`. Then restart Claude Desktop.

**Verified (2026-11-14, Linux, simulated only).** On the Generator, `p300_average("Pz")` reported:
- a target-minus-non-target peak of 4.8 µV at 276 ms
- 0.7 µV of pre-flash noise
- `p300_visible: true`, labelled Simulated
- 3 of 3 decisions correct

`tests/test_mcp.py` (7 tests, `slow`) runs every tool against a Generator pipeline. It also runs one real stdio session with the official MCP client, including a bad argument, which returns a tool error instead of crashing. CI installs the `mcp` extra, so these tests run there.

**For the video (#34):** start the server in Claude Desktop, ask "Is the wearer's P300 visible?", and record about 30 s of the assistant calling `p300_average` and answering. Say on screen that the data is **Simulated**.

**Not done:**
- live P300 through MCP; use the app or the evidence view with a wearer
- recorded replay as a source
- g.tec's own `gpype-visualizer` MCP server, which we haven't been given (ask at #19); ours would sit beside it as the app-level view: decisions, contract, quality
