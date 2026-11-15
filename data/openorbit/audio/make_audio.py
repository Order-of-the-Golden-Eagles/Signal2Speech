"""Generate the two bundled OpenOrbit clips offline with espeak-ng (#97).

    python data/openorbit/audio/make_audio.py           # (re)write the WAVs and manifest.json
    python data/openorbit/audio/make_audio.py --check   # verify texts match, write nothing

Each clip reads the exact spokenText from contracts/demo-round.json, so the bundled audio says
the same words as the preview the wearer confirmed. espeak-ng is open source (GPL-3.0); the
audio it generates is ours to redistribute. Install it with `brew install espeak-ng`,
`sudo apt install espeak-ng`, or the Windows installer from github.com/espeak-ng/espeak-ng.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT = ROOT / "contracts" / "demo-round.json"
MANIFEST = HERE / "manifest.json"
CLIPS = ("show_satellite", "compare_air_quality")
VOICE = {"voice": "en-us", "words_per_minute": 145, "pitch": 45, "amplitude": 180}


def contract_texts() -> dict:
    choices = json.loads(CONTRACT.read_text(encoding="utf-8"))["choices"]
    texts = {c["actionId"]: c["spokenText"] for c in choices}
    return {k: texts[k] for k in CLIPS}


def espeak_version(exe: str) -> str:
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True).stdout
    return out.split(":")[1].split("Data")[0].strip() if ":" in out else out.strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="verify the manifest texts only")
    args = p.parse_args(argv)
    texts = contract_texts()
    if args.check:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        bad = [k for k in CLIPS if manifest["clips"][k]["text"] != texts[k]
               or not (HERE / f"{k}.wav").is_file()]
        print("OK" if not bad else f"out of date: {bad}. Run make_audio.py again.")
        return 1 if bad else 0
    exe = shutil.which("espeak-ng")
    if exe is None:
        print("espeak-ng not found. Install it first (see the docstring).", file=sys.stderr)
        return 2
    for key, text in texts.items():
        subprocess.run([exe, "-v", VOICE["voice"], "-s", str(VOICE["words_per_minute"]),
                        "-p", str(VOICE["pitch"]), "-a", str(VOICE["amplitude"]),
                        "-w", str(HERE / f"{key}.wav"), text], check=True)
        print(f"wrote {key}.wav: {text}")
    MANIFEST.write_text(json.dumps({
        "tool": f"espeak-ng {espeak_version(exe)}", "settings": VOICE,
        "clips": {k: {"file": f"{k}.wav", "text": t} for k, t in texts.items()},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
