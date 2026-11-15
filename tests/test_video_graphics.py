"""Video graphics (#132): the three cards exist at 1920x1080 and stay small."""
import struct
from pathlib import Path

import pytest

MEDIA = Path(__file__).resolve().parents[1] / "docs" / "demo-submission" / "media"


@pytest.mark.parametrize("name", ["title-card.png", "closing-card.png", "architecture.png"])
def test_card_is_a_small_1080p_png(name):
    data = (MEDIA / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])          # IHDR
    assert (width, height) == (1920, 1080)
    assert len(data) < 500_000


def test_shot_list_links_every_card():
    text = (MEDIA.parent / "shot-list.md").read_text(encoding="utf-8")
    for name in ("title-card.png", "closing-card.png", "architecture.png"):
        assert f"media/{name}" in text
