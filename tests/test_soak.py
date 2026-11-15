"""#165: the soak harness reads the app's transcript correctly (no app is started here).

The soak itself (tests/soak/soak.py) runs for an hour and isn't part of pytest. These tests
pin the part that decides pass or fail: counting rounds and catching double outputs.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("soak", ROOT / "tests" / "soak" / "soak.py")
soak = importlib.util.module_from_spec(spec)
sys.modules["soak"] = soak          # dataclasses look the module up while it loads
spec.loader.exec_module(soak)


def feed(lines):
    t = soak.Tally()
    for i, line in enumerate(lines):
        t.feed(float(i), line)
    t.finish()
    return t


CONFIRM_ROUND = [
    "03:00:00  input: Simulated (g.Pype Generator + synthetic P300 · alpha bursts)",
    "03:00:10  round r1 choose: target-1=Show the satellite view, target-2=Compare counties",
    "03:00:13  round r2 confirm: target-1=Confirm, target-2=Cancel",
    "03:00:13  Previewed: simulated s1 r1->target-2",
    "03:00:16  OUTPUT map: compare_air_quality()  [simulated]",
    "03:00:16  OUTPUT speak: \"Washtenaw's AQI rose 186 points. Wayne's rose 168 points.\"",
    "03:00:16  timing: confirm→map 3 ms",
    "03:00:16  Confirmed: simulated s2 r2->target-1",
]


def test_a_clean_round_counts_once_with_its_times():
    t = feed(CONFIRM_ROUND)
    assert (t.previews, t.confirms, t.maps, t.speaks, t.double_outputs) == (1, 1, 1, 1, [])
    assert t.selection_s == [(3.0, 2.0)]                 # choose line 1 -> preview line 3
    assert t.confirm_map_ms == [(6.0, 3.0)]


def test_a_second_output_for_one_confirm_is_a_double_output():
    lines = CONFIRM_ROUND[:5] + [CONFIRM_ROUND[4]] + CONFIRM_ROUND[5:]
    assert feed(lines).double_outputs == [
        "Confirmed: simulated s2 r2->target-1: 2 map action(s), 1 spoken line(s)"]


def test_output_on_a_cancelled_round_is_caught():
    lines = CONFIRM_ROUND[:4] + ["03:00:20  OUTPUT speak: \"hello\"",
                                 "03:00:28  cleared (timeout): no output"]
    t = feed(lines)
    assert t.cancels == 1 and t.double_outputs == ["cleared (timeout): no output: output without a confirm"]


def test_restarts_crashes_and_tracebacks_are_seen():
    t = feed(["[launcher] 03:01:00  app exited with code -9 after 90 s. Restart 1/5 in 1 s.",
              "Traceback (most recent call last):",
              CONFIRM_ROUND[0]])
    assert len(t.app_exits) == 1 and len(t.errors) == 1 and len(t.app_starts) == 1


def test_a_run_cut_mid_confirm_is_not_a_double_output():
    assert feed(CONFIRM_ROUND[:6]).double_outputs == []


def test_the_script_never_runs_out_and_mixes_confirm_and_cancel():
    picks = soak.script_for(60, p300=True).split(",")
    assert len(picks) >= 2 * 60 * 60 // 8 and set(picks) == {"1", "2"}
    confirms = sum(1 for i in range(1, len(picks), 2) if picks[i] == "1")
    assert 0.6 < confirms / (len(picks) / 2) < 0.9


def test_memory_is_judged_per_app_process():
    """A restart starts a new process; each one must stay stable after its start-up samples."""
    run = soak.Soak.__new__(soak.Soak)            # no launcher: just the bookkeeping
    run.samples = ([soak.Sample(60.0 * i, 1, mb) for i, mb in enumerate([300, 226, 226, 230, 241])]
                   + [soak.Sample(60.0 * (30 + i), 2, mb)
                      for i, mb in enumerate([310, 300, 300, 302, 303, 400])])
    first, second = run.memory()
    assert (first["start_mb"], first["end_mb"]) == (226, 241) and run.stable(first)
    assert (second["start_mb"], second["end_mb"]) == (300, 400) and not run.stable(second)
    assert run.memory_ok() is False
