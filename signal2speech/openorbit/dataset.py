"""OpenOrbit dataset for the comparison view (#30). Pure Python, no Qt.

Reads the verified files from data/openorbit/ (#29) and computes the AQI changes from the EPA
rows, so nothing on screen is hardcoded.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "openorbit"
BEFORE = "2023-06-26"
AFTER = "2023-06-28"
COUNTIES = ("Washtenaw", "Wayne")
REBUILD_HINT = "Run `python data/openorbit/build_dataset.py` to rebuild it (#29)."


@dataclass(frozen=True)
class Place:
    id: str
    label: str
    short: str
    county: str
    lat: float
    lon: float


@dataclass(frozen=True)
class CountyChange:
    county: str
    before: int
    after: int
    before_category: str
    after_category: str
    # The pollutant that set each day's county AQI (EPA "Defining Parameter"), e.g. Ozone, PM2.5.
    before_pollutant: str = ""
    after_pollutant: str = ""

    @property
    def change(self) -> int:
        return self.after - self.before


@dataclass(frozen=True)
class Dataset:
    root: Path
    images: Dict[str, Path]    # date -> image path
    bbox: Dict[str, float]     # west, south, east, north (EPSG:4326)
    width: int
    height: int
    layer: str
    places: Tuple[Place, ...]
    changes: Tuple[CountyChange, ...]  # in COUNTIES order
    #: Day-by-day frames for the satellite view: (date, short note), oldest first, ending on AFTER.
    #: Just (AFTER, "") when the extra days aren't in the data folder.
    timelapse: Tuple[Tuple[str, str], ...] = ()

    def to_pixel(self, lat: float, lon: float) -> Tuple[float, float]:
        """Image pixel for a lat/lon. The images are plain lat/lon grids (EPSG:4326)."""
        b = self.bbox
        x = (lon - b["west"]) / (b["east"] - b["west"]) * self.width
        y = (b["north"] - lat) / (b["north"] - b["south"]) * self.height
        return x, y

    def change_for(self, county: str) -> CountyChange:
        return next(c for c in self.changes if c.county == county)

    def largest_increase(self) -> CountyChange:
        return max(self.changes, key=lambda c: c.change)

    def highest_after(self) -> CountyChange:
        return max(self.changes, key=lambda c: c.after)

    def spoken_comparison(self) -> str:
        """The compare line, built from the data in the contract's wording
        ("Washtenaw's AQI rose 186 points. Wayne's rose 168 points."). Tests check it against
        contracts/demo-round.json, so the data and the spoken line can't drift apart."""
        parts = []
        for i, c in enumerate(self.changes):
            subject = f"{c.county}'s AQI" if i == 0 else f"{c.county}'s"
            verb = "rose" if c.change >= 0 else "fell"
            parts.append(f"{subject} {verb} {abs(c.change)} points.")
        return " ".join(parts)

    @property
    def nasa_credit(self) -> str:
        satellite = "Terra" if "Terra" in self.layer else "Aqua" if "Aqua" in self.layer else self.layer
        return f"Imagery: NASA GIBS / Worldview, MODIS {satellite} Corrected Reflectance"

    @property
    def epa_credit(self) -> str:
        return "Air quality: U.S. EPA AirData, daily AQI by county"


@dataclass(frozen=True)
class FirePoint:
    lat: float
    lon: float
    date: str


@dataclass(frozen=True)
class Fires:
    """Optional NASA FIRMS sample (#32): vegetation-fire detections over a wider region."""
    image: Path
    bbox: Dict[str, float]
    width: int
    height: int
    dates: Tuple[str, ...]
    points: Tuple[FirePoint, ...]   # type 0 ("presumed vegetation fire") only
    sensor: str

    def to_pixel(self, lat: float, lon: float) -> Tuple[float, float]:
        b = self.bbox
        return ((lon - b["west"]) / (b["east"] - b["west"]) * self.width,
                (b["north"] - lat) / (b["north"] - b["south"]) * self.height)

    @property
    def credit(self) -> str:
        return (f"Fire detections: NASA FIRMS, {self.sensor}. "
                "Each dot is a hot satellite pixel, not a fire outline.")


def load_fires(root: Optional[Path] = None) -> Optional[Fires]:
    """Load data/openorbit/firms/ if it's there. Returns None when it's missing or unreadable,
    so the core view never depends on it (#31)."""
    folder = (Path(root) if root is not None else DATA_DIR) / "firms"
    try:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        image = folder / summary["image"]["file"]
        if not image.is_file():
            return None
        with open(folder / summary["csv"], newline="", encoding="utf-8") as f:
            points = tuple(FirePoint(float(r["latitude"]), float(r["longitude"]), r["acq_date"])
                           for r in csv.DictReader(f) if r["type"] == "0")
        return Fires(image=image, bbox={k: float(v) for k, v in summary["bbox"].items()},
                     width=int(summary["image"]["width"]), height=int(summary["image"]["height"]),
                     dates=tuple(summary["dates"]), points=points,
                     sensor=summary.get("sensor", "VIIRS"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_dataset(root: Optional[Path] = None) -> Dataset:
    """Load data/openorbit/. Raises FileNotFoundError or ValueError with a rebuild hint."""
    root = Path(root) if root is not None else DATA_DIR
    places_path, rows_path = root / "places.json", root / "aqi_rows.csv"
    for path in (places_path, rows_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. {REBUILD_HINT}")

    meta = json.loads(places_path.read_text(encoding="utf-8"))
    images = {date: root / name for date, name in meta["images"].items()}
    for date in (BEFORE, AFTER):
        if date not in images or not images[date].exists():
            raise FileNotFoundError(f"Missing the {date} image in {root}. {REBUILD_HINT}")

    with open(rows_path, newline="", encoding="utf-8") as f:
        rows = {(r["county"], r["date"]): r for r in csv.DictReader(f)}
    changes = []
    for county in COUNTIES:
        try:
            before, after = rows[(county, BEFORE)], rows[(county, AFTER)]
        except KeyError as missing:
            raise ValueError(f"aqi_rows.csv has no row for {missing}. {REBUILD_HINT}") from None
        changes.append(CountyChange(county, int(before["aqi"]), int(after["aqi"]),
                                    before["category"], after["category"],
                                    before.get("defining_parameter", ""),
                                    after.get("defining_parameter", "")))

    places = tuple(Place(p["id"], p["label"], p.get("short", p["label"]), p["county"],
                         float(p["lat"]), float(p["lon"])) for p in meta["places"])
    frames = tuple((f["date"], f.get("note", "")) for f in meta.get("timelapse", [])
                   if f.get("date") in images and images[f["date"]].exists())
    if not frames or frames[-1][0] != AFTER:           # the sequence must end on the smoke image
        frames = ((AFTER, ""),)
    return Dataset(root=root, images=images, bbox={k: float(v) for k, v in meta["bbox"].items()},
                   width=int(meta["image"]["width"]), height=int(meta["image"]["height"]),
                   layer=meta.get("layer", ""), places=places, changes=tuple(changes),
                   timelapse=frames)
