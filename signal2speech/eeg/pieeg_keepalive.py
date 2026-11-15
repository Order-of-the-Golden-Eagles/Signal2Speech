"""Keep a PiEEG Octopus 16 streaming over LSL, reconnecting when the Bluetooth link drops (#150).

PiEEG's own ``python_quickstart.py --lsl`` exits quietly the moment the link drops, and the LSL
stream goes with it. On 2026-11-15 the real board ran for 8.5 minutes and then dropped. This
runs PiEEG's code (its packet decoder and its LSL publisher, unchanged) inside a loop:

- the LSL stream ``Octopus16`` stays up across a drop, so readers don't have to be restarted;
- it reconnects by itself and says how long the gap was;
- every drop is counted and timed, so we can tell a flaky link from a dead power bank.

    python -m signal2speech.eeg.pieeg_keepalive --starter C:/Projects/HackTheNest/hello_world_octopus_16

It needs PiEEG's starter folder (``git clone https://github.com/pieeg-club/hello_world_octopus_16``)
and ``bleak``. Power the board from a 5 V power bank only while it is on someone's head.
A gap in the data is still a gap: the board session stops if one lasts more than a few seconds.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

DEFAULT_STARTER = Path(__file__).resolve().parents[3] / "hello_world_octopus_16"
CONNECT_TIMEOUT_S = 30.0          # the default 10 s timed out once in a room with ~300 devices
SCAN_TIMEOUT_S = 10.0


def load_starter(folder: Path):
    """Import PiEEG's ``python_quickstart.py`` from its own folder, without copying it."""
    script = Path(folder) / "python_quickstart.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"PiEEG's starter isn't at {folder}. Clone it: "
            "git clone https://github.com/pieeg-club/hello_world_octopus_16")
    spec = importlib.util.spec_from_file_location("pieeg_quickstart", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp() -> str:
    return time.strftime("%H:%M:%S")


def describe_drop(connected_s: float, drops: int) -> str:
    """One plain line about a drop, with the most likely cause for how long the link lasted."""
    if connected_s < 20:
        hint = ("it dropped almost at once: something else may be connecting to the board "
                "(close the PiEEG Dashboard tab), or it is too far away")
    else:
        hint = ("check the power bank: many switch off when a small board draws too little "
                "current. Keep the board close to the laptop")
    return f"link dropped after {connected_s:.0f} s (drop {drops}). {hint}"


async def stream_once(q, monitor, say) -> float:
    """Connect and stream until the link drops. Returns how many seconds it stayed connected,
    or -1 if the board wasn't found."""
    from bleak import BleakClient, BleakScanner

    def is_board(device, adv) -> bool:
        if q.SERVICE_UUID in [u.lower() for u in (adv.service_uuids or [])]:
            return True
        name = (device.name or adv.local_name or "").lower()
        return name.startswith(("octopus", "octopos", "bioron", "pieeg"))

    device = await BleakScanner.find_device_by_filter(is_board, timeout=SCAN_TIMEOUT_S)
    if device is None:
        return -1.0
    say(f"[{stamp()}] found {device.name or device.address}, connecting...")
    async with BleakClient(device, timeout=CONNECT_TIMEOUT_S) as client:
        def on_notify(_sender, data: bytearray) -> None:
            for offset in range(0, len(data) - q.PACKET_SIZE + 1, q.PACKET_SIZE):
                decoded = q.decode_octopus16_packet(data[offset:offset + q.PACKET_SIZE])
                if decoded:
                    monitor.ingest(decoded[0], decoded[1])

        await client.start_notify(q.NOTIFY_CHAR_UUID, on_notify)
        started = time.monotonic()
        say(f"[{stamp()}] CONNECTED, streaming 16 channels (Ctrl+C to stop)")
        while client.is_connected:
            await asyncio.sleep(0.25)
        return time.monotonic() - started


async def keep_alive(q, monitor, say=print, max_drops: Optional[int] = None) -> int:
    """Stream, and reconnect after every drop. Returns the number of drops."""
    drops, told_waiting = 0, False
    while True:
        try:
            connected_s = await stream_once(q, monitor, say)
        except (asyncio.TimeoutError, TimeoutError):
            say(f"[{stamp()}] connecting timed out, trying again")
            connected_s = None
        except Exception as err:                      # bleak raises several kinds on a bad link
            say(f"[{stamp()}] connection error ({type(err).__name__}: {err}), trying again")
            connected_s = None
        if connected_s is not None and connected_s >= 0:
            drops += 1
            say(f"[{stamp()}] " + describe_drop(connected_s, drops))
            told_waiting = False
            if max_drops is not None and drops >= max_drops:
                return drops
        elif connected_s is not None and not told_waiting:
            say(f"[{stamp()}] the board isn't advertising. Is it powered (slow LED blink), and is "
                "anything else connected to it? Still looking...")
            told_waiting = True
        await asyncio.sleep(1.0)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.pieeg_keepalive",
                                description="PiEEG Octopus 16 to LSL, reconnecting after drops (#150)")
    p.add_argument("--starter", type=Path, default=DEFAULT_STARTER,
                   help="folder holding PiEEG's python_quickstart.py")
    p.add_argument("--csv", default=None, help="also save the raw stream to this CSV file")
    args = p.parse_args(argv)
    try:
        q = load_starter(args.starter)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 1
    monitor = q.StreamMonitor(csv_path=args.csv, use_lsl=True)
    try:
        asyncio.run(keep_alive(q, monitor))
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        monitor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
