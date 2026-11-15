"""Build and verify the NASA FIRMS fire-detection sample (#32) for the optional
"where the smoke came from" panel (#31). Standard library only.

    python data/openorbit/firms/build_firms.py               # download, filter, verify
    python data/openorbit/firms/build_firms.py --verify-only # offline check of committed files

Source: NASA FIRMS yearly country files for VIIRS NOAA-20 (375 m), which need no key. Each file
is sorted by date, so the script binary-searches it with HTTP byte ranges and downloads only the
demo dates (about 1 MB instead of 170 MB). The background image is NASA GIBS MODIS Terra for
June 28 over the same box.
"""
import argparse
import csv
import io
import json
import struct
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "dataset-fetch/1.0"}

DATES = ("2023-06-26", "2023-06-28")              # the demo's before and after days
COUNTRIES = ("Canada", "United_States")
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-jpss1/2023/viirs-jpss1_2023_{}.csv"
# Great Lakes to Quebec: where the smoke came from, with southeast Michigan inside it.
BBOX = {"west": -95.0, "south": 40.0, "east": -65.0, "north": 56.0}
WIDTH, HEIGHT = 1200, 640                         # 0.025 degrees per pixel on both axes
# The demo's own image bounds (data/openorbit/places.json), for the "no wildfires here" check.
DEMO_BBOX = {"west": -84.4, "south": 41.8, "east": -82.6, "north": 42.8}
GIBS = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap"
        "&VERSION=1.3.0&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor&STYLES=&CRS=EPSG:4326"
        "&BBOX={s},{w},{n},{e}&WIDTH={W}&HEIGHT={H}&FORMAT=image/jpeg&TIME={t}")

CSV_NAME = "viirs_noaa20_2023-06-26_28.csv"
IMAGE_NAME = "region_2023-06-28.jpg"
SUMMARY_NAME = "summary.json"
FIELDS = ["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp", "daynight", "type", "country"]
TYPES = {"0": "presumed vegetation fire", "1": "active volcano", "2": "other static land source", "3": "offshore"}


def fetch(url, start=None, end=None):
    headers = dict(UA)
    if start is not None:
        headers["Range"] = f"bytes={start}-{end}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
        return r.headers, r.read()


def total_size(url):
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60) as r:
        return int(r.headers["Content-Length"])


def date_at(url, offset, date_col):
    """(start offset, acq_date) of the first full line at or after offset."""
    _, chunk = fetch(url, offset, offset + 4095)
    nl = chunk.find(b"\n")
    line_start = offset + nl + 1
    line = chunk[nl + 1:].split(b"\n", 1)[0].decode("utf-8")
    return line_start, (line.split(",")[date_col] if line else "9999-99-99")


def first_offset(url, size, header_len, date_col, date):
    """Byte offset of the first row whose acq_date >= date (rows are sorted by date)."""
    lo, hi = header_len, size
    while hi - lo > 4096:
        mid = (lo + hi) // 2
        _, found = date_at(url, mid, date_col)
        if found < date:
            lo = mid
        else:
            hi = mid
    start, found = date_at(url, lo - 1, date_col) if lo > header_len else (header_len, "")
    # walk forward line by line from lo to the exact first row >= date
    _, chunk = fetch(url, lo, min(size - 1, lo + 65535))
    pos = lo
    lines = chunk.split(b"\n")
    if lo > header_len:
        pos += len(lines[0]) + 1
        lines = lines[1:]
    for line in lines:
        text = line.decode("utf-8")
        if text and text.split(",")[date_col] >= date:
            return pos
        pos += len(line) + 1
    return pos


def rows_for(country):
    url = FIRMS_URL.format(country)
    size = total_size(url)
    _, head = fetch(url, 0, 1023)
    header = head.split(b"\n", 1)[0].decode("utf-8").split(",")
    header_len = len(head.split(b"\n", 1)[0]) + 1
    date_col = header.index("acq_date")
    rows = []
    for date in DATES:
        start = first_offset(url, size, header_len, date_col, date)
        next_day = date[:-2] + f"{int(date[-2:]) + 1:02d}"
        end = first_offset(url, size, header_len, date_col, next_day)
        _, body = fetch(url, start, end - 1)
        for rec in csv.DictReader(io.StringIO(body.decode("utf-8")), fieldnames=header):
            if rec["acq_date"] != date:
                raise SystemExit(f"{country}: byte range for {date} returned a {rec['acq_date']} row")
            rows.append(rec)
        print(f"{country} {date}: {body.count(b'\n')} rows downloaded ({len(body) // 1024} KB)")
    return rows


