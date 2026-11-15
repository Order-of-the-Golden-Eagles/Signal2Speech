"""Which amplifier are we reading, and which of its channels sit over the back of the head?

The eyes-closed confirm (#47) watches the alpha rhythm, which is strongest over the occipital
cortex. Each device puts those electrodes on different channels:

- **g.tec Unicorn Hybrid Black**: fixed montage Fz C3 Cz C4 Pz PO7 Oz PO8, so PO7/Oz/PO8 are
  channels 6-8. Nothing to choose.
- **g.tec P300 Speller dataset**: fixed montage Fz Cz P3 Pz P4 PO7 PO8 Oz (its montage.png), so
  the same channel numbers 6-8, in a different order.
- **PiEEG Octopus 16**: a 26 mm puck with 16 dry pins (plus reference and ground) in one
  20 x 20 mm cluster. It reads one spot, not a cap, so every channel is wherever the puck is:
  put it on the back of the head (Oz or Pz). The pins differ in contact, not position, so we
  drop pins with no contact or heavy noise and average every pin whose alpha rises when the
  wearer closes their eyes (``pick_alpha_channels``). ``--channels`` overrides it.
  Its reference pin is inside the cluster, so signals are smaller than with a normal cap.

Pure numpy, no g.Pype or Qt, so it is testable anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

ALPHA_BAND = (8.0, 13.0)


@dataclass(frozen=True)
class Device:
    key: str
    name: str
    vendor: str
    channel_count: int
    rate: float
    channel_names: Optional[Tuple[str, ...]]     # None: unnamed, placement varies
    alpha_channels: Optional[Tuple[int, ...]]    # 0-based; None: pick from data
    contact_rms_uv: Optional[Tuple[float, float]] = None   # vendor's "good contact" range, 1-40 Hz

    @property
    def fixed_montage(self) -> bool:
        return self.alpha_channels is not None

    def describe_channels(self, indices: Sequence[int]) -> str:
        if self.channel_names:
            return ", ".join(f"{self.channel_names[i]} (ch {i + 1})" for i in indices)
        return ", ".join(f"ch {i + 1}" for i in indices)


UNICORN = Device("unicorn", "g.tec Unicorn Hybrid Black", "g.tec", 8, 250.0,
                 ("Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8"), (5, 6, 7))
GTEC_P300_DATASET = Device("gtec-p300-dataset", "g.tec P300 Speller dataset", "g.tec", 8, 250.0,
                           ("Fz", "Cz", "P3", "Pz", "P4", "PO7", "PO8", "Oz"), (5, 6, 7))
# Contact range from PiEEG's AGENTS.md: good 2-150 uV RMS, above is "railed", below is "flat".
# Some boards sample at 244.14 Hz, not 250; PiEEG says 250 nominal is fine for band power.
PIEEG_OCTOPUS16 = Device("pieeg-octopus16", "PiEEG Octopus 16", "PiEEG", 16, 250.0, None, None,
                         contact_rms_uv=(2.0, 150.0))
GENERATOR = Device("generator", "g.Pype Generator (simulated)", "g.tec", 8, 250.0, None, (5, 6, 7))
UNKNOWN = Device("unknown", "Unknown EEG stream", "?", 0, 0.0, None, None)

DEVICES = (UNICORN, GTEC_P300_DATASET, PIEEG_OCTOPUS16, GENERATOR)


def detect(source: Optional[str] = None, *, stream_name: Optional[str] = None,
           channel_count: Optional[int] = None, rate: Optional[float] = None) -> Device:
    """Work out the device from how we are connected to it.

    ``source`` is our own source kind when we know it ("hybridblack", "generator", "dataset").
    For an LSL stream, pass its name, channel count and rate. An unrecognised stream comes back
    as UNKNOWN with the stream's own channel count, and its channels are picked from data.
    """
    kind = (source or "").lower().replace("-", "").replace("_", "")
    if kind in ("hybridblack", "unicorn"):
        return UNICORN
    if kind in ("dataset", "gtecp300dataset"):
        return GTEC_P300_DATASET
    if kind == "generator":
        return GENERATOR
    name = (stream_name or "").lower()
    if "octopus" in name or "pieeg" in name or channel_count == 16:
        return PIEEG_OCTOPUS16
    if "unicorn" in name or name.startswith("un-"):
        return UNICORN
    return Device("unknown", stream_name or UNKNOWN.name, "?", int(channel_count or 0),
                  float(rate or 0.0), None, None)


def alpha_power(block: np.ndarray, rate: float, band: Tuple[float, float] = ALPHA_BAND) -> np.ndarray:
    """Mean alpha-band power per channel, averaged over 1 s windows. ``block``: samples x channels."""
    x = np.asarray(block, dtype=float)
    if x.ndim != 2 or len(x) < int(rate):
        raise ValueError("need at least one second of samples x channels")
    n = int(rate)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    mask = (freqs >= band[0]) & (freqs <= band[1])
    window = np.hanning(n)[:, None]
    powers = []
    for start in range(0, len(x) - n + 1, n // 2):
        seg = x[start:start + n]
        seg = (seg - seg.mean(axis=0)) * window
        powers.append((np.abs(np.fft.rfft(seg, axis=0)) ** 2)[mask].mean(axis=0))
    return np.mean(powers, axis=0)


@dataclass(frozen=True)
class ChannelPick:
    channels: Tuple[int, ...]            # 0-based, best first
    ratios: Tuple[float, ...]            # closed/open alpha power, every channel
    reason: str

    def table(self, device: Device) -> str:
        order = np.argsort(self.ratios)[::-1]
        rows = [f"  {device.describe_channels([int(i)]):>14}  x{self.ratios[int(i)]:.1f}"
                + ("   <- used" if int(i) in self.channels else "") for i in order]
        return "\n".join(rows)


def band_rms(block: np.ndarray, rate: float, lo: float = 1.0, hi: float = 40.0) -> np.ndarray:
    """RMS per channel of the 1-40 Hz part of the signal, in the block's units (microvolts)."""
    x = np.asarray(block, dtype=float)
    x = x - x.mean(axis=0)
    spec = np.fft.rfft(x, axis=0)
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    spec[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(spec, n=len(x), axis=0).std(axis=0)


def contact_ok(block: np.ndarray, rate: Optional[float] = None,
               bounds: Optional[Tuple[float, float]] = None,
               flat_uv: float = 0.05, noisy_factor: float = 6.0) -> np.ndarray:
    """True per channel if the pin seems to be touching the scalp.

    With the vendor's range (``bounds``, in microvolts RMS over 1-40 Hz) use that. Without one,
    fall back to: not flat, and not far noisier than the typical pin."""
    x = np.asarray(block, dtype=float)
    if bounds is not None and rate:
        rms = band_rms(x, rate)
        return (rms >= bounds[0]) & (rms <= bounds[1])
    rms = (x - x.mean(axis=0)).std(axis=0)
    typical = float(np.median(rms[rms > flat_uv])) if np.any(rms > flat_uv) else 0.0
    return (rms > flat_uv) & (rms <= noisy_factor * typical if typical else rms > flat_uv)


class NoAlphaResponse(ValueError):
    """No channel's alpha rose enough with eyes closed. The message says what to try."""


def pick_alpha_channels(open_block: np.ndarray, closed_block: np.ndarray, rate: float,
                        k: int = 3, min_ratio: float = 1.5,
                        contact_bounds: Optional[Tuple[float, float]] = None) -> ChannelPick:
    """The channels whose alpha power rises most from eyes open to eyes closed.

    Keeps up to ``k`` channels, but only those within half of the best channel's ratio, so one
    good occipital electrode isn't diluted by fifteen that see nothing.
    """
    p_open = alpha_power(open_block, rate)
    p_closed = alpha_power(closed_block, rate)
    ratios = p_closed / np.maximum(p_open, 1e-12)
    usable = (contact_ok(open_block, rate, contact_bounds)
              & contact_ok(closed_block, rate, contact_bounds))
    if not usable.any():
        raise NoAlphaResponse("Every channel looks flat or very noisy: no pin seems to be touching "
                              "the scalp. Part the hair, press the sensor straight down, hold it "
                              "snug with a headband, and try again.")
    ratios = np.where(usable, ratios, 0.0)
    order = np.argsort(ratios)[::-1]
    best = float(ratios[order[0]])
    if best < min_ratio:
        raise NoAlphaResponse(
            f"No channel's alpha rose with eyes closed (best x{best:.1f}, need x{min_ratio:g}). "
            "Check that an electrode is on the back of the head and touching the scalp, that the "
            "eyes were really closed, and try again. Or name the channel with --channels.")
    keep = [int(i) for i in order[:k] if ratios[i] >= max(min_ratio, best / 2)]
    return ChannelPick(tuple(keep), tuple(float(r) for r in ratios),
                       f"picked from data: alpha rose x{best:.1f} on the best channel")


def resolve_alpha_channels(device: Device, requested: Optional[Sequence[int]] = None,
                           open_block: Optional[np.ndarray] = None,
                           closed_block: Optional[np.ndarray] = None,
                           rate: Optional[float] = None) -> ChannelPick:
    """The channels to use, in priority order: asked for, the device's montage, picked from data."""
    count = device.channel_count
    if requested:
        chans = tuple(int(c) for c in requested)
        if count and any(not 0 <= c < count for c in chans):
            raise ValueError(f"{device.name} has channels 1..{count}")
        return ChannelPick(chans, (), "chosen with --channels")
    if device.fixed_montage:
        return ChannelPick(device.alpha_channels, (), f"{device.name} montage: "
                           f"{device.describe_channels(device.alpha_channels)}")
    if open_block is None or closed_block is None:
        raise ValueError(f"{device.name} has no fixed montage: give --channels, or eyes-open and "
                         "eyes-closed data to pick from")
    # A single-spot sensor: use every pin that responds, not just the top three.
    k = device.channel_count or 3
    return pick_alpha_channels(open_block, closed_block, rate or device.rate, k=k,
                               contact_bounds=device.contact_rms_uv)
