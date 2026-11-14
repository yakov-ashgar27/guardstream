"""Per-card sliding-window state passed from Redis into the engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CardWindowState:
    """Per-card state read from Redis at evaluation time.

    Counts *exclude* the transaction being evaluated.
    """

    prior_count_velocity: int = 0
    prior_count_10m: int = 0
    last_country: str | None = None
    last_city: str | None = None
    last_lat: float | None = None
    last_lon: float | None = None
    last_ts_ms: int | None = None
