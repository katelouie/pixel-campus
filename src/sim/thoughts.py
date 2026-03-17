"""Thoughts system -- stackable mood modifiers with durations.

Students accumulate thoughts from activities, social interactions, events,
and daily life. Each thought has a mood effect and a countdown timer.
Mood = needs baseline + sum of active thoughts.

Inspired by Rimworld's thought/mood stack system.
"""

from dataclasses import dataclass, field


@dataclass
class Thought:
    """A single thought that affects mood for a duration."""

    label: str  # "Aced a test", "Made a new friend"
    mood_effect: float  # +5, -3, +12, etc.
    duration_ticks: int  # total lifetime in ticks
    ticks_remaining: int  # countdown to expiry
    category: str = ""  # "academic", "social", "event", "activity", "rest"
    stackable: bool = False  # can you have multiple of this thought?
    source_id: str = ""  # unique key to prevent duplicates (e.g., "activity_favorite")

    @property
    def expired(self) -> bool:
        return self.ticks_remaining <= 0


def tick_thoughts(thoughts: list[Thought]) -> list[Thought]:
    """Decrement timers, return list with expired thoughts removed."""
    for t in thoughts:
        t.ticks_remaining -= 1
    return [t for t in thoughts if not t.expired]


def add_thought(thoughts: list[Thought], thought: Thought) -> None:
    """Add a thought, respecting stacking rules.

    If not stackable, replaces any existing thought with the same source_id.
    This means "Did something I love" refreshes instead of piling up.
    """
    if not thought.stackable and thought.source_id:
        thoughts[:] = [t for t in thoughts if t.source_id != thought.source_id]
    thoughts.append(thought)


def sum_thought_effects(thoughts: list[Thought]) -> float:
    """Total mood impact of all active thoughts."""
    return sum(t.mood_effect for t in thoughts)


# -------------------------------------------------------------------
# THOUGHT FACTORIES
# Convenience functions that create common thoughts with proper defaults.
# -------------------------------------------------------------------


def thought_activity_favorite(skill_name: str) -> Thought:
    """Student just did an activity in their favorite skill area."""
    return Thought(
        label=f"Did something I love ({skill_name})",
        mood_effect=4.0,
        duration_ticks=12,  # ~2 hours
        ticks_remaining=12,
        category="activity",
        source_id="activity_favorite",
    )


def thought_activity_dreaded(skill_name: str) -> Thought:
    """Student was stuck doing their least favorite activity."""
    return Thought(
        label=f"Stuck doing {skill_name}",
        mood_effect=-3.0,
        duration_ticks=12,
        ticks_remaining=12,
        category="activity",
        source_id="activity_dreaded",
    )


def thought_friendship_levelup(friend_name: str) -> Thought:
    """Friendship leveled up."""
    return Thought(
        label=f"Getting closer to {friend_name}",
        mood_effect=6.0,
        duration_ticks=42,  # ~1 day
        ticks_remaining=42,
        category="social",
        stackable=True,  # can befriend multiple people
    )


def thought_best_friend(friend_name: str) -> Thought:
    """Became best friends with someone."""
    return Thought(
        label=f"Made a best friend! ({friend_name})",
        mood_effect=10.0,
        duration_ticks=84,  # ~2 days (since 84 ticks = 1 day, this is actually 1 day)
        ticks_remaining=84,
        category="social",
        source_id=f"best_friend_{friend_name}",
    )


def thought_crush(crush_name: str) -> Thought:
    """Romance reached crush level."""
    return Thought(
        label=f"{crush_name} likes me?!",
        mood_effect=8.0,
        duration_ticks=84,
        ticks_remaining=84,
        category="social",
        source_id=f"crush_{crush_name}",
    )


def thought_event_success(event_name: str) -> Thought:
    """Student succeeded at a school event."""
    return Thought(
        label=f"Nailed the {event_name}!",
        mood_effect=8.0,
        duration_ticks=168,  # ~2 days
        ticks_remaining=168,
        category="event",
        source_id=f"event_{event_name}",
    )


def thought_event_failure(event_name: str) -> Thought:
    """Student failed at a school event."""
    return Thought(
        label=f"Bombed the {event_name}...",
        mood_effect=-5.0,
        duration_ticks=84,
        ticks_remaining=84,
        category="event",
        source_id=f"event_{event_name}",
    )


def thought_great_report_card() -> Thought:
    """All grades are A or B."""
    return Thought(
        label="Great report card!",
        mood_effect=10.0,
        duration_ticks=168,
        ticks_remaining=168,
        category="academic",
        source_id="report_card_great",
    )


