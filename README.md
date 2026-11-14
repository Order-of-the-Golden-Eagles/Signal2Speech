# Signal2Speech

**Hands-free communication with an EEG headset.**

Hack the Nest 2026 · Order of the Golden Eagles

Signal2Speech is an accessibility prototype for people who have difficulty speaking or typing. A conversation partner asks a question, AI offers a few short replies, and the headset wearer selects, previews, and confirms the words they want spoken.

> The app suggests what to say. The wearer decides what gets said.

## What we’re building

| Feature | Experience |
| --- | --- |
| **AI Answering** | A partner enters a question. The app offers possible replies. The wearer can choose one, ask for other options, or cancel. The app speaks the exact reply the wearer confirms. |
| **OpenOrbit** | The wearer uses the same controls to explore Earth data and decide which evidence to show. A confirmed choice updates the satellite view and speaks a short, source-backed explanation. |

**Interaction:** Question → choices → EEG selection → preview → confirmation → speech or on-screen action.

New to the project? [Follow one answer through the app](docs/architecture/README.md) for a plain-language walkthrough and architecture diagram.

## Live demo

**“Which county’s AQI rose more when wildfire smoke reached southeast Michigan?”**

The wearer chooses **Compare counties** and confirms. OpenOrbit switches from the June 26, 2023 satellite image to June 28, shows the EPA’s daily county AQI values, and reads the result aloud.

| Michigan county | June 26 | June 28 | Change |
| --- | ---: | ---: | ---: |
| Washtenaw (Eastern Michigan University) | 32 | 218 | **+186** |
| Wayne (Detroit) | 58 | 226 | **+168** |

**Washtenaw’s AQI rose 18 points more. Wayne’s June 28 AQI was 8 points higher.** NASA imagery shows how the region looked from orbit. The EPA data reports air quality at ground level.

## Proposed tech stack

| Layer | Current plan |
| --- | --- |
| EEG hardware | **g.tec Unicorn Hybrid Black** |
| EEG acquisition and selection | **g.tec Unicorn Suite** and the **Unity ERP starter with C#** |
| Interface | **Unity 2022.3 LTS and C#**: vendor `ERPFlashTag3D` targets plus uGUI and TextMeshPro overlays. No browser UI. |
| Local integration | In-process in Unity through the shared [selection contract](docs/architecture/selection-contract.md). No bridge. |
| AI Answering | Short reply suggestions with explicit wearer confirmation. **Model, provider, and integration TBD.** |
| Speech | Bundled audio for the OpenOrbit demo. **Speech synthesis for generated replies TBD.** |
| OpenOrbit data | Locally bundled **NASA MODIS imagery** and **EPA AirData daily county AQI**. **NASA FIRMS fire detections** are a planned extension. |
| Testing | Keyboard rehearsal, simulated input, then live EEG validation |

Use platform APIs and hardware-required packages. Keep the OpenOrbit demo assets local for offline rehearsal.

## Implementation status

**Planning and prototyping.** The first demo targets Unity. The app layout, any separate browser host, AI provider, and setup instructions are **TBD**. The first milestone is a keyboard-driven selection that produces one confirmed map-and-speech reveal. The live milestone is the same flow driven by two deliberate EEG selections, one to preview and one to confirm.

## Resources

- [g.tec Hackathon resources](https://github.com/unicorn-bi/Hackathon)
- [g.tec Unity ERP starter](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/build-your-first-erp-application.md)
- [NASA GIBS imagery documentation](https://nasa-gibs.github.io/gibs-api-docs/access-basics/)
- [EPA AirData 2023 daily county AQI download](https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2023.zip)
- [NASA FIRMS historical fire detections](https://firms.modaps.eosdis.nasa.gov/download/)
