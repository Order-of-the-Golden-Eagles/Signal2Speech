"""``python -m signal2speech.evidence --source generator|hybridblack|replay``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m signal2speech.evidence",
        description="Judge-facing evidence window: raw vs filtered EEG, "
                    "OSCAR, spectrum and averaged target vs non-target "
                    "response.")
    parser.add_argument("--source", nargs="+", default=["generator"],
                        metavar="KIND",
                        help="generator | hybridblack | replay <run_dir>")
    parser.add_argument("--oscar", choices=["on", "off"], default="on",
                        help="HybridBlack only: OSCAR artifact removal "
                             "(default on)")
    parser.add_argument("--record", nargs="?", const="", default=None,
                        metavar="STEM",
                        help="Record this run (EEG and flash markers) under "
                             "STEM_<timestamp>/ (default recordings/evidence)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Replay speed (replay only)")
    parser.add_argument("--no-flasher", action="store_true",
                        help="Do not emit simulated flash markers (use when "
                             "the P300 chooser's tiles send them)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="Close the window after this many seconds")
    parser.add_argument("--screenshot", type=Path, default=None,
                        help="Save a PNG of the window just before closing")
    args = parser.parse_args(argv)
    kind = args.source[0]
    if kind not in ("generator", "hybridblack", "replay"):
        parser.error("--source must be generator, hybridblack or replay")
    if kind == "replay":
        if len(args.source) != 2:
            parser.error("--source replay needs a run directory")
        if args.record is not None:
            parser.error("cannot record a replay")
    elif len(args.source) != 1:
        parser.error(f"--source {kind} takes no path")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    # Imported after argument parsing so --help works without g.Pype.
    from .run import run

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
