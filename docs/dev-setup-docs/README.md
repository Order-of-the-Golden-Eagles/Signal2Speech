# Dev Setup and Docs

Record the verified launch command, vendor prerequisites, and revision.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#11](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/11)

## Unity launch path (#19)

Steps come from the [g.tec installation guide](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/installation-guideline.md), [quick start](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/quick-start-guide.md), and [ERP tutorial](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/build-your-first-erp-application.md). **Each step is unverified until someone runs it on the demo laptop and checks it off in #19.**

| # | Step | Expected result | Verified |
| --- | --- | --- | --- |
| 1 | Install **Unity Hub**, then **Unity 2022.3.11f1** (the vendor's recommended 2022.3 LTS). Unity 6 is not supported by the SDK. | Hub lists 2022.3.11f1 | ☐ |
| 2 | Install **Unicorn Suite Hybrid Black** → DevTools → **Unicorn Unity** → download → Open. | `C:\Users\<you>\Documents\gtec\Unicorn Suite\Hybrid Black\Unicorn Unity Interface\UnicornUnityInterface.unitypackage` exists | ☐ |
| 3 | Open `unity/Signal2Speech` in Hub with 2022.3.11f1. #19 creates it from the 3D template and commits it. | Empty project opens | ☐ |
| 4 | Assets → Import Package → Custom Package → `UnicornUnityInterface.unitypackage` | `Assets/gtec/Unity Interface/Prefabs` exists | ☐ |
| 5 | Check that `Packages/manifest.json` has `"com.goldeneagles.signal2speech.core": "file:../../../core"`. Window → General → Test Runner → EditMode → Run All. | 11 core tests pass | ☐ |
| 6 | Open `Assets/Signal2Speech/Scenes/Demo.unity` (until #25 lands, use the vendor's `MyFirstERPBCI.unity`: **BCI Visual ERP 3D** prefab plus an **EventSystem**) → **Play** | Upper-left device dropdown and Connect button | ☐ |
| 7 | Choose `UN-0000.00.00` (the vendor's **Unicorn simulator**) → Connect | 8 signal-quality boxes | ☐ |
| 8 | Start Training, then run **≥30 trials (60 recommended)** → Continue | The classifier circle is green or yellow, and `On Class Selection` fires | ☐ |
| 9 | Live headset: choose the real serial → Connect over Bluetooth → wait for all boxes to turn light blue → train → Continue | Same as step 8, labelled `live-eeg` | ☐ (#23) |

**Open question:** is the vendor `.unitypackage` licensed for redistribution? If not, keep `Assets/gtec/` out of git and have each dev import it in step 4. `*.unitypackage` is already gitignored.