def thought_failing_subject(subject_name: str) -> Thought:
    """Got an F on report card."""
    return Thought(
        label=f"Failing {subject_name}...",
        mood_effect=-8.0,
        duration_ticks=168,
        ticks_remaining=168,
        category="academic",
        source_id=f"failing_{subject_name}",
    )


def thought_grades_improving() -> Thought:
    """Grades went up since last report card."""
    return Thought(
        label="Grades are going up!",
        mood_effect=5.0,
        duration_ticks=84,
        ticks_remaining=84,
        category="academic",
        source_id="grades_improving",
    )


def thought_slept_well() -> Thought:
    """Had good rest at end of day."""
    return Thought(
        label="Slept well",
        mood_effect=3.0,
        duration_ticks=42,  # ~half a day
        ticks_remaining=42,
        category="rest",
        source_id="sleep_quality",
    )


def thought_exhausted() -> Thought:
    """Was exhausted at end of day."""
    return Thought(
        label="So tired...",
        mood_effect=-4.0,
        duration_ticks=42,
        ticks_remaining=42,
        category="rest",
        source_id="sleep_quality",
    )


def thought_running_on_fumes() -> Thought:
    """REST need critically low (< 10)."""
    return Thought(
        label="Running on fumes",
        mood_effect=-6.0,
        duration_ticks=6,  # short, but refreshes while REST stays low
        ticks_remaining=6,
        category="rest",
        source_id="critical_rest",
    )


def thought_so_bored() -> Thought:
    """FUN need critically low (< 15)."""
    return Thought(
        label="So bored...",
        mood_effect=-5.0,
        duration_ticks=6,
        ticks_remaining=6,
        category="fun",
        source_id="critical_fun",
    )


def thought_lonely() -> Thought:
    """SOCIAL need critically low."""
    return Thought(
        label="Feeling really lonely...",
        mood_effect=-5.0,
        duration_ticks=6,
        ticks_remaining=6,
        category="social",
        source_id="critical_social",
    )


def thought_academic_pressure() -> Thought:
    """ACADEMICS need critically low — feels behind."""
    return Thought(
        label="Falling behind on everything",
        mood_effect=-4.0,
        duration_ticks=6,
        ticks_remaining=6,
        category="academic",
        source_id="critical_academics",
    )


def thought_skill_milestone(skill_name: str, level: int) -> Thought:
    """Hit a skill milestone (25/50/75/100)."""
    labels = {
        25:  f"Getting the hang of {skill_name}!",
        50:  f"Really improving at {skill_name}",
        75:  f"Almost mastered {skill_name}!",
        100: f"I'm amazing at {skill_name}!",
    }
    effects = {25: 4.0, 50: 6.0, 75: 8.0, 100: 12.0}
    return Thought(
        label=labels.get(level, f"{skill_name} milestone"),
        mood_effect=effects.get(level, 5.0),
        duration_ticks=48,
        ticks_remaining=48,
        category="activity",
        stackable=True,
    )


def thought_lunch_social() -> Thought:
    """Had a good lunch with people around."""
    return Thought(
        label="Lunch was nice today",
        mood_effect=2.0,
        duration_ticks=18,
        ticks_remaining=18,
        category="social",
        source_id="lunch_social",
    )


def thought_dating(partner_name: str) -> Thought:
    """Started dating someone."""
    return Thought(
        label=f"I'm with {partner_name} now! 💕",
        mood_effect=15.0,
        duration_ticks=96,
        ticks_remaining=96,
        category="social",
        source_id=f"dating_{partner_name}",
    )


def thought_charmed_by(name: str) -> Thought:
    """A Flirt interacted with someone Attractive."""
    return Thought(
        label=f"Can't stop thinking about {name}",
        mood_effect=5.0,
        duration_ticks=24,
        ticks_remaining=24,
        category="social",
        stackable=True,
    )


def thought_good_conversation(friend_name: str) -> Thought:
    """Had a pleasant conversation with someone."""
    return Thought(
        label=f"Good chat with {friend_name}",
        mood_effect=3.0,
        duration_ticks=18,
        ticks_remaining=18,
        category="social",
        stackable=True,
    )


def thought_found_common_ground(friend_name: str) -> Thought:
    """Discovered shared worldview or deep common ground."""
    return Thought(
        label=f"Really clicked with {friend_name}",
        mood_effect=6.0,
        duration_ticks=42,
        ticks_remaining=42,
        category="social",
        stackable=True,
    )


def thought_disagreed_with(friend_name: str) -> Thought:
    """Had a conflicting conversation."""
    return Thought(
        label=f"Got into it with {friend_name}...",
        mood_effect=-3.0,
        duration_ticks=18,
        ticks_remaining=18,
        category="social",
        stackable=True,
    )
