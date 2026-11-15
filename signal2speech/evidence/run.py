"""Wire the CLI to the pipeline, the recorder and the window."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import recording
from .pipeline import InputLabel, SourceKind, build_evidence_graph
from .synthetic import Flasher


def run(args: argparse.Namespace) -> int:
    kind_arg = args.source[0]
    oscar = args.oscar == "on"
    stem = None
    if kind_arg == "replay":
        run_dir = Path(args.source[1])
        kind = recording.configure_replay(run_dir, args.speed)
        label = InputLabel.RECORDED
        detail = f"Replaying {run_dir.name} (recorded from {kind.value})"
    else:
        kind = SourceKind(kind_arg)
        label = None
        detail = "Live headset" if kind is SourceKind.HYBRIDBLACK else \
            "Synthetic P300 added after target flashes"
        if args.record is not None:
            stem = Path(args.record) if args.record else \
                recording.default_stem()
            recording.configure_recording(stem)
            detail += "   |   REC"

    ev = session = header = None
    box: dict = {}
    if getattr(args, "p300", False):
        from . import p300_mode

        ev = p300_mode.build_p300_evidence(kind, label=label, oscar=oscar,
                                           flashes_per_tile=args.flashes)
        graph = ev.graph
        detail = ("Live headset" if kind is SourceKind.HYBRIDBLACK else
                  "Synthetic P300 after the attended tile's flashes") + \
            "   |   P300 chooser drives the flashes" + \
            ("   |   REC" if stem is not None else "")
        session = p300_mode.P300Session(ev, calibration=args.calibration,
                                        seed=args.seed)

        def header(banner):
            return p300_mode.make_header(banner, box)
    else:
        graph = build_evidence_graph(kind, label=label, oscar=oscar)
    graph.detail = detail

    flasher = None
    if kind_arg != "replay" and not args.no_flasher and ev is None:
        flasher = Flasher(graph.marker)

    from .app import run_window

    def started(app):
        if flasher is not None:
            flasher.start()
        if session is not None:
            if box:
                p300_mode.wire_session(session, box)
            session.start()
        if args.seconds is not None:
            _close_later(app, args.seconds, args.screenshot)

    try:
        code = run_window(graph, on_started=started, header=header)
    finally:
        if flasher is not None:
            flasher.stop()

    if stem is not None:
        run_dir = recording.newest_run(stem)
        if run_dir is not None:
            recording.write_meta(run_dir, kind, oscar)
            print(f"Recorded to {run_dir} (gitignored; do not commit).")
            print("Replay it with:\n  python -m signal2speech.evidence "
                  f"--source replay {run_dir}")
    return code


def _close_later(app, seconds: float, screenshot: Path | None) -> None:
    from PySide6.QtCore import QTimer

    def close():
        window = app.window
        if screenshot is not None and window is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(screenshot))
            print(f"Screenshot saved to {screenshot}")
        if window is not None:
            window.close()

    QTimer.singleShot(int(seconds * 1000), close)
