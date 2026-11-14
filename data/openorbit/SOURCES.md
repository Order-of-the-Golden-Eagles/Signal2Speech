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

The script checks these values and stops if EPA's file disagrees, so they match the README and `docs/MEMORY.md`. **Washtenaw had the larger increase (+186). Wayne had the higher June 28 AQI (226, 8 points higher).**

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
