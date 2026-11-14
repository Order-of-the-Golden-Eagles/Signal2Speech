"""Simulated EEG decisions through a real g.Pype pipeline (#21).

This is the live-EEG path with a scripted brain:

    gp.Generator (8 ch noise, 250 Hz)  ->  DecisionSink        [g.Pype worker thread]
        -> SimulatedDecoder.decided (queued Qt signal)         [crosses to the Qt main thread]
        -> InputAdapter(handler, SIMULATED).select_captured()  [main thread only]

The Generator stands in for the headset stream, so threading and timing are real. Which target
gets picked is deterministic: it comes from ``--picks``, from Ctrl+1 / Ctrl+2 in the window, or
from ``set_next()``. Every event is labelled ``simulated``.

    python -m signal2speech.eeg.simulated --picks 2,1        # headless: preview, then confirm
    python -m signal2speech.eeg.simulated --ui               # #24 window; Ctrl+1/Ctrl+2 pick
    python -m signal2speech.eeg.simulated --ui --picks 2,1   # window, scripted

Round rule: ``arm_capture()`` runs when a sequence starts (here, when a round opens), never when
the decision arrives. A decision from an older sequence is dropped before it reaches the
adapter, so a late result can't land in the next round.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import deque
from typing import Callable, Iterable, List, Optional

import gpype as gp
from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal, Slot

from signal2speech.core import (EegClassMap, InputAdapter, InputSources, Outcome, Round,
                                SelectionEvent, SelectionHandler)

PORT_IN = "in"
DEFAULT_DECISION_S = 0.8   # stand-in for a P300 sequence; long enough to see the preview


class DecisionSink(gp.INode):
    """Runs on a g.Pype worker thread. Emits one decision per requested sequence.

    A request says "after ``samples`` more stream samples, decide ``cls`` for sequence
    ``seq``". Counting real samples means the decision waits on the stream like a classifier
    would, and a stalled stream delivers no decision.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.emit: Callable[[int, int], None] = lambda seq, cls: None
        self._lock = threading.Lock()
        self._request: Optional[List[int]] = None   # [seq, cls, samples_left]
        self.samples_seen = 0

    def request(self, seq: int, cls: int, samples: int) -> None:
        with self._lock:
            self._request = [seq, cls, max(1, int(samples))]

    def cancel(self) -> None:
        with self._lock:
            self._request = None

    def step(self, data):
        block = data.get(PORT_IN)
        rows = 0 if block is None else len(block)
        fire = None
        with self._lock:
            self.samples_seen += rows
            if self._request is not None:
                self._request[2] -= rows
                if self._request[2] <= 0:
                    fire, self._request = (self._request[0], self._request[1]), None
        if fire is not None:
            self.emit(*fire)   # Qt queues it to the main thread
        return {}


