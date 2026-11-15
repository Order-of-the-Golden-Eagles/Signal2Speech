# OpenOrbit dataset sources (#29)

Retrieved 2026-11-14 with [`build_dataset.py`](build_dataset.py). Rebuild with `python data/openorbit/build_dataset.py`, or check the committed files offline with `--verify-only`.

## Air quality (ground level)

**Attribution:** U.S. EPA AirData, daily AQI by county, 2023.
**Source:** <https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2023.zip> (the zip stays in the gitignored `raw/` folder).
**File:** [`aqi_rows.csv`](aqi_rows.csv), 4 rows filtered to Michigan, Washtenaw and Wayne, June 26 and 28, 2023.

| County | June 26 | June 28 | Change | June 28 category | June 28 defining pollutant |
| --- | ---: | ---: | ---: | --- | --- |
| Washtenaw | 32 (Good) | 218 | **+186** | Very Unhealthy | PM2.5 |
| Wayne | 58 (Moderate) | 226 | **+168** | Very Unhealthy | PM2.5 |

The script checks these values and stops if EPA's file disagrees, so they match the README and `docs/MEMORY.md`. **June 26 defining pollutants:** Washtenaw **Ozone** (1 site reporting), Wayne PM2.5 (10 sites). Washtenaw's +186 therefore starts from an ozone-set value. See the [science note](../../docs/openorbit-data/science-note.md) for what that means. **Washtenaw had the larger increase (+186). Wayne had the higher June 28 AQI (226, 8 points higher).**

Context from the same file: the smoke arrived on June 27 (Washtenaw 214, Wayne 186), and June 28 is the highest day for both counties between June 24 and 30.

## Imagery (view from orbit)

**Attribution:** NASA GIBS / Worldview, MODIS Terra Corrected Reflectance (True Color).
**Source:** NASA GIBS WMS 1.3.0, layer `MODIS_Terra_CorrectedReflectance_TrueColor`, `CRS=EPSG:4326`, `BBOX=41.8,-84.4,42.8,-82.6` (south, west, north, east), 1440 × 800 px (0.00125° per pixel). The exact request is `gibs_url()` in the script.

| File | Date | What it shows |
| --- | --- | --- |
| [`modis_2023-06-26.jpg`](modis_2023-06-26.jpg) | June 26, 2023 | **Mostly cloud cover.** Aqua was also cloudy that day (checked), so the "before" view shows little ground. The AQI rows carry the before/after comparison. |
| [`modis_2023-06-28.jpg`](modis_2023-06-28.jpg) | June 28, 2023 | Gray wildfire-smoke haze over southeast Michigan. The Detroit River and Lake St. Clair are visible on the right. |

**Bounds check:** NASA's GIBS `Coastlines` layer, requested with the same bbox and size and drawn over the June 28 image, traces Lake St. Clair, the St. Clair delta, the Detroit River islands, and the Lake Erie shore.

NASA imagery shows how the region looked from orbit. EPA AQI reports air quality at ground level. Keep the two attributions separate on screen.

## Places

[`places.json`](places.json) holds the image bounds and size, and the marker coordinates.

| Marker | County | Lat, lon | Source |
| --- | --- | --- | --- |
| Eastern Michigan University | Washtenaw | 42.2502, -83.6245 | [Wikipedia](https://en.wikipedia.org/wiki/Eastern_Michigan_University) |
| Detroit | Wayne | 42.3317, -83.0458 | [Wikipedia](https://en.wikipedia.org/wiki/Detroit) |

Coordinates are Wikipedia's, rounded to 4 decimals (about 10 m, well under one pixel).

Pixel position: `x = (lon - west) / (east - west) * width`, `y = (north - lat) / (north - south) * height`. EMU lands at about (620, 440) and Detroit at about (1083, 375), on the Detroit River's west bank in the image.

## Fire detections (optional, #32)

**Attribution:** "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's LANCE and ESDIS." In captions: NASA FIRMS.
**Source:** NASA FIRMS yearly country files for VIIRS NOAA-20 (375 m), no key needed: `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-jpss1/2023/viirs-jpss1_2023_{Canada,United_States}.csv`. [`firms/build_firms.py`](firms/build_firms.py) downloads only June 26 and 28 with byte ranges, keeps the box from 40°N to 56°N and 95°W to 65°W (Great Lakes to Quebec), and stops if any row has the wrong date or falls outside the box. `--verify-only` checks the committed files offline.
**Files:** [`firms/viirs_noaa20_2023-06-26_28.csv`](firms/viirs_noaa20_2023-06-26_28.csv) (9,982 detections), [`firms/summary.json`](firms/summary.json) (counts), and `firms/region_2023-06-28.jpg` (NASA GIBS MODIS Terra, same box, 1200 × 640).

| Date | Detections in the box | Vegetation fires (type 0) | Of those, east of 79.5°W (Quebec) | Inside the demo area (southeast Michigan) |
| --- | ---: | ---: | ---: | --- |
| June 26, 2023 | 5,873 | 5,606 | 5,164 | 8, all type 2 (industrial or other static source) |
| June 28, 2023 | 4,109 | 3,851 | 2,938 | 5, all type 2 |

**What a detection means:** a 375 m satellite pixel with at least one hot spot in it at the time of the overpass (UTC). It is not a fire outline or a burned area. The view draws only type 0 ("presumed vegetation fire"). The Canada row count for June 26 (7,959) matches an independent count, which confirms the byte-range download.

**Why a wider map:** southeast Michigan had smoke but no wildfire detections. The fires were in Quebec and Ontario, more than 1,000 km away.

## Audio (spoken lines, #97)

**Files:** [`audio/show_satellite.wav`](audio/show_satellite.wav) and [`audio/compare_air_quality.wav`](audio/compare_air_quality.wav), about 7 s each, mono 22.05 kHz, under 350 KB.
**Made with:** [espeak-ng](https://github.com/espeak-ng/espeak-ng) 1.52.0 (GPL-3.0), voice `en-us`, 145 words per minute, generated offline by [`audio/make_audio.py`](audio/make_audio.py). The generated audio isn't covered by espeak-ng's licence, so we can redistribute it.
**Text:** the exact `spokenText` from `contracts/demo-round.json`, recorded in [`audio/manifest.json`](audio/manifest.json). `python data/openorbit/audio/make_audio.py --check` and `tests/test_audio.py` fail if the contract text, or the dataset's `spoken_comparison()`, changes without regenerating the audio.
