"""Game clock -- translates ticks into real-world time.

1 tick = 10 in-game minutes.
School day: 8am (tick 0) to 10pm (tick 84) by default.
Ticks per day is configurable via scenario settings.
"""

from dataclasses import dataclass

TICKS_PER_DAY: int = 84  # 14 hours * 6 ticks/hour (default)
MINUTES_PER_TICK: int = 10
DAY_START_HOUR: int = 8  # 8:00 AM


@dataclass
class GameClock:
    """Tracks in-game time."""

    day: int = 1
    tick: int = 0  # Start of day
    ticks_per_day: int = TICKS_PER_DAY  # configurable per scenario

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

    _WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Mon", "Tue")  # loops through a school week

    @property
    def weekday_str(self) -> str:
        """Named weekday: Mon, Tue, Wed, Thu, Fri (cycles weekly)."""
        return self._WEEKDAYS[(self.day - 1) % 5]

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
    def day_time_str(self) -> str:
        """Combined display like 'Mon 9:35a' for the HUD banner."""
        h = self.hour
        m = self.minute
        period = "a" if h < 12 else "p"
        display_h = h % 12
        if display_h == 0:
            display_h = 12
        return f"{self.weekday_str} {display_h}:{m:02d}{period}"

    @property
    def is_day_over(self) -> bool:
        return self.tick >= self.ticks_per_day

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
        return self.tick / self.ticks_per_day
