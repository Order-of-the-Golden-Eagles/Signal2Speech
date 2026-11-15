"""Shared pytest setup.

Tests that run a real-time g.Pype pipeline for several seconds are marked ``slow`` here, in one
place, so test files stay untouched. CI runs them on Windows (the judging laptop) and Ubuntu
py3.12 for every PR, and on every OS for pushes to main. Locally, ``pytest`` runs everything;
``pytest -m "not slow"`` gives a fast loop.
"""
import pytest

# Node-id prefixes of tests that take more than ~5 s (measured 2026-11-14).
SLOW = (
    "tests/test_live.py::test_generator_",                      # live-run harness dry runs (#23)
    "tests/test_evidence.py::test_generator_average_separates",  # evidence averaging (#48)
    "tests/test_alpha_confirm.py::test_generator_alpha_burst",   # alpha switch on g.Pype (#47)
    "tests/test_p300.py::test_realtime_generator_pipeline",      # P300 real-time path (#46)
    "tests/test_evidence_dataset.py::test_realtime_recording",   # g.tec recording playback (#142)
    "tests/test_lsl_source.py::test_self_test_stream",            # LSL stream into the alpha switch (#150)
)


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.replace("\\", "/").startswith(SLOW):
            item.add_marker(pytest.mark.slow)
