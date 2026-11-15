# Security and Privacy

Keep credentials and raw EEG out of Git and public logs. Validate any local bridge input.

**Active work** · [#10](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/10)

## Release check (#10, #35)

Run it on the exact revision you plan to submit, from a clean checkout:

```
python tools/release_check.py                  # all checks, about a minute
python tools/release_check.py --all-branches   # also scan every branch's history for secrets
```

It never prints a secret value or an email address. Exit code 1 means a check failed.

| Check | What it looks for |
| --- | --- |
| Secrets in history | API keys (Anthropic, OpenAI-style, GitHub, AWS, Google, Slack), private key blocks, and hardcoded `api_key`, `token`, or `password` strings in every added or removed line |
| Tracked files | `.env`, keys, and raw EEG formats (`.h5`, `.hdf5`, `.edf`, `.bdf`, `.gdf`, `.xdf`, `.fif`, `.mat`) fail. Media, archives, and files over 1 MB are flagged for review. |
| Raw EEG ignore rules | Recording paths under `recordings/` (g.Pype and the evidence view, #48) and `.env` must be gitignored |
| Email addresses | Addresses inside tracked files, and commit authors who don't use a GitHub noreply address |
| Data, tests, offline app | The same checks as the [judging laptop runbook](../devops/judging-build.md#judging-laptop-runbook-39) |

A test run with planted problems (fake keys, a tracked `.env` and `.h5`, removed ignore rules, an email in a file) failed on every one of them.

### Results on 2026-11-14

Scanned `architecture-and-libraries` and every fetched branch.

| Item | Result |
| --- | --- |
| Secrets in any branch's history | None found |
| Credentials or raw EEG tracked on any branch | None. No files over 1 MB. |
| EEG recordings (#48 writes `recordings/evidence_<timestamp>/*.h5`) | Gitignored by `recordings/`, `*.h5`, and `*.hdf5` |
| Local bridge (#35) | Not applicable. No code on any branch opens a listening socket, and the app runs in one process (team decision). |
| AI provider key (#35, branch `issue-5-ai`) | Read only from `ANTHROPIC_API_KEY` in the environment or the gitignored `.env`, and never logged. Only the typed question goes to the provider, never EEG. Without a key or a connection, it falls back to saved phrases. |
| Personal data | No email addresses inside files. Commit metadata includes one teammate's university address (on `main`) and one personal address (on `21-simulated-input`). Both become public if the repo goes public. |

**Keep new commits private:** in GitHub Settings → Emails, turn on "Keep my email addresses private" and "Block command line pushes that expose my email". Then set `git config user.email` to your `ID+username@users.noreply.github.com` address. Rewriting existing history would break everyone's branches, so that is a team decision.

**Still to do before submitting (#10 Done when):** run the full check on the exact submission revision, and look through any demo video or screenshots for personal data before uploading them.

## Judging revision review (#33)

### First pass: `main` at `aec013f`, 2026-11-14 6:20 PM ET

This is not the judging commit yet (#42 hasn't frozen one). Repeat the final pass below on the frozen commit and the real submission assets.

| Item | Result | How it was checked |
| --- | --- | --- |
| Secrets in any branch's history | None found | `python tools/release_check.py --quick --all-branches` |
| Credentials, raw EEG, or large files tracked | None | Same |
| Recording paths and `.env` gitignored | Yes, all 14 sample paths | Same |
| Trained per-wearer models and logs | Gitignored (`models/`, `*.pkl`, `*.joblib`, `logs/`). P300 calibration stays in memory, and synthetic recordings go to a temporary folder (`signal2speech/eeg/p300.py`). | `git check-ignore` on sample paths, code read |
| Network senders | None in `signal2speech/` (no `UDPSender`, `LSLSender`, sockets, or HTTP). The only outbound call is the optional Claude request in `signal2speech/ai/`, and it sends the typed question only, never EEG. | `grep`, code read |
| Tracked images | Two NASA MODIS JPEGs in `data/openorbit/`, with no GPS, author, or camera metadata | `sips -g all` |
| Personal data in commit metadata | **Warning.** Two commit authors (In Young Song, Long Le) used personal email addresses rather than GitHub noreply ones. They become public if the repo goes public. | `release_check.py` (addresses not printed) |

**Action for those two authors:** in GitHub Settings → Emails, turn on "Keep my email addresses private". Then run `git config user.email <id>+<username>@users.noreply.github.com` for future commits. Whether to rewrite existing history is a team decision, because it breaks every open branch.

### Final pass checklist (run on the frozen judging commit)

- [ ] Check out the exact commit from #42 into a clean folder, and record its hash here: `________`
- [ ] `python tools/release_check.py --all-branches`: 0 failures. Decide on the email warning before the repo goes public.
- [ ] No `.env`, `recordings/`, `models/`, or `logs/` content in the commit or in any file attached to the submission
- [ ] **Video and screenshots (#34):** no API key, `.env`, terminal history, notifications, email, or file paths with personal names on screen. Every EEG shot is labelled Live EEG, Recorded, or Simulated.
- [ ] **Devpost text:** no personal emails or phone numbers beyond what the team agreed to share
- [ ] Repo visibility switched to public only after the items above pass
