# Science note: what the OpenOrbit data is, and what we claim (#153)

For the Beyond the Horizon judges. Every number below is from the committed files in [`data/openorbit/`](../../data/openorbit/), which [`build_dataset.py`](../../data/openorbit/build_dataset.py) checks against the source. The provenance is in [SOURCES.md](../../data/openorbit/SOURCES.md).

## What the app claims, and what it doesn't

| We claim | We don't claim |
| --- | --- |
| In EPA's daily county AQI, Washtenaw went from 32 on June 26, 2023 to 218 on June 28 (+186), and Wayne went from 58 to 226 (+168). | That the satellite image measures air quality, or shows PM2.5. True-color imagery shows how the scene looked from orbit. |
| On June 28, both counties were Very Unhealthy, and PM2.5 set the AQI in both. | That every AQI point is due to smoke. The comparison is a before/after correlation during a documented smoke event, not an attribution model. |
| The June 28 MODIS image shows gray haze over southeast Michigan on the day the PM2.5 AQI peaked. Michigan's EGLE called a PM2.5 Air Quality Action Day that day, and the National Weather Service attributed the smoke to Canadian wildfires. | That the fires were in Michigan. FIRMS shows no wildfire detections in the demo area. The fires were in Quebec and Ontario, more than 1,000 km away (see the optional fire map). |
| June 26 → June 28 is a valid comparison on the AQI scale for both counties. | That Washtenaw's +186 is a PM2.5-to-PM2.5 change. Its June 26 value was set by **ozone** (see below). |

## The satellite images (view from orbit)

- **Product:** NASA GIBS layer `MODIS_Terra_CorrectedReflectance_TrueColor`, MODIS on the Terra satellite. It's corrected reflectance in true color, with bands 1, 4, and 3 as red, green, and blue, at 250 m. The 500 m bands 3 and 4 are sharpened with the 250 m band 1. ([NASA MODIS True Color](https://www.earthdata.nasa.gov/sites/default/files/imported/MODIS_True_Color.pdf))
- **Dates:** June 26 and June 28, 2023, the GIBS daily image for each date.
- **Time of overpass:** Terra is the morning MODIS satellite. Its nominal equator crossing is 10:30 a.m. local solar time on the descending pass. Since a final maneuver in February 2020 it has drifted earlier: past 10:15 by fall 2022, so a little earlier still in June 2023. ([About Terra](https://terra.nasa.gov/about), [Terra orbital drift](https://terra.nasa.gov/about/terras-orbit-changes/terra-orbital-drift-information)) So the images are a late-morning snapshot. The EPA values are whole-day figures.
- **Bounds:** 41.8°N to 42.8°N, 84.4°W to 82.6°W (EPSG:4326), 1440 × 800 px, which is 0.00125° per pixel. The bounds are checked by overlaying NASA's GIBS coastlines on the June 28 image.
- **What's visible:**
  - **June 26 is mostly cloud.** Aqua was also cloudy that day. The white is cloud, not clear air, and the app captions it "mostly cloud". The before/after comparison rests on the AQI rows, not on that image.
  - **June 28 shows gray haze**, with the Detroit River and Lake St. Clair visible through it.

## The air quality numbers (ground level)

**What a daily county AQI is.** EPA computes a daily AQI for each pollutant each monitor measures: PM2.5 from the 24-hour average, and ozone from the highest 8-hour average. A county's daily AQI is the **highest** of those values across its monitors. The pollutant that produced it is the day's "defining parameter". ([EPA AQS AQI data](https://aqs.epa.gov/aqsweb/documents/aqi/aqi_data.html)) Categories: 0–50 Good, 51–100 Moderate, 101–150 Unhealthy for Sensitive Groups, 151–200 Unhealthy, 201–300 Very Unhealthy.

| County | Date | AQI | Category | Defining pollutant | Defining site | Sites reporting |
| --- | --- | ---: | --- | --- | --- | ---: |
| Washtenaw | June 26 | 32 | Good | **Ozone** | 26-161-9991 | 1 |
| Washtenaw | June 28 | 218 | Very Unhealthy | PM2.5 | 26-161-0008 | 2 |
| Wayne | June 26 | 58 | Moderate | PM2.5 | 26-163-0099 | 10 |
| Wayne | June 28 | 226 | Very Unhealthy | PM2.5 | 26-163-0097 | 10 |

**What that means for the comparison**
- **Wayne** is like for like: PM2.5 set the AQI on both days, from 10 reporting sites.
- **Washtenaw on June 26** came from a single reporting site, and ozone set it. Any PM2.5 measured in Washtenaw that day was at or below AQI 32, or it would have been the defining pollutant. So "+186" is a true change in the county AQI. But the starting point is an ozone value, and the PM2.5-only rise is at least as large: it starts at or below 32 and ends at 218.
- **"Which county rose more?"** Washtenaw (+186 vs +168). **"Which was worse on June 28?"** Wayne (226 vs 218). The app shows both answers, because they differ.
- **Values as published:** these are the values in EPA's AirData 2023 daily county file, retrieved 2026-11-14. We don't recompute AQI from concentrations. EPA revised the PM2.5 AQI breakpoints in 2024, so other sources, or recomputed values, may differ slightly. The event also shows on June 27 (Washtenaw 214, Wayne 186), and June 28 is the highest day for both counties from June 24 to 30.

## The smoke event

Michigan's EGLE declared June 28, 2023 an Air Quality Action Day for elevated PM2.5 in southeast Michigan. The National Weather Service attributed the smoke to Canadian wildfires, held near the ground by a morning temperature inversion. The advisory was later extended statewide through June 29. ([WDET](https://wdet.org/2023/06/28/air-quality-alert-for-metro-detroit-extended-to-thursday/), [PBS NewsHour](https://www.pbs.org/newshour/nation/air-quality-plummets-in-parts-of-the-u-s-again-due-to-wildfire-smoke-from-canada)) NASA FIRMS (VIIRS NOAA-20) shows thousands of vegetation-fire detections in Quebec and Ontario on June 26 and 28, and none in the demo area. See [SOURCES.md](../../data/openorbit/SOURCES.md#fire-detections-optional-32).

## On-screen wording, checked against this note

| Where | Text | Status |
| --- | --- | --- |
| Spoken line (`contracts/demo-round.json`) | "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." | ✅ True on the AQI scale |
| Spoken line | "…NASA MODIS view of southeast Michigan under wildfire smoke." | ✅ Supported by the same-day PM2.5 peak, the EGLE action day, and the FIRMS fires |
| View | June 26 image caption | ✅ Now reads "June 26, 2023 · mostly cloud" (#153) |
| View | Pollutant line under the table | ✅ Added (#153), computed from the data: "PM2.5 everywhere except Washtenaw Jun 26: ozone" |
| View | Separate NASA and EPA credit lines | ✅ Matches SOURCES.md |
| README | "NASA imagery shows the smoke from orbit. EPA data measures air quality at ground level." | ✅ |
