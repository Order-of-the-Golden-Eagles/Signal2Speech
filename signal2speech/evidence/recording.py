"""Record and replay an evidence run with g.Pype's launch-level recorder.

``LaunchConfig.save_as`` records every source (the EEG and the flash
``Marker``) to a run directory of HDF5 files, before OSCAR. ``load_from``
replays that directory in place of the sources, so the same graph runs
on the recording. We add one small ``evidence.json`` beside the HDF5
files so a replay knows which source graph to rebuild.

Recordings live under ``recordings/``, which is gitignored. Never commit
them.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import gpype as gp

from .pipeline import SourceKind

#: Default folder for runs; gitignored.
RECORDINGS_DIR = Path("recordings")
META_FILE = "evidence.json"


def default_stem() -> Path:
    """``recordings/evidence``; g.Pype appends a timestamp per run."""
    return RECORDINGS_DIR / "evidence"


def configure_recording(stem: Path) -> None:
    """Record every source of the next pipeline under ``stem_<timestamp>``.

    Must run before the first source node is constructed.
    """
    stem.parent.mkdir(parents=True, exist_ok=True)
    gp.LaunchConfig.configure(save_as=str(stem))


def configure_replay(run_dir: Path, speed: float = 1.0) -> SourceKind:
    """Replay ``run_dir`` in place of the sources. Returns the recorded kind.

    Must run before the first source node is constructed.
    """
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"No recording at {run_dir}")
    gp.LaunchConfig.configure(load_from=str(run_dir), replay_speed=speed)
    return read_kind(run_dir)


def newest_run(stem: Path) -> Path | None:
    """The newest run directory g.Pype wrote for ``stem``."""
    runs = sorted(p for p in stem.parent.glob(stem.name + "_*") if p.is_dir())
    return runs[-1] if runs else None


def write_meta(run_dir: Path, kind: SourceKind, oscar: bool) -> None:
    """Note which source was recorded, so a replay rebuilds the same graph."""
    meta = {"source": kind.value, "oscar_requested": oscar,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "note": "Raw EEG. Do not commit. Label as Recorded."}
    (Path(run_dir) / META_FILE).write_text(json.dumps(meta, indent=2),
                                          encoding="utf-8")


def read_kind(run_dir: Path) -> SourceKind:
    """The recorded source kind; Generator when the run has no metadata."""
    path = Path(run_dir)
    if path.is_file():
        path = path.parent
    meta = path / META_FILE
    if meta.exists():
        return SourceKind(json.loads(meta.read_text("utf-8"))["source"])
    return SourceKind.GENERATOR
