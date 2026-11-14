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

## Known limits

- **June 26 is mostly cloud** on both MODIS Terra and Aqua, so the "before" image shows little ground. The AQI rows carry the before and after. The decision on this is deferred.
- **Stretched map:** the images are plain lat/lon grids, so they look about 1.35 times wider east to west than the ground really is.
- **No bundled audio:** the spoken lines use the offline Windows voice, because no `data/openorbit/audio/<action_id>.wav` is bundled.

## FIRMS fire detections (#8, #31, #32): research only, nothing built

- **The demo area has no wildfire hotspots.** Inside the southeast Michigan image bounds, NASA FIRMS has only a handful of detections on June 26 and 28, 2023. Nearly all are type 2 ("other static land source"), clustered around the River Rouge industrial area. So a hotspot layer on the current map would show factories, not wildfires.
- **The fires were in Quebec and Ontario,** more than 1,000 km away. On June 26 most detections were in central Quebec. NOAA's June 28 smoke bulletin puts the thickest smoke "from western Quebec through southern Ontario and into portions of the Midwestern and Upper Midwest". A useful hotspot view (#31) needs a wider "where the smoke came from" map. **That's a team decision** before anyone builds it.
- **Data without a key:**
  - The yearly country files need no key, for example `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-jpss1/2023/viirs-jpss1_2023_Canada.csv`. That one is about 138 MB, but one day is about 650 KB.
  - The area API needs a free `MAP_KEY` that is sent by email.
  - NASA GIBS also renders `VIIRS_NOAA20_Thermal_Anomalies_375m_All` as a transparent overlay for a date.
- **What a detection means:** a satellite pixel (375 m for VIIRS, 1 km for MODIS) with at least one hot spot in it, at a UTC time. It is not a fire outline, and it doesn't measure burned area. `type` 0 means a presumed vegetation fire.
- **Credit line:** "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's LANCE and ESDIS." Use "NASA FIRMS" in captions.
- **Still to verify (#32):** these counts come from a research pass. Re-count from the downloaded files before anything ships.
