"""Authority-clock semantics independent of wall-clock time."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class RuntimeMode(StrEnum):
    """M1 clock-policy modes; no transport behavior is implied."""

    HEADLESS_FAST = "HEADLESS_FAST"
    UNITY_LIVE = "UNITY_LIVE"
    REPLAY = "REPLAY"


LIVE_TIME_SCALES = (0.0, 1.0, 2.0, 4.0)


@dataclass(frozen=True, slots=True)
class ClockAdvance:
    """An accepted absolute game-minute input to the authority core."""

    previous_game_minute: int
    target_game_minute: int

    @property
    def elapsed_game_minutes(self) -> int:
        return self.target_game_minute - self.previous_game_minute

    def minutes(self) -> range:
        return range(self.previous_game_minute + 1, self.target_game_minute + 1)


def accept_advanced_game_minute(previous_game_minute: int, target_game_minute: int) -> ClockAdvance:
    """Validate an already-advanced authority time.

    The caller may derive this integer from a UI time scale, a headless driver,
    or replay input. The simulation core deliberately accepts no wall seconds.
    """

    if previous_game_minute < 0:
        raise ValueError("previous game minute must be non-negative")
    if target_game_minute <= previous_game_minute:
        raise ValueError("target game minute must advance authority time")
    return ClockAdvance(previous_game_minute, target_game_minute)


def approve_time_scale(requested: float, mode: RuntimeMode) -> float:
    """Approve presentation/driver scale without advancing authority time."""

    if not math.isfinite(requested) or requested < 0:
        raise ValueError("time scale must be finite and non-negative")
    if mode is RuntimeMode.UNITY_LIVE and requested not in LIVE_TIME_SCALES:
        raise ValueError(f"Unity Live scale must be one of {LIVE_TIME_SCALES}")
    return requested
