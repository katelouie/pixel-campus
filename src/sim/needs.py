"""Needs system -- the foundation of student motivation.

Each student has 6 needs that decay over time. Activities satisfy specific
needs. Overall mood is derived from how well needs are being met.
"""

from dataclasses import dataclass
from enum import Enum


class NeedType(Enum):
    FUN = "fun"
    SOCIAL = "social"
    REST = "rest"
    ACADEMICS = "academics"
    CREATIVITY = "creativity"
    ATHLETICS = "athletics"


# Default decay rates per tick for each need type.
# 48 ticks/day — these rates are tuned so needs create real pressure without being brutal.
# Overnight recovery (high_school.json day_reset) is set to roughly break even with OKAY sleep.
DEFAULT_DECAY_RATES: dict[NeedType, float] = {
    NeedType.FUN:        0.6,   # 28.8/day — needs active fun or slowly drains
    NeedType.SOCIAL:     0.5,   # 24.0/day — socializing is required, not optional
    NeedType.REST:       0.8,   # 38.4/day — tiredness accumulates noticeably
    NeedType.ACADEMICS:  0.3,   # 14.4/day — background anxiety without study
    NeedType.CREATIVITY: 0.3,   # 14.4/day
    NeedType.ATHLETICS:  0.35,  # 16.8/day
}


@dataclass
class Need:
    """A single need that decays over time and contributes to mood."""

    need_type: NeedType
    value: float = 50.0
    decay_per_tick: float = 0.5
    weight: float = 1.0

    @property
    def satisfaction(self) -> float:
        """0.0 (desperate) to 1.0 (fully satisfied)."""
        return self.value / 100.0

    @property
    def mood_contribution(self) -> float:
        """Mood impact: negative when low, positive when high, neutral in the middle.

        Below 30: increasingly painful (up to -10 * weight)
        30-70: neutral zone (0)
        Above 70: pleasant bonus (up to +5 * weight)
        """
        if self.value < 30:
            return -self.weight * (30 - self.value) / 30 * 10
        elif self.value > 70:
            return self.weight * (self.value - 70) / 30 * 5
        return 0.0

    def clamp(self) -> None:
        """Keep value within 0-100."""
        self.value = max(0.0, min(100.0, self.value))


def create_default_needs() -> dict[NeedType, Need]:
    """Create a fresh set of needs for a new student."""
    return {
        nt: Need(need_type=nt, value=50.0, decay_per_tick=rate)
        for nt, rate in DEFAULT_DECAY_RATES.items()
    }


def tick_needs(
    needs: dict[NeedType, Need],
    traits: list | None = None,
) -> None:
    """Decay all needs by their per-tick rate. Called once per student per tick.

    If traits are provided, applies trait decay multipliers.
    """
    for need in needs.values():
        decay = need.decay_per_tick
        if traits:
            from .traits import combined_need_decay_mult
            decay *= combined_need_decay_mult(traits, need.need_type.value)
        need.value -= decay
        need.clamp()


def satisfy_need(
    needs: dict[NeedType, Need],
    need_type: NeedType,
    amount: float,
    traits: list | None = None,
) -> None:
    """Add (or subtract) from a specific need. Clamps to 0-100.

    If traits are provided, applies trait satisfaction multipliers.
    """
    if need_type in needs:
        if traits and amount > 0:
            from .traits import combined_need_satisfy_mult
            amount *= combined_need_satisfy_mult(traits, need_type.value)
        needs[need_type].value += amount
        needs[need_type].clamp()


def compute_needs_mood(needs: dict[NeedType, Need]) -> float:
    """Compute mood baseline from needs. Returns a value roughly in the 0-100 range.

    50 = perfectly neutral (all needs in the middle zone).
    Below 50 = some needs are hurting.
    Above 50 = needs are well-satisfied.
    """
    total = sum(n.mood_contribution for n in needs.values())
    return max(0.0, min(100.0, 50.0 + total))
