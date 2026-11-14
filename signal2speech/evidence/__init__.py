"""Judge-facing evidence view (#48): raw vs filtered EEG, OSCAR, spectrum,
and the averaged target vs non-target response.

Run it with ``python -m signal2speech.evidence --source generator``.
"""

from .pipeline import (
    EvidenceGraph,
    FrontEnd,
    InputLabel,
    SourceKind,
    build_evidence_graph,
    default_front_end,
)

__all__ = [
    "EvidenceGraph",
    "FrontEnd",
    "InputLabel",
    "SourceKind",
    "build_evidence_graph",
    "default_front_end",
]
