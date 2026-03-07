"""Game clock -- translates ticks into real-world time.

1 time = 10 in-game minutes.
School day: 8am (tick 0) to 10pm (tick 84).
"""

from dataclasses import dataclass

TICKS_PER_DAY: int = 84  # 14 hours * 6 ticks/hour
MINUTES_PER_TICK: int = 10
DAY_START_HOUR: int = 8  # 8:00 AM


@dataclass
class GameClock:
    """Tracks in-game time."""

    day: int = 1
    tick: int = 0  # Start of day

    @property
    def minutes_elapsed(self) -> int:
        """Minutes elapsed since start of the day."""
        return self.tick * MINUTES_PER_TICK

    @property
    def hour(self) -> int:
        """Current hour (24h format.)"""
        return DAY_START_HOUR + (self.minutes_elapsed // 60)

    @property
    def minute(self) -> int:
        """Current minute within the hour."""
        return self.minutes_elapsed % 60

    @property
    def time_str(self) -> str:
        """Human-readable time like '2:30 PM'."""
        h = self.hour
        m = self.minute
        period = "AM" if h < 12 else "PM"
        display_h = h % 12
        if display_h == 0:
            display_h = 12

        return f"{display_h}:{m:02d} {period}"

    @property
    def is_day_over(self) -> bool:
        return self.tick >= TICKS_PER_DAY

    def advance(self) -> bool:
        """Advance one tick. Returns True if the day just ended."""
        self.tick += 1
        return self.is_day_over

    def new_day(self) -> None:
        """Reset tick counter and start new day."""
        self.day += 1
        self.tick = 0

    @property
    def day_progress(self) -> float:
        """0.0 to 1.0. How far through the day it is."""
        return self.tick / TICKS_PER_DAY
