"""Events — school events like Prom, Finals, Art Show.

Events trigger on certain days (every 7th day by default). They
check student skill levels and resolve with point bonuses or penalties.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import GameState

from .models import Skill


@dataclass
class SchoolEvent:
    """A scheduled campus event."""

    name: str
    required_skill: Skill
    skill_threshold: int = 30
    point_reward: int = 50
    point_penalty: int = -10
    description: str = ""


EVENTS: list[SchoolEvent] = [
    SchoolEvent(
        name="Basketball Game",
        required_skill=Skill.ATHLETICS,
        skill_threshold=35,
        point_reward=60,
        description="The big game! Athletic students shine.",
    ),
    SchoolEvent(
        name="Art Show",
        required_skill=Skill.CREATIVITY,
        skill_threshold=30,
        point_reward=50,
        description="Gallery night.",
    ),
    SchoolEvent(
        name="Finals Week",
        required_skill=Skill.ACADEMICS,
        skill_threshold=40,
        point_reward=70,
        description="Finals are here! Hope everyone studied...",
    ),
    SchoolEvent(
        name="Prom",
        required_skill=Skill.SOCIAL,
        skill_threshold=25,
        point_reward=80,
        description="The big dance!",
    ),
]


def check_for_event(state: GameState) -> SchoolEvent | None:
    """Check if an event triggers on this tick.

    Events fire at the start of every 7th day (on tick 0).
    """
    if state.clock.tick != 0 or state.clock.day <= 1:
        return None
    if state.clock.day % 7 == 0:
        idx = (state.clock.day // 7 - 1) % len(EVENTS)
        return EVENTS[idx]
    return None


def resolve_event(state: GameState, event: SchoolEvent) -> list[str]:
    """Run an event. Returns log messages."""
    log: list[str] = []
    log.append(f"EVENT: {event.name}! - {event.description}")

    successes = 0
    for student in state.students:
        skill_level = student.skills.get(event.required_skill, 0)
        if skill_level >= event.skill_threshold:
            successes += 1
            student.mood_value = min(100, student.mood_value + 10)
            log.append(
                f"{student.name} nails it! ({event.required_skill.value}: {skill_level:.0f})"
            )
        else:
            student.mood_value = max(0, student.mood_value - 5)
            log.append(
                f"{student.name} struggles... ({event.required_skill.value}: {skill_level:.0f})"
            )

    ratio = successes / len(state.students) if state.students else 0
    if ratio >= 0.6:
        points = event.point_reward
        log.append(f"Great turnout! +{points} points!")
    elif ratio >= 0.3:
        points = event.point_reward // 2
        log.append(f"Decent showing. +{points} points.")
    else:
        points = event.point_penalty
        log.append(f"Rough night. {points} points")

    state.total_points += points
    return log
