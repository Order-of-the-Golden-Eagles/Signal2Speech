"""Build and verify the OpenOrbit demo dataset (#29). Standard library only.

    python data/openorbit/build_dataset.py              # download, extract, verify
    python data/openorbit/build_dataset.py --verify-only  # offline check of committed files

Downloads two same-bounds NASA GIBS MODIS images (June 26 and 28, 2023) and the EPA AirData
2023 daily county AQI file, keeps the Washtenaw and Wayne rows for those days, and checks them
against the values the team quotes (README, docs/MEMORY.md). The EPA zip goes to raw/, which
is gitignored.
"""
import argparse
import csv
import io
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

DATES = ("2023-06-26", "2023-06-28")
COUNTIES = ("Washtenaw", "Wayne")
# Values quoted in README.md and docs/MEMORY.md. The script refuses to write data that disagrees.
EXPECTED_AQI = {
    ("Washtenaw", "2023-06-26"): 32,
    ("Washtenaw", "2023-06-28"): 218,
    ("Wayne", "2023-06-26"): 58,
    ("Wayne", "2023-06-28"): 226,
}

# Southeast Michigan, EPSG:4326. WMS 1.3.0 with EPSG:4326 takes BBOX as lat,lon (south,west,north,east).
BBOX = {"west": -84.4, "south": 41.8, "east": -82.6, "north": 42.8}
WIDTH, HEIGHT = 1440, 800  # 0.00125 degrees per pixel on both axes
DEFAULT_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"
GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
EPA_ZIP_URL = "https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2023.zip"

AQI_FIELDS = ["date", "state", "county", "aqi", "category", "defining_parameter",
              "defining_site", "sites_reporting"]


def image_name(date):
    return f"modis_{date}.jpg"


def gibs_url(date, layer):
    bbox = f"{BBOX['south']},{BBOX['west']},{BBOX['north']},{BBOX['east']}"
    return (f"{GIBS_WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES="
            f"&CRS=EPSG:4326&BBOX={bbox}&WIDTH={WIDTH}&HEIGHT={HEIGHT}&FORMAT=image/jpeg&TIME={date}")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dataset-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.headers.get("Content-Type", ""), resp.read()


def jpeg_size(data):
    """(width, height) from a JPEG's SOF marker, without Pillow."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("bad JPEG marker")
        marker = data[i + 1]
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    raise ValueError("no SOF marker")


def download_images(layer):
    for date in DATES:
        ctype, data = fetch(gibs_url(date, layer))
        if not ctype.startswith("image/jpeg"):
            raise SystemExit(f"GIBS returned {ctype} for {date}: {data[:300]!r}")
        (HERE / image_name(date)).write_bytes(data)
        print(f"saved {image_name(date)} ({len(data) // 1024} KB, {jpeg_size(data)})")


def extract_aqi_rows():
    RAW.mkdir(exist_ok=True)
    zip_path = RAW / Path(EPA_ZIP_URL).name
    if not zip_path.exists():
        _, data = fetch(EPA_ZIP_URL)
        zip_path.write_bytes(data)
        print(f"saved raw/{zip_path.name} ({len(data) // 1024} KB)")
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8", newline="")
        rows = []
        for r in csv.DictReader(text):
            if (r["State Name"] == "Michigan" and r["county Name"] in COUNTIES
                    and r["Date"] in DATES):
                rows.append({
                    "date": r["Date"], "state": r["State Name"], "county": r["county Name"],
                    "aqi": r["AQI"], "category": r["Category"],
                    "defining_parameter": r["Defining Parameter"],
                    "defining_site": r["Defining Site"],
                    "sites_reporting": r["Number of Sites Reporting"],
                })
    rows.sort(key=lambda r: (r["county"], r["date"]))
    return rows


def require(ok, message):
    """Explicit check that still runs under `python -O` (unlike assert)."""
    if not ok:
        raise SystemExit("FAILED: " + message)


def check_rows(rows):
    keys = sorted((r["county"], r["date"]) for r in rows)
    require(keys == sorted(EXPECTED_AQI), f"expected one row per county and date, got {keys}")
    found = {(r["county"], r["date"]): int(r["aqi"]) for r in rows}
    if found != EXPECTED_AQI:
        print("AQI MISMATCH. Expected:", EXPECTED_AQI)
        print("Found:   ", found)
        raise SystemExit("Stop: the team's quoted values disagree with EPA. Do not commit; raise it in #29.")
    for county in COUNTIES:
        before, after = found[(county, DATES[0])], found[(county, DATES[1])]
        print(f"{county}: {before} -> {after} (+{after - before})")


def write_rows(rows):
    with open(HERE / "aqi_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=AQI_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("saved aqi_rows.csv")


def write_places(layer):
    places = json.loads((HERE / "places.json").read_text(encoding="utf-8"))
    places.update({"crs": "EPSG:4326", "bbox": BBOX, "image": {"width": WIDTH, "height": HEIGHT},
                   "layer": layer, "images": {d: image_name(d) for d in DATES}})
    (HERE / "places.json").write_text(json.dumps(places, indent=2) + "\n", encoding="utf-8")
    print("updated places.json")


def verify_committed():
    """Offline check that the committed files are complete and consistent."""
    with open(HERE / "aqi_rows.csv", newline="", encoding="utf-8") as f:
        check_rows(list(csv.DictReader(f)))
    places = json.loads((HERE / "places.json").read_text(encoding="utf-8"))
    require(places["bbox"] == BBOX, "places.json bbox differs from the download bbox")
    sizes = set()
    for date in DATES:
        data = (HERE / places["images"][date]).read_bytes()
        sizes.add(jpeg_size(data))
        require(len(data) < 1_000_000, f"{date} image is over 1 MB")
    require(sizes == {(places["image"]["width"], places["image"]["height"])}, f"image sizes differ: {sizes}")
    for p in places["places"]:
        inside = BBOX["south"] < p["lat"] < BBOX["north"] and BBOX["west"] < p["lon"] < BBOX["east"]
        require(inside, f"{p['id']} is outside the image bounds")
    print("verify-only: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-only", action="store_true", help="check committed files, no network")
    ap.add_argument("--layer", default=DEFAULT_LAYER, help="GIBS layer (e.g. MODIS_Aqua_CorrectedReflectance_TrueColor)")
    args = ap.parse_args(argv)
    if not args.verify_only:
        rows = extract_aqi_rows()
        check_rows(rows)
        write_rows(rows)
        download_images(args.layer)
        write_places(args.layer)
    verify_committed()


if __name__ == "__main__":
    sys.exit(main())