def inside(lat, lon, box):
    return box["south"] <= lat <= box["north"] and box["west"] <= lon <= box["east"]


def jpeg_size(data):
    i = 2
    while i < len(data):
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    raise ValueError("no SOF marker")


def summarize(rows):
    summary = {"dates": list(DATES), "bbox": BBOX, "sensor": "VIIRS NOAA-20 375 m",
               "counts": {}, "demo_area": {}}
    for date in DATES:
        day = [r for r in rows if r["acq_date"] == date]
        veg = [r for r in day if r["type"] == "0"]
        summary["counts"][date] = {"all": len(day), "vegetation_fires": len(veg),
                                   "vegetation_fires_east_of_79_5W": sum(float(r["longitude"]) > -79.5 for r in veg)}
        demo = [r for r in day if inside(float(r["latitude"]), float(r["longitude"]), DEMO_BBOX)]
        summary["demo_area"][date] = {"all": len(demo), "by_type": {t: sum(r["type"] == t for r in demo)
                                                                    for t in sorted({r["type"] for r in demo})}}
    return summary


def build():
    rows = []
    for country in COUNTRIES:
        for rec in rows_for(country):
            lat, lon = float(rec["latitude"]), float(rec["longitude"])
            if inside(lat, lon, BBOX):
                rows.append({"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "acq_date": rec["acq_date"],
                             "acq_time": rec["acq_time"], "confidence": rec["confidence"], "frp": rec["frp"],
                             "daynight": rec["daynight"], "type": rec["type"], "country": country.replace("_", " ")})
    rows.sort(key=lambda r: (r["acq_date"], r["acq_time"], r["latitude"], r["longitude"]))
    with open(HERE / CSV_NAME, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    url = GIBS.format(s=BBOX["south"], w=BBOX["west"], n=BBOX["north"], e=BBOX["east"], W=WIDTH, H=HEIGHT, t=DATES[-1])
    headers, image = fetch(url)
    if not headers.get("Content-Type", "").startswith("image/jpeg"):
        raise SystemExit(f"GIBS returned {headers.get('Content-Type')}: {image[:200]!r}")
    (HERE / IMAGE_NAME).write_bytes(image)
    summary = summarize(rows)
    summary["csv"] = CSV_NAME
    summary["image"] = {"file": IMAGE_NAME, "width": WIDTH, "height": HEIGHT,
                        "layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "date": DATES[-1]}
    (HERE / SUMMARY_NAME).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"saved {CSV_NAME} ({len(rows)} rows), {IMAGE_NAME}, {SUMMARY_NAME}")


def require(ok, message):
    if not ok:
        raise SystemExit("FAILED: " + message)


def verify():
    with open(HERE / CSV_NAME, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    require(rows, "no rows")
    for r in rows:
        require(r["acq_date"] in DATES, f"unexpected date {r['acq_date']}")
        require(inside(float(r["latitude"]), float(r["longitude"]), BBOX), f"outside the box: {r}")
        require(r["type"] in TYPES and r["confidence"] in ("l", "n", "h"), f"bad type or confidence: {r}")
        require(r["daynight"] in ("D", "N"), f"bad daynight: {r}")
    summary = json.loads((HERE / SUMMARY_NAME).read_text(encoding="utf-8"))
    require(summary.get("csv") == CSV_NAME and summary["image"]["file"] == IMAGE_NAME, "summary.json file names")
    recount = summarize(rows)
    require(summary["counts"] == recount["counts"] and summary["demo_area"] == recount["demo_area"],
            "summary.json doesn't match the CSV")
    data = (HERE / IMAGE_NAME).read_bytes()
    require(jpeg_size(data) == (WIDTH, HEIGHT), "image size differs")
    require((HERE / CSV_NAME).stat().st_size < 1_000_000 and len(data) < 1_000_000, "a file is over 1 MB")
    for date, c in summary["counts"].items():
        print(f"{date}: {c['all']} detections, {c['vegetation_fires']} vegetation fires "
              f"({c['vegetation_fires_east_of_79_5W']} east of 79.5 W); demo area: {summary['demo_area'][date]}")
    print("verify-only: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-only", action="store_true", help="check committed files, no network")
    args = ap.parse_args(argv)
    if not args.verify_only:
        build()
    verify()


if __name__ == "__main__":
    sys.exit(main())