class SimulatedDecoder(QObject):
    """Feeds scripted decisions into the handler through the same calls live EEG uses.

    Create it on the Qt main thread. ``decided`` is emitted on a g.Pype worker thread and
    delivered to ``_on_decided`` on the main thread through a queued connection.
    """

    decided = Signal(int, int)   # (sequence id, classifier class index)

    def __init__(self, handler: SelectionHandler, picks: Iterable[int] = (), *,
                 decision_s: float = DEFAULT_DECISION_S, auto: bool = True,
                 classes: Optional[EegClassMap] = None, source=None,
                 sampling_rate: float = 250.0, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.handler = handler
        self.adapter = InputAdapter(handler, InputSources.SIMULATED)
        self.classes = classes or EegClassMap.default()
        self.decision_s = decision_s
        self.sampling_rate = sampling_rate
        self._picks = deque(int(p) for p in picks)
        self._seq = 0
        self._pending_seq: Optional[int] = None
        self._waiting_for_pick = False
        self.decision_threads: List[str] = []   # thread names that ran _on_decided (tests)
        self.dropped: List[int] = []            # stale sequence ids dropped before the adapter

        self.source = source or gp.Generator(sampling_rate=sampling_rate, channel_count=8,
                                             noise_amplitude=10.0)
        self.sink = DecisionSink()
        self.sink.emit = self.decided.emit
        self.pipeline = gp.Pipeline()
        self.pipeline.connect(self.source, self.sink)
        self.decided.connect(self._on_decided, Qt.ConnectionType.QueuedConnection)
        self.running = False

        if auto:
            handler.on_round_opened.append(self._on_round_opened)
            handler.on_cleared.append(lambda _reason: self.cancel_sequence())

    # ── Stream lifecycle ─────────────────────────────────────
    def start(self) -> None:
        if not self.running:
            self.pipeline.start()
            self.running = True

    def stop(self) -> None:
        if self.running:
            self.cancel_sequence()
            self.pipeline.stop()
            self.running = False

    def close(self) -> None:
        self.stop()
        self.pipeline.close()

    def disconnect_stream(self) -> None:
        """Simulate the headset dropping: stop the stream and clear the round (no output)."""
        self.stop()
        self.handler.disconnect()

    # ── Sequences ────────────────────────────────────────────
    @property
    def busy(self) -> bool:
        """True while a sequence is waiting for its decision or picks remain."""
        return self._pending_seq is not None or bool(self._picks)

    def start_sequence(self) -> Optional[int]:
        """Arm the adapter for the open round and request a decision if a pick is queued."""
        if self.handler.current is None:
            return None
        self.adapter.arm_capture()             # stamp the round now, as live EEG does
        self._seq += 1
        self._pending_seq = self._seq
        self.sink.cancel()
        if self._picks:
            self._request(self._picks.popleft())
        else:
            self._waiting_for_pick = True      # Ctrl+1/Ctrl+2 or set_next() decides
        return self._seq

    def set_next(self, cls: int) -> None:
        """Pick for the waiting sequence, or queue the pick for the next one."""
        if self._pending_seq is not None and self._waiting_for_pick:
            self._request(int(cls))
        else:
            self._picks.append(int(cls))

    def cancel_sequence(self) -> None:
        self._pending_seq = None
        self._waiting_for_pick = False
        self.sink.cancel()

    def _request(self, cls: int) -> None:
        self._waiting_for_pick = False
        self.sink.request(self._pending_seq, cls, round(self.decision_s * self.sampling_rate))

    def _on_round_opened(self, _rnd: Round) -> None:
        self.start_sequence()

    @Slot(int, int)
    def _on_decided(self, seq: int, cls: int) -> None:
        """Main thread. Only the current sequence reaches the adapter."""
        self.decision_threads.append(threading.current_thread().name)
        if seq != self._pending_seq:
            self.dropped.append(seq)
            return
        self._pending_seq = None
        self.adapter.select_captured(self.classes.target_for(cls))


# ── Standalone run ───────────────────────────────────────────
def log_line(e: Optional[SelectionEvent], outcome: Outcome) -> str:
    row = {"t": round(time.monotonic(), 3), "outcome": outcome.value}
    if e is not None:
        row.update(source=e.source, roundId=e.roundId, eventId=e.eventId, targetId=e.targetId)
    return json.dumps(row)


def parse_picks(text: str) -> List[int]:
    picks = [int(s) for s in (p.strip() for p in text.split(",")) if s]
    if any(p not in (1, 2) for p in picks):
        raise argparse.ArgumentTypeError("picks are classes 1 or 2, e.g. 2,1")
    return picks


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.simulated")
    p.add_argument("--picks", type=parse_picks, default=[],
                   help="classes to decide, one per sequence, e.g. 2,1 = choose tile 2, confirm")
    p.add_argument("--decision-s", type=float, default=DEFAULT_DECISION_S,
                   help="stream seconds per sequence before the decision")
    p.add_argument("--ui", action="store_true", help="open the #24 window labelled Simulated")
    p.add_argument("--timeout", type=float, default=20.0, help="headless: give up after N s")
    args = p.parse_args(argv)

    from signal2speech.ui.__main__ import PrintSink, load_demo_choices   # reuse #24's stubs

    if args.ui:
        from PySide6.QtGui import QKeySequence, QShortcut
        from PySide6.QtWidgets import QApplication
        from signal2speech.ui import SelectionWindow
        app = QApplication.instance() or QApplication(sys.argv[:1])
    else:
        app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])

    handler = SelectionHandler(PrintSink())
    handler.on_handled.append(lambda e, o: print(log_line(e, o), flush=True))
    decoder = SimulatedDecoder(handler, args.picks, decision_s=args.decision_s)
    choices = load_demo_choices()

    if args.ui:
        keyboard = InputAdapter(handler, InputSources.KEYBOARD)
        win = SelectionWindow(handler, keyboard, input_source=InputSources.SIMULATED)
        win.set_connection("simulated stream (g.Pype Generator)")
        for seq, cls in (("Ctrl+1", 1), ("Ctrl+2", 2)):
            sc = QShortcut(QKeySequence(seq), win)
            sc.setAutoRepeat(False)
            sc.activated.connect(lambda c=cls: decoder.set_next(c))
        reopen = QTimer(win, singleShot=True, interval=1500)
        reopen.timeout.connect(lambda: handler.begin_choice_round(choices))
        handler.on_cleared.append(lambda _r: reopen.start())
        handler.on_handled.append(lambda _e, o: reopen.start() if o is Outcome.Confirmed else None)
        win.show()
    else:
        # Headless: stop once the scripted picks are spent and nothing is pending.
        def maybe_quit(_e, _o):
            if not decoder.busy:
                QTimer.singleShot(200, app.quit)
        handler.on_handled.append(maybe_quit)
        QTimer.singleShot(int(args.timeout * 1000), app.quit)
        if not args.picks:
            print("no --picks given; nothing will be decided headless (use --ui for keys)")

    decoder.start()
    handler.begin_choice_round(choices)
    try:
        return app.exec()
    finally:
        decoder.close()


if __name__ == "__main__":
    sys.exit(main())
