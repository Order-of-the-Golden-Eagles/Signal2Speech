# OpenOrbit and Data

Use NASA MODIS imagery and EPA daily county AQI for June 26–28, 2023. FIRMS is a stretch layer.

**Active work** · [#7](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/7), [#8](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/8)

## What's built

| Piece | Where | Check it |
| --- | --- | --- |
| Verified dataset ([#29](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/29)) | `data/openorbit/`: two same-bounds MODIS images, `aqi_rows.csv`, `places.json`, and [`SOURCES.md`](../../data/openorbit/SOURCES.md) | `python data/openorbit/build_dataset.py --verify-only` (offline) |
| Comparison view ([#30](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/30)) | `signal2speech/openorbit/`: `OpenOrbitView` | `pytest tests/test_openorbit.py` |

- **In the app:** `load_view()` in `signal2speech/app.py` loads `OpenOrbitView` automatically. After a confirm, `AppSink` calls `show_satellite()` or `compare_air_quality()`. The view never speaks, uses no network, and never calls the selection handler. `perform(action_id)` and `reset()` are there too.
- **Computed, not typed in:** the changes come from the EPA rows. A test checks that they match the spoken line in `contracts/demo-round.json`, so the data and the speech can't drift apart.
- **Missing data:** if `data/openorbit/` is missing or broken, both actions show a labelled "OpenOrbit data missing (#29)" panel and the app keeps running.
- **Screen fit:** the view needs at least 442×423, so the app fits a 1920×1080 screen at 125% scaling.
- **Dev harness:** `python -m signal2speech.openorbit` (S satellite, C compare, R reset) is labelled "DEV HARNESS (no EEG)".

## Explaining the comparison (#7)

| County | June 26 | June 28 | Change |
| --- | ---: | ---: | ---: |
| Washtenaw | 32 (Good) | 218 (Very Unhealthy) | **+186** |
| Wayne | 58 (Moderate) | 226 (Very Unhealthy) | **+168** |

- **Biggest increase:** Washtenaw, +186, which is 18 more than Wayne.
- **Highest final AQI:** Wayne, 226 on June 28, which is 8 more than Washtenaw.
- **Timing:** the smoke arrived June 27 (Washtenaw 214, Wayne 186). June 28 was the worst day for both counties between June 24 and 30.
- **Two sources, two views:** NASA imagery shows the region from orbit. EPA AQI measures air quality at ground level. The view credits them on separate lines.

## Verified on 2026-11-14

Windows 11, Python 3.12, and the pinned `requirements-lock.txt`.

- **Real app, offline:** in `signal2speech.app` with keyboard input, every network call blocked inside Python, and audio muted, keys 2,1 give one `compare_air_quality()` and one spoken line. Keys 1,1 give one `show_satellite()` and one spoken line.
- **Merge check:** a test merge with `main`, #48, #21, and the `issue-5-ai` branch had no conflicts. `pytest` on the result: 102 passed, 2 skipped (the AI tests need the `anthropic` package).
- **Still to do:** a real Wi-Fi-off run on the judging laptop. See the [runbook](../devops/judging-build.md#judging-laptop-runbook-39).

## Day by day: June 24 to June 28 (2026-11-15)

Both map screens play five NASA MODIS Terra images, same bounds and size, one day flowing into the next and resting on June 28:

| Day | What the image shows | Caption |
| --- | --- | --- |
| June 24 | Broken cloud, ground and lakes visible | "before the smoke" |
| June 25, 26, 27 | Overcast | "mostly cloud" |
| June 28 | Grey smoke haze over the region | "wildfire smoke" |

- **Where:** `places.json` lists the frames under `timelapse`; `Dataset.timelapse` loads them and always ends on June 28. `OpenOrbitView` cross-fades through them once per reveal (`LAPSE_STEP_MS`, `LAPSE_FADE_MS`) and stops. It doesn't loop, because a moving picture next to the flashing tiles would pull the wearer's eyes.
- **The fire map** beside the satellite view shows only the detections up to the day on screen. Our FIRMS sample has detections for June 26 and June 28.
- **Images and numbers cover different days, and the screen says so.** The images start on June 24. The EPA numbers we hold are for June 26 and June 28, so the table and the spoken comparison use those two days. A line under the image states this.
- **The spoken satellite line** is now "NASA satellite images from June 24 to June 28, 2023: clear ground, then cloud, then wildfire smoke over southeast Michigan."
- **Before any confirm,** the panel shows the June 28 image at 30 % opacity with the two places marked and no numbers.
- Images are drawn in a rounded frame with a thin border.

## Known limits

- **June 25, 26 and 27 are mostly cloud** on MODIS Terra, and also on Aqua and VIIRS (checked 2026-11-15), so those days show little ground. The view captions each one "mostly cloud", and the [science note](science-note.md) explains it. June 24 is the last day the surface is visible before the smoke.
- **Stretched map:** the images are plain lat/lon grids, so they look about 1.35 times wider east to west than the ground really is.
- **Audio:** the comparison line has a bundled clip (`data/openorbit/audio/compare_air_quality.wav`) for machines without the natural voice. The satellite line no longer has one: its words changed when the view became a day-by-day sequence, and a clip must never say different words from the ones approved.

## FIRMS fire detections (#8, #31, #32)

**Built (optional layer):**

- **Data (#32):** `data/openorbit/firms/` holds the VIIRS NOAA-20 detections for June 26 and 28, 2023, from the Great Lakes to Quebec, plus a NASA image of that region. The counts and the meaning of a detection are in [`SOURCES.md`](../../data/openorbit/SOURCES.md#fire-detections-optional-32). `python data/openorbit/firms/build_firms.py --verify-only` checks the files offline.
- **View (#31):** "Show the satellite view" adds a second map, **Where the smoke came from**, beside the Michigan smoke image. Vegetation fires show as red dots (June 26) and yellow dots (June 28), and southeast Michigan is circled. The map has its own legend and a FIRMS credit line, and it never appears on the AQI comparison.
- **Optional by design:** if `data/openorbit/firms/` is missing or broken, the satellite view shows only the Michigan image, as before. The contract, the spoken lines, and `app.py` are unchanged. Tests cover a missing and a broken FIRMS folder.

**Research notes:**

- **The demo area has no wildfire hotspots.** Inside the southeast Michigan image bounds, NASA FIRMS has only a handful of detections on June 26 and 28, 2023. Nearly all are type 2 ("other static land source"), clustered around the River Rouge industrial area. So a hotspot layer on the current map would show factories, not wildfires.
- **The fires were mostly in Quebec,** at a median of about 1,340 km (86% of the 9,457 vegetation-fire detections). A few small detections were closer: 7 within 200 km, the nearest 84 km away. On June 26 most detections were in central Quebec. NOAA's June 28 smoke bulletin puts the thickest smoke "from western Quebec through southern Ontario and into portions of the Midwestern and Upper Midwest". That's why the hotspot view (#31) uses a wider "where the smoke came from" map.
- **Data without a key:**
  - The yearly country files need no key, for example `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-jpss1/2023/viirs-jpss1_2023_Canada.csv`. That one is about 138 MB, but one day is about 650 KB.
  - The area API needs a free `MAP_KEY` that is sent by email.
  - NASA GIBS also renders `VIIRS_NOAA20_Thermal_Anomalies_375m_All` as a transparent overlay for a date.
- **What a detection means:** a satellite pixel (375 m for VIIRS, 1 km for MODIS) with at least one hot spot in it, at a UTC time. It is not a fire outline, and it doesn't measure burned area. `type` 0 means a presumed vegetation fire.
- **Credit line:** "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's LANCE and ESDIS." Use "NASA FIRMS" in captions.
- **Verified (#32):** the research counts were re-counted from the downloaded files and match: 8 detections in the demo area on June 26 and 5 on June 28, all type 2. The June 26 Canada file has 7,959 rows.

**Science note (#153):** [science-note.md](science-note.md) covers what the MODIS images and daily county AQI are, which pollutant set each value (Washtenaw June 26 was ozone), and what the app does and doesn't claim. It's for the Beyond the Horizon judges.
