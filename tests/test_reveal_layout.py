"""Reveal layout (#225): while the map is shown, the left column stays readable."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QFont, QTextLayout  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import TargetIds  # noqa: E402

T1 = TargetIds.TARGET_1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


class Speaker:
    def say(self, text, clip=None):
        pass


class MapView(QLabel):
    def __init__(self):
        super().__init__("map")
        self.setMinimumSize(360, 280)

    def show_satellite(self):
        pass

    def compare_air_quality(self):
        pass


def wrapped_lines(label, px):
    """The lines Qt draws for the word-wrapped preview at its current width and font size."""
    font = QFont(label.font())
    font.setPixelSize(px)
    font.setBold(True)
    layout = QTextLayout(label.text(), font)
    width = label.contentsRect().width()
    layout.beginLayout()
    lines = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        lines.append(label.text()[line.textStart():line.textStart() + line.textLength()].strip())
    layout.endLayout()
    return lines


@pytest.mark.parametrize("size", [(1280, 720), (1600, 900)])
def test_reveal_keeps_the_quote_and_strip_readable(qapp, size):
    app = App(view=MapView(), speaker=Speaker(), echo=False, reveal_ms=60000)
    app.root.resize(*size)
    app.root.show()
    app.ask()
    app.window.press_target(T1)
    app.window.press_target(T1)                                # confirm: the map is revealed
    pump(qapp, 0.3)
    w = app.window
    assert app.revealing and w.compact
    assert app.view.width() > w.width()                        # the map still gets most of the width
    assert not w.ring.isVisible()                              # the header says "✓ Shown and spoken"
    lines = wrapped_lines(w.preview, w.preview_px)
    assert len(lines) >= 1 and all(len(ln.split()) >= 2 for ln in lines[:-1]), lines
    for lbl in (w.input_label, w.round_label):
        assert lbl.sizeHint().width() <= lbl.width() + 1, lbl.text()
    out = w.outcome_label
    assert out.text().startswith("Last: Confirmed")
    assert out.heightForWidth(out.width()) <= out.height() + 1    # wraps instead of clipping
    assert w.strip.height() < size[1] * 0.2                        # and doesn't swallow the column
    app.close()
    app.root.close()


def test_next_question_restores_the_normal_layout(qapp):
    app = App(view=MapView(), speaker=Speaker(), echo=False, reveal_ms=60000)
    app.root.show()
    app.ask()
    app.window.press_target(T1)
    app.window.press_target(T1)
    assert app.window.compact
    app.ask()
    w = app.window
    assert not app.revealing and not w.compact
    assert all(t.isVisible() for t in w.tiles.values())
    assert w._strip_row1.indexOf(w.outcome_label) >= 0 and not w.outcome_label.wordWrap()
    app.close()
    app.root.close()
