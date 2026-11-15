"""OpenOrbit comparison view (#30): NASA imagery and EPA county AQI, fully offline.

Only #25's sink calls this, on the Qt main thread, after a confirmed choice:

    if not view.perform(action.action_id):   # show_satellite or compare_air_quality
        ...                                  # not an OpenOrbit action (e.g. speak_reply)
    view.reset()                             # cancel, disconnect, or the next question

The view never plays audio, never uses the network, and never talks to the selection handler.
Speech stays in #25.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QStackedLayout,
                               QVBoxLayout, QWidget)

from signal2speech.core import ActionIds

from .dataset import AFTER, BEFORE, Dataset, Fires, Place, load_dataset, load_fires

BACKGROUND = "#101418"
TEXT = "#FFFFFF"
MUTED = "#C9D1D9"
MARKER = QColor("#FFD400")
LABEL_BOX = QColor(0, 0, 0, 185)
FIRE_COLORS = ("#FF453A", "#FFD60A")   # first and last FIRMS date
HOME_COLOR = "#00E5FF"                  # southeast Michigan on the regional fire map
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

# EPA AQI category colors, with readable text on each. The category name is always shown too,
# so color is never the only cue.
AQI_COLORS = {
    "Good": ("#00E400", "#000000"),
    "Moderate": ("#FFFF00", "#000000"),
    "Unhealthy for Sensitive Groups": ("#FF7E00", "#000000"),
    "Unhealthy": ("#FF0000", "#FFFFFF"),
    "Very Unhealthy": ("#8F3F97", "#FFFFFF"),
    "Hazardous": ("#7E0023", "#FFFFFF"),
}

BLANK_HINT = "The map appears after a confirmed choice."
#: How faint the idle picture is. Low enough that nobody takes it for the revealed map.
IDLE_OPACITY = 0.30
# Text sizes in px. They keep the view inside the app's output panel (#4) next to the selection
# tiles on a 1536x864 screen (1920x1080 at 125%). The images take the remaining space.
TITLE_PX, BODY_PX, SMALL_PX = 26, 17, 13


def _parts(iso: str) -> Tuple[int, int, int]:
    year, month, day = (int(p) for p in iso.split("-"))
    return year, month, day


def _month_day(iso: str) -> str:
    _, month, day = _parts(iso)
    return f"{MONTHS[month - 1]} {day}"


def _long_date(iso: str) -> str:
    return f"{_month_day(iso)}, {_parts(iso)[0]}"


def _short_date(iso: str) -> str:
    _, month, day = _parts(iso)
    return f"{MONTHS[month - 1][:3]} {day}"


def _label(text: str, px: int, color: str = TEXT, bold: bool = False,
           align=Qt.AlignLeft | Qt.AlignVCenter, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setPixelSize(px)
    font.setBold(bold)
    label.setFont(font)
    label.setStyleSheet(f"color: {color};")
    label.setAlignment(align)
    label.setWordWrap(wrap)
    return label


def _aqi_cell(aqi: int, category: str) -> QLabel:
    """AQI number on top, category below, in the EPA category color."""
    background, foreground = AQI_COLORS.get(category, ("#444C56", TEXT))
    label = QLabel(f"<div style='font-size:22px; font-weight:700;'>{aqi}</div>"
                   f"<div style='font-size:{SMALL_PX}px; font-weight:600;'>{html.escape(category)}</div>")
    label.setTextFormat(Qt.RichText)
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(True)
    label.setAccessibleName(f"{aqi} {category}")
    label.setStyleSheet(f"background-color: {background}; color: {foreground};"
                        " border-radius: 6px; padding: 2px 10px;")
    return label


def _clamp(box: QRectF, bounds: QRectF) -> QRectF:
    x = min(max(box.x(), bounds.left()), bounds.right() - box.width())
    y = min(max(box.y(), bounds.top()), bounds.bottom() - box.height())
    return QRectF(x, y, box.width(), box.height())


class MapImage(QWidget):
    """One satellite image, scaled to fit with its aspect ratio kept, with a date caption and
    labelled place markers drawn on top."""

    def __init__(self, dataset: Dataset, date: str, caption: Optional[str] = None,
                 parent: Optional[QWidget] = None, caption_short: Optional[str] = None):
        super().__init__(parent)
        self._ds = dataset
        self.date = date
        self.caption = caption
        self.caption_short = caption_short    # used when the full caption won't fit the image
        self._pixmap = QPixmap(str(dataset.images[date]))
        self.opacity = 1.0                    # below 1 draws the whole map faintly (idle panel, #182)
        self.setMinimumSize(200, 111)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def image_rect(self) -> QRectF:
        scale = min(self.width() / self._ds.width, self.height() / self._ds.height)
        w, h = self._ds.width * scale, self._ds.height * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def marker_points(self) -> List[Tuple[Place, QPointF]]:
        r = self.image_rect()
        points = []
        for place in self._ds.places:
            x, y = self._ds.to_pixel(place.lat, place.lon)
            points.append((place, QPointF(r.x() + x * r.width() / self._ds.width,
                                          r.y() + y * r.height() / self._ds.height)))
        return points

    def _font(self, px: float, minimum: int = 13) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(minimum, int(px)))
        font.setBold(True)
        return font

    def caption_text(self) -> Optional[str]:
        """The caption that fits: the full one, else the short one (never wider than the image)."""
        if not self.caption:
            return None
        r = self.image_rect()
        metrics = QFontMetricsF(self._font(r.height() / 18))
        if self.caption_short and metrics.horizontalAdvance(self.caption) + 32 > r.width():
            return self.caption_short
        return self.caption

    def caption_layout(self) -> Optional[Tuple[QFont, QRectF]]:
        text = self.caption_text()
        if not text:
            return None
        r = self.image_rect()
        font = self._font(r.height() / 18)
        metrics = QFontMetricsF(font)
        box = QRectF(r.left() + 8, r.top() + 8,
                     metrics.horizontalAdvance(text) + 16, metrics.height() + 6)
        return font, box

    def marker_radius(self) -> float:
        return max(6.0, self.image_rect().height() / 60)

    def label_layout(self) -> Tuple[QFont, float, List[Tuple[Place, QPointF, QRectF, str]]]:
        """Marker labels: each sits next to its own marker, inside the image, without covering
        another label, any marker, or the caption. If they don't all fit, fall back to short
        labels, then a smaller font, then leave out the labels that still don't fit. Markers
        are always drawn, so a misleading label is never drawn."""
        r = self.image_rect()
        base = r.height() / 22
        attempts = ((self._font(base), True), (self._font(base), False),
                    (self._font(base * 0.8, minimum=11), False))
        for font, with_county in attempts:
            labels = self._place_labels(font, with_county)
            if all(box is not None for _, _, box, _ in labels):
                break
        return font, self.marker_radius(), [l for l in labels if l[2] is not None]

    def _place_labels(self, font: QFont, with_county: bool):
        r = self.image_rect()
        metrics = QFontMetricsF(font)
        radius = self.marker_radius()
        points = self.marker_points()
        taken = [QRectF(p.x() - radius - 2, p.y() - radius - 2, 2 * radius + 4, 2 * radius + 4)
                 for _, p in points]
        caption = self.caption_layout()
        if caption:
            taken.append(caption[1])
        labels = []
        for place, p in points:
            text = f"{place.short} ({place.county})" if with_county else place.short
            w, h = metrics.horizontalAdvance(text) + 12, metrics.height() + 4
            gap = radius + 4
            candidates = (QRectF(p.x() - w / 2, p.y() - gap - h, w, h),   # above
                          QRectF(p.x() - w / 2, p.y() + gap, w, h),       # below
                          QRectF(p.x() + gap, p.y() - h / 2, w, h),       # right
                          QRectF(p.x() - gap - w, p.y() - h / 2, w, h))   # left
            box = None
            if w <= r.width() and h <= r.height():
                for candidate in candidates:
                    c = _clamp(candidate, r)
                    others = [q for _, q in points if q != p]
                    nearest_is_own = all((c.center() - p).manhattanLength()
                                         < (c.center() - q).manhattanLength() for q in others)
                    if nearest_is_own and not any(c.intersects(t) for t in taken):
                        box = c
                        break
            if box is not None:
                taken.append(box)
            labels.append((place, p, box, text))
        return labels

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setOpacity(self.opacity)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.image_rect()
        if self._pixmap.isNull():
            painter.setPen(QColor(TEXT))
            painter.drawText(r, Qt.AlignCenter, f"Image missing: {self.date}")
            painter.end()
            return
        painter.drawPixmap(r, self._pixmap, QRectF(self._pixmap.rect()))

        caption = self.caption_layout()
        if caption:
            font, box = caption
            painter.setFont(font)
            self._draw_box_text(painter, box, self.caption_text())

        font, radius, labels = self.label_layout()
        for _, point in self.marker_points():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("black"), 5))
            painter.drawEllipse(point, radius, radius)
            painter.setPen(QPen(MARKER, 3))
            painter.drawEllipse(point, radius, radius)
        painter.setFont(font)
        for _, _, box, text in labels:
            self._draw_box_text(painter, box, text)
        painter.end()

    @staticmethod
    def _draw_box_text(painter: QPainter, box: QRectF, text: str) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(LABEL_BOX)
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor(TEXT))
        painter.drawText(box, Qt.AlignCenter, text)


class FiresMap(QWidget):
    """Optional (#31): NASA FIRMS vegetation-fire detections drawn over the June 28 regional image,
    with southeast Michigan marked so viewers can see how far the smoke travelled."""

    def __init__(self, fires: Fires, home: Tuple[float, float], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._fires = fires
        self._home = home
        self._pixmap = QPixmap(str(fires.image))
        self._colors = {date: QColor(FIRE_COLORS[min(i, len(FIRE_COLORS) - 1)])
                        for i, date in enumerate(fires.dates)}
        self.setMinimumSize(200, 107)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def image_rect(self) -> QRectF:
        scale = min(self.width() / self._fires.width, self.height() / self._fires.height)
        w, h = self._fires.width * scale, self._fires.height * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _point(self, lat: float, lon: float) -> QPointF:
        r = self.image_rect()
        x, y = self._fires.to_pixel(lat, lon)
        return QPointF(r.x() + x * r.width() / self._fires.width, r.y() + y * r.height() / self._fires.height)

    def dot_points(self) -> List[Tuple[str, QPointF]]:
        return [(p.date, self._point(p.lat, p.lon)) for p in self._fires.points]

    def home_point(self) -> QPointF:
        return self._point(*self._home)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.image_rect()
        if self._pixmap.isNull():
            painter.setPen(QColor(TEXT))
            painter.drawText(r, Qt.AlignCenter, "Fire map image missing")
            painter.end()
            return
        painter.drawPixmap(r, self._pixmap, QRectF(self._pixmap.rect()))
        dot = max(1.2, r.width() / 450)
        painter.setPen(Qt.NoPen)
        for date, point in self.dot_points():
            painter.setBrush(self._colors.get(date, QColor(FIRE_COLORS[0])))
            painter.drawEllipse(point, dot, dot)

        home, radius = self.home_point(), max(5.0, r.height() / 45)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("black"), 5))
        painter.drawEllipse(home, radius, radius)
        painter.setPen(QPen(QColor(HOME_COLOR), 3))
        painter.drawEllipse(home, radius, radius)
        font = QFont(self.font())
        font.setPixelSize(max(12, int(r.height() / 16)))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        text = "SE Michigan"
        w, h = metrics.horizontalAdvance(text) + 12, metrics.height() + 4
        box = _clamp(QRectF(home.x() - w / 2, home.y() - radius - 4 - h, w, h), r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(LABEL_BOX)
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor(TEXT))
        painter.drawText(box, Qt.AlignCenter, text)
        painter.end()


class OpenOrbitView(QWidget):
    """Blank until a confirmed OpenOrbit action. Exposes both action IDs from the contract.

    If the #29 data is missing or unreadable, the view still builds (so the app never crashes)
    and both actions show a clearly labelled "data missing" panel instead of a map.
    """

    ACTION_IDS = (ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY)
    MODES = ("blank", "satellite", "compare")

    def __init__(self, dataset: Optional[Dataset] = None, parent: Optional[QWidget] = None, *,
                 data_root: Optional[Path] = None, with_fires: bool = True):
        super().__init__(parent)
        self.data_error: Optional[str] = None
        if dataset is None:
            try:
                dataset = load_dataset(data_root)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.data_error = str(exc) or type(exc).__name__
        self.dataset = dataset
        # Optional FIRMS layer (#31). Missing or broken files just mean no fire map.
        self.fires: Optional[Fires] = (load_fires(dataset.root)
                                       if dataset is not None and with_fires else None)
        self.setObjectName("OpenOrbitView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#OpenOrbitView {{ background-color: {BACKGROUND}; }}")
        if self.data_error is None:
            satellite, compare = self._build_satellite(), self._build_compare()
        else:
            satellite = compare = self._build_missing(self.data_error)
        self._pages = {"blank": self._build_blank(), "satellite": satellite, "compare": compare}
        self._stack = QStackedLayout(self)
        for page in dict.fromkeys(self._pages.values()):
            self._stack.addWidget(page)
        self._mode = "blank"
        self.reset()

    @property
    def mode(self) -> str:
        return self._mode

    def perform(self, action_id: str) -> bool:
        """Run an OpenOrbit action. Returns False for any other action ID."""
        run = {ActionIds.SHOW_SATELLITE: self.show_satellite,
               ActionIds.COMPARE_AIR_QUALITY: self.compare_air_quality}.get(action_id)
        if run is None:
            return False
        run()
        return True

    def show_satellite(self) -> None:
        """June 28 NASA MODIS view with the EMU and Detroit markers."""
        self._show("satellite")

    def compare_air_quality(self) -> None:
        """June 26 and June 28 imagery plus the county AQI comparison."""
        self._show("compare")

    def reset(self) -> None:
        """Blank panel for cancel, disconnect, or the next question."""
        self._show("blank")

    def _show(self, mode: str) -> None:
        self._mode = mode
        self._stack.setCurrentWidget(self._pages[mode])

    @staticmethod
    def _page() -> Tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(6)
        return page, layout

    def _build_blank(self) -> QWidget:
        """Before any confirm: a dimmed look at the region, so the panel isn't an empty box (#182).
        It is plainly not the reveal: it is faint, has no data on it, and says what it's waiting for."""
        page, layout = self._page()
        ds = self.dataset
        if ds is None or self.data_error is not None:
            layout.addStretch(1)
            layout.addWidget(_label(BLANK_HINT, SMALL_PX + 2, MUTED, align=Qt.AlignCenter))
            layout.addStretch(1)
            return page
        layout.addWidget(_label("Wildfire smoke over southeast Michigan", TITLE_PX, MUTED, bold=True))
        layout.addWidget(_label(f"{_long_date(BEFORE)} and {_long_date(AFTER)}  ·  NASA satellite imagery "
                                "and EPA air quality", SMALL_PX + 2, MUTED))
        self.idle_image = MapImage(ds, AFTER)
        # Drawn faintly by the painter itself. A graphics effect on this custom-painted widget
        # crashed the test run on macOS (bus error).
        self.idle_image.opacity = IDLE_OPACITY
        layout.addWidget(self.idle_image, 1)
        layout.addWidget(_label(BLANK_HINT, BODY_PX, MUTED, align=Qt.AlignCenter))
        layout.addWidget(_label(ds.nasa_credit, SMALL_PX, MUTED))
        return page

    def _build_missing(self, error: str) -> QWidget:
        page, layout = self._page()
        box = QLabel(f"<b>OpenOrbit data missing (#29)</b><br><br>{html.escape(error)}")
        box.setTextFormat(Qt.RichText)
        box.setWordWrap(True)
        box.setStyleSheet(f"color: {TEXT}; font-size: {BODY_PX}px; border: 3px dashed #F59E0B;"
                          " border-radius: 14px; padding: 16px;")
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _build_satellite(self) -> QWidget:
        ds = self.dataset
        page, layout = self._page()
        layout.addWidget(_label("Southeast Michigan under wildfire smoke", TITLE_PX, bold=True))
        if self.fires is None:
            layout.addWidget(MapImage(ds, AFTER, caption=_long_date(AFTER)), 1)
            layout.addWidget(_label(ds.nasa_credit, SMALL_PX, MUTED))
            return page

        # With the optional FIRMS sample: the fire map sits beside the smoke image, under its
        # own heading, legend, and credit, so detections are never mixed up with smoke or AQI.
        home = (sum(p.lat for p in ds.places) / len(ds.places), sum(p.lon for p in ds.places) / len(ds.places))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.addWidget(_label("Smoke over the demo counties", BODY_PX, bold=True), 0, 0)
        grid.addWidget(_label("Where the smoke came from", BODY_PX, bold=True), 0, 1)
        grid.addWidget(MapImage(ds, AFTER, caption=_long_date(AFTER)), 1, 0)
        grid.addWidget(FiresMap(self.fires, home), 1, 1)
        swatches = "&nbsp;&nbsp;".join(
            f"<span style='color:{FIRE_COLORS[min(i, len(FIRE_COLORS) - 1)]}'>&#9679;</span> {_long_date(d)}"
            for i, d in enumerate(self.fires.dates))
        legend = QLabel(f"Vegetation fires detected: {swatches}&nbsp;&nbsp;"
                        f"<span style='color:{HOME_COLOR}'>&#9711;</span> Southeast Michigan")
        legend.setTextFormat(Qt.RichText)
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color: {MUTED}; font-size: {SMALL_PX}px;")
        grid.addWidget(legend, 2, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid, 1)
        layout.addWidget(_label(ds.nasa_credit, SMALL_PX, MUTED))
        layout.addWidget(_label(self.fires.credit, SMALL_PX, MUTED))
        return page

    def _build_compare(self) -> QWidget:
        ds = self.dataset
        page, layout = self._page()
        layout.addWidget(_label("Wildfire smoke: before and after", TITLE_PX, bold=True))

        images = QHBoxLayout()
        images.setSpacing(10)
        for date in (BEFORE, AFTER):
            # June 26 was overcast for both MODIS satellites: the white is cloud, not clear air (#153).
            caption = _long_date(date) + (" · mostly cloud" if date == BEFORE else "")
            images.addWidget(MapImage(ds, date, caption=caption,
                                      caption_short=_long_date(date)), 1)
        layout.addLayout(images, 1)
        layout.addWidget(_label(ds.nasa_credit, SMALL_PX, MUTED))

        layout.addWidget(self._aqi_table())
        for line in self._summary_lines():
            layout.addWidget(_label(line, BODY_PX))
        layout.addWidget(_label(ds.epa_credit, SMALL_PX, MUTED))
        return page

    def _aqi_table(self) -> QWidget:
        ds = self.dataset
        table = QWidget()
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        headers = ("County", f"{_short_date(BEFORE)} AQI", f"{_short_date(AFTER)} AQI", "Change")
        for col, text in enumerate(headers):
            align = Qt.AlignLeft | Qt.AlignVCenter if col == 0 else Qt.AlignCenter
            grid.addWidget(_label(text, 14, MUTED, bold=True, align=align, wrap=False), 0, col)
        for row, c in enumerate(ds.changes, start=1):
            grid.addWidget(_label(c.county, 20, bold=True, wrap=False), row, 0)
            grid.addWidget(_aqi_cell(c.before, c.before_category), row, 1)
            grid.addWidget(_aqi_cell(c.after, c.after_category), row, 2)
            grid.addWidget(_label(f"{c.change:+d}", 24, bold=True, align=Qt.AlignCenter, wrap=False), row, 3)
        grid.setColumnStretch(4, 1)
        return table

    def _summary_lines(self) -> List[str]:
        """Largest increase vs highest final AQI, computed (#7 asks a teammate to explain both)."""
        ds = self.dataset
        if len(ds.changes) < 2:
            return []
        by_change = sorted(ds.changes, key=lambda c: c.change, reverse=True)
        by_after = sorted(ds.changes, key=lambda c: c.after, reverse=True)
        top, runner = by_change[0], by_change[1]
        first = (f"Biggest jump: {top.county}, {top.change:+d} "
                 f"({top.change - runner.change} more than {runner.county}).")
        top, runner = by_after[0], by_after[1]
        second = (f"Highest {_short_date(AFTER)} AQI: {top.county}, {top.after} "
                  f"({top.after - runner.after} more than {runner.county}).")
        lines = [first, second]
        pollutants = self._pollutant_line()
        return lines + ([pollutants] if pollutants else [])

    def _pollutant_line(self) -> str:
        """Which pollutant set each county AQI, when it isn't the same everywhere (#153).

        Says nothing if any value's pollutant is unknown, so it never claims "all" falsely.
        Ties go to the alphabetically first pollutant, so the text is the same every run.
        """
        ds = self.dataset
        cells = [(c.county, d, p) for c in ds.changes
                 for d, p in ((BEFORE, c.before_pollutant), (AFTER, c.after_pollutant))]
        if not cells or any(not p for _, _, p in cells):
            return ""
        kinds = sorted({p for _, _, p in cells})
        if len(kinds) < 2:
            return ""
        common = min(kinds, key=lambda k: (-sum(p == k for _, _, p in cells), k))
        odd = [f"{county} {_short_date(d)} ({p})" for county, d, p in cells if p != common]
        return (f"Each county AQI is set by its highest pollutant AQI that day: "
                f"{common} for all values except {', '.join(odd)}.")


__all__ = ["FiresMap", "MapImage", "OpenOrbitView"]
