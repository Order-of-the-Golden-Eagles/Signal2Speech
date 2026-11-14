# DevOps

Keep an offline judging build and rollback path. Add PR smoke checks after the local check works.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15), [#14](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/14)

**Consolidated issues** · [#17](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/17), [#18](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/18)

## CI on every PR (#37)

`.github/workflows/tests.yml` runs on every pull request and every push to `main`.

- **Matrix:** Windows, Ubuntu, and macOS (Apple silicon) on Python 3.12, plus Ubuntu on 3.13. Qt runs offscreen.
- **Install:** `pip install -c requirements-lock.txt -e ".[dev]"`. The verified pins apply wherever a package is needed, so CI tests what the judging laptop runs. Windows-only pins (pywin32, comtypes) are ignored elsewhere. The pip cache is keyed on `pyproject.toml` and the lock file.
- **Steps:**
  - install
  - version report (`importlib.metadata`, so it can't crash the job)
  - `pytest -q -rs`
  - `python -m signal2speech.app --smoke`. It's a visible "Smoke skipped" notice until #41 merges.
  - a **manual checks** list
- **Job summary:** each job's summary shows the pytest result line, every skip with its reason, the full smoke report, and the manual checklist. Skips are never silent.
- **Cancelling runs:** a new push cancels the older run only on PRs. Each commit on `main` keeps its own result, because the main push at 22:13:56 UTC was cancelled by the next merge.
- **Linux packages** are the same list as in [platform notes](../dev-setup-docs/README.md#platform-notes). Only `espeak-ng` is installed, because pyttsx3 2.99 loads `libespeak-ng` and the legacy `libespeak1` isn't needed.
