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
    python -m signal2speech.eeg.simulated --ui --flash --picks 2,1 --confirm-s 2   # P300-like timing

Round rule: ``arm_capture()`` runs when a sequence starts (here, when a round opens), never when
the decision arrives. A decision from an older sequence is dropped before it reaches the
adapter, so a late result can't land in the next round.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import deque
from typing import Callable, Iterable, List, Optional

import gpype as gp
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

from signal2speech.core import (EegClassMap, InputAdapter, InputSources, Outcome, Round,
                                RoundKind, SelectionEvent, SelectionHandler)

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

    Timing modes:

    - **No flasher (default).** Every round arms when it opens. The decision arrives after
      ``decision_s`` (Choose) or ``confirm_s`` (Confirm) seconds of stream.
    - **With ``flasher=window.flasher``** (the #24 ``FlashScheduler``). A Choose round arms on
      ``on_sequence_started`` and decides on ``on_sequence_finished``, as the P300 will (#46).
      A Confirm round arms when it opens and decides after ``confirm_s``, the alpha window
      (#47). This is the same contract as ``InjectedSimulatedInput`` in ``app.py``.
    """

    decided = Signal(int, int)   # (sequence id, classifier class index)

    def __init__(self, handler: SelectionHandler, picks: Iterable[int] = (), *,
                 decision_s: float = DEFAULT_DECISION_S, confirm_s: Optional[float] = None,
                 flasher=None, auto: bool = True,
                 classes: Optional[EegClassMap] = None, source=None,
                 sampling_rate: float = 250.0, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.handler = handler
        self.adapter = InputAdapter(handler, InputSources.SIMULATED)
        self.classes = classes or EegClassMap.default()
        self.decision_s = decision_s
        self.confirm_s = decision_s if confirm_s is None else confirm_s
        self.sampling_rate = sampling_rate
        self._picks = deque(int(p) for p in picks)
        self._seq = 0
        self._pending_seq: Optional[int] = None  # the sequence whose decision we accept
        self._pick: Optional[int] = None         # its pick; None = waiting for set_next()
        self._requested = False                  # the pick has been handed to the stream
        self._flashing = False                   # between on_sequence_started and _finished
        self.decision_threads = deque(maxlen=64)  # thread names that ran _on_decided (tests)
        self.dropped = deque(maxlen=64)           # stale sequence ids dropped before the adapter
        self._closed = False

        self.source = source or gp.Generator(sampling_rate=sampling_rate, channel_count=8,
                                             noise_amplitude=10.0)
        self.sink = DecisionSink()
        self.sink.emit = self.decided.emit
        self.pipeline = gp.Pipeline()
        self.pipeline.connect(self.source, self.sink)
        self.decided.connect(self._on_decided, Qt.ConnectionType.QueuedConnection)
        self.running = False

        self.flasher = flasher
        self._prev_hooks = None
        if flasher is not None:              # chain, don't replace, the window's own hooks
            started, finished = flasher.on_sequence_started, flasher.on_sequence_finished
            self._prev_hooks = (started, finished)

            def on_started():
                self._flash_started()
                if started:
                    started()

            def on_finished():
                self._flash_finished()
                if finished:
                    finished()
            flasher.on_sequence_started, flasher.on_sequence_finished = on_started, on_finished
        self._auto = auto
        if auto:
            handler.on_round_opened.append(self._on_round_opened)
            handler.on_cleared.append(self._on_cleared)

    # ── Stream lifecycle ─────────────────────────────────────
    def start(self) -> None:
        if not self.running:
            self.pipeline.start()
            self.running = True

    def stop(self) -> None:
        if self.running:
            self.cancel_sequence(restore=True)
            self.pipeline.stop()
            self.running = False

    def close(self) -> None:
        """Stop the stream and unhook from the handler and flasher. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self.stop()
        self.pipeline.close()
        if self._auto:
            for hooks, fn in ((self.handler.on_round_opened, self._on_round_opened),
                              (self.handler.on_cleared, self._on_cleared)):
                if fn in hooks:
                    hooks.remove(fn)
        if self.flasher is not None and self._prev_hooks is not None:
            self.flasher.on_sequence_started, self.flasher.on_sequence_finished = self._prev_hooks

    def disconnect_stream(self) -> None:
        """Simulate the headset dropping: stop the stream and clear the round (no output)."""
        self.stop()
        self.handler.disconnect()

    # ── Sequences ────────────────────────────────────────────
    @property
    def idle(self) -> bool:
        """Nothing scripted is left to deliver: no queued picks and no picked decision pending."""
        return not self._picks and (self._pending_seq is None or self._pick is None)

    @property
    def busy(self) -> bool:
        return not self.idle

    def start_sequence(self, delay_s: Optional[float] = None, hold: bool = False) -> Optional[int]:
        """Arm the adapter for the open round and give this sequence the next pick.

        ``hold=True`` (flash sequences) delivers the pick only when ``_flash_finished()`` runs.
        A previous sequence that never got its decision (another input used that round) drops
        its pick, so picks stay aligned one per round.
        """
        if self.handler.current is None:
            return None
        self.adapter.arm_capture()             # stamp the round now, as live EEG does
        self._seq += 1
        self._pending_seq = self._seq
        self._requested = False
        self._flashing = hold
        self.sink.cancel()
        self._pick = self._picks.popleft() if self._picks else None   # None: set_next() decides
        if self._pick is not None and not hold:
            self._request(self.decision_s if delay_s is None else delay_s)
        return self._seq

    def set_next(self, cls: int) -> None:
        """Pick for the waiting sequence (after its flashes end), or queue it for the next one."""
        if self._pending_seq is not None and self._pick is None:
            self._pick = int(cls)
            if not self._flashing:
                self._request(0.0)
        else:
            self._picks.append(int(cls))

    def cancel_sequence(self, restore: bool = False) -> None:
        """Forget the open sequence. ``restore`` puts its unused pick back for the next round."""
        if restore and self._pending_seq is not None and self._pick is not None:
            self._picks.appendleft(self._pick)
        self._pending_seq = self._pick = None
        self._requested = self._flashing = False
        self.sink.cancel()

    def _request(self, delay_s: float) -> None:
        if self._pending_seq is not None and self._pick is not None and not self._requested:
            self._requested = True
            self.sink.request(self._pending_seq, self._pick, round(delay_s * self.sampling_rate))

    def _on_round_opened(self, rnd: Round) -> None:
        if rnd.kind is RoundKind.CONFIRM:
            self.start_sequence(self.confirm_s)
        elif self.flasher is None:
            self.start_sequence(self.decision_s)
        # With a flasher, the Choose round arms in _flash_started.

    def _on_cleared(self, _reason: str) -> None:
        self.cancel_sequence(restore=True)     # cancel/disconnect: the same step comes again

    def _flash_started(self) -> None:
        self.start_sequence(hold=True)

    def _flash_finished(self) -> None:
        self._flashing = False
        self._request(0.0)                     # next stream frame carries the decision

    @Slot(int, int)
    def _on_decided(self, seq: int, cls: int) -> None:
        """Main thread. Only the current sequence reaches the adapter."""
        self.decision_threads.append(threading.current_thread().name)
        if seq != self._pending_seq:
            self.dropped.append(seq)
            return
        self._pending_seq = self._pick = None
        self._requested = False
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
    p.add_argument("--flash", action="store_true",
                   help="with --ui: flash Choose tiles, arm/decide on the flash sequence")
    p.add_argument("--confirm-s", type=float, default=None,
                   help="stream seconds before a Confirm-round decision (default: --decision-s)")
    p.add_argument("--timeout", type=float, default=20.0, help="headless: give up after N s")
    args = p.parse_args(argv)

    from signal2speech.ui import SelectionWindow
    from signal2speech.ui.__main__ import PrintSink, load_demo_choices   # reuse #24's stubs

    if not args.ui and not args.picks:
        print("headless needs --picks (e.g. --picks 2,1); use --ui to pick with Ctrl+1/Ctrl+2",
              file=sys.stderr)
        return 2
    if not args.ui and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"     # headless: no display needed
    # Always a QApplication: the first Qt app in a process wins, and widgets need this one.
    app = QApplication.instance() or QApplication(sys.argv[:1])

    handler = SelectionHandler(PrintSink())
    handler.on_handled.append(lambda e, o: print(log_line(e, o), flush=True))
    choices = load_demo_choices()
    win = None
    if args.ui:
        keyboard = InputAdapter(handler, InputSources.KEYBOARD)
        win = SelectionWindow(handler, keyboard, input_source=InputSources.SIMULATED,
                              flash=args.flash)
    decoder = SimulatedDecoder(handler, args.picks, decision_s=args.decision_s,
                               confirm_s=args.confirm_s,
                               flasher=win.flasher if win is not None and args.flash else None)

    if win is not None:
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
        # Headless: reopen the question while picks remain; quit once they are spent.
        def after(_e, o):
            if o not in (Outcome.Confirmed, Outcome.Cancelled):
                return
            if decoder.idle:
                QTimer.singleShot(200, app.quit)
            else:
                QTimer.singleShot(100, lambda: handler.begin_choice_round(choices))
        handler.on_handled.append(after)

        def give_up():
            timed_out.append(True)
            print(f"timeout after {args.timeout:g} s with picks left; exit 1", file=sys.stderr)
            app.exit(1)
        QTimer.singleShot(int(args.timeout * 1000), give_up)
    timed_out: List[bool] = []

    decoder.start()
    handler.begin_choice_round(choices)
    try:
        code = app.exec()
        return 1 if timed_out else code
    finally:
        decoder.close()


if __name__ == "__main__":
    sys.exit(main())
