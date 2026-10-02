"""TACAN/DME channel -> paired VHF frequency (ICAO Annex 10, Vol. I,
Table A of the DME channelling and pairing plan).

Only X and Y channels 17-59 and 70-126 have a paired VHF navigation
frequency (108.00-117.95 MHz). Channels 1-16 and 60-69 are paired with
no VHF frequency at all, so they return None -- callers must not
invent one.

  17X-59X  -> 108.00 + (n - 17) * 0.10 MHz   (Y channels add 0.05)
  70X-126X -> 112.30 + (n - 70) * 0.10 MHz   (Y channels add 0.05)
"""

from __future__ import annotations

import re

_CHANNEL_RE = re.compile(r"^(\d{1,3})([XY])$")


def paired_vhf_mhz(channel: str) -> float | None:
    match = _CHANNEL_RE.match(channel.strip().upper())
    if not match:
        return None
    number = int(match.group(1))
    offset = 0.05 if match.group(2) == "Y" else 0.0
    if 17 <= number <= 59:
        return round(108.00 + (number - 17) * 0.10 + offset, 2)
    if 70 <= number <= 126:
        return round(112.30 + (number - 70) * 0.10 + offset, 2)
    return None
