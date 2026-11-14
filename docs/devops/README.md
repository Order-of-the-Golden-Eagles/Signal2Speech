# DevOps

Keep an offline judging build and rollback path. Add PR smoke checks after the local check works.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15), [#14](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/14)

**Consolidated issues** · [#17](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/17), [#18](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/18)

## CI on every PR (#37)

`.github/workflows/tests.yml` runs on every pull request and every push to `main`.

- **Matrix:** Windows, Ubuntu, and macOS (Apple silicon) on Python 3.12, plus Ubuntu on 3.13. Qt runs offscreen.
- **Install:** `pip install -c requirements-lock.txt -e ".[dev]"`. Every package in the lock (g.Pype, PySide6, numpy, scipy, scikit-learn, h5py, and so on) gets its verified pin, and the pins have cp313 wheels too. Windows-only pins (pywin32, comtypes) are ignored elsewhere. Linux and macOS extras that the Windows-generated lock doesn't list (pynput's evdev and python-xlib, pyobjc) still float. The pip cache is keyed on `pyproject.toml` and the lock file.
- **Steps:**
  - install
  - version report (`importlib.metadata`, so it can't crash the job)
  - `pytest -q -rs`
  - `python -m signal2speech.app --smoke`. It's a visible "Smoke skipped" notice until #41 merges.
  - a **manual checks** list
- **Job summary:** each `ci (...)` job's summary shows the pytest exit code and result line, every skip with its reason, any FAILED or ERROR lines, the full smoke report with its exit code, and the manual checklist. It's written even when a step fails, so skips and failures are never silent. If the app can't even start, the smoke step fails instead of reporting a skip.
- **Cancelling runs:** a new push cancels the older run only on PRs. Each commit on `main` keeps its own result. Before this change, a quick second merge cancelled the first merge's run ([example](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43646992188)).
- **Linux packages** are the same list as in [platform notes](../dev-setup-docs/README.md#platform-notes). Only `espeak-ng` is installed, because pyttsx3 2.99 loads `libespeak-ng` and the legacy `libespeak1` isn't needed.

### Verified: the PR check passes and fails (#38)

| Run | Change | Result |
| --- | --- | --- |
| [43648496045](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43648496045) | #68 final commit | ✅ all 4 jobs green |
| [43649217606](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43649217606) | #38: a deliberately failing test (`tests/test_zz_ci_canary.py`) | ❌ all 4 jobs red with `1 failed, 104 passed`. The assertion message shows in the log and the `FAILED` line in the job summary. The smoke and manual-check steps still ran. |
| see PR #75 | #38: canary removed | ✅ expected green (recorded in PR #75) |

- **Matrix:** Ubuntu appears twice on purpose. `py3.12` matches the judging laptop. `py3.13` is the forward-compat canary, and it caught a 3.13-only test bug in #41 on its first day.
- **Known flake:** `tests/test_evidence.py:130` (#48, synthetic P300 peak `> 2.5`) failed once on macOS at 2.41 ([run](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43648196650)). Reported to the #48 owner. Re-run before treating a lone macOS evidence failure as real.
