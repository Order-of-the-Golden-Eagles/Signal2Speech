"""OpenOrbit offline comparison view (#30).

`dataset` is pure Python. `OpenOrbitView` needs PySide6 and is imported lazily, so importing the
dataset never pulls in Qt.
"""
from .dataset import Dataset, load_dataset

__all__ = ["Dataset", "OpenOrbitView", "load_dataset"]


def __getattr__(name):
    if name == "OpenOrbitView":
        from .view import OpenOrbitView
        return OpenOrbitView
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
