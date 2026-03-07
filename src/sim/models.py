"""Core data models for Pixel Campus.

All game entities are defined here as dataclasses. These are pure data:
no display logic, no side effects. The engine manipulates these and
the UI reads from them.
"""

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class Mood(Enum):
    """Emotional state that affects behaviour and point generation."""

    HAPPY = auto()
    NEUTRAL = auto()
    SAD = auto()
    TIRED = auto()

    @property
    def icon(self) -> str:
        return {
            Mood.HAPPY: "😊",
            Mood.NEUTRAL: "😐",
            Mood.SAD: "😢",
            Mood.TIRED: "😴",
        }[self]


class Skill(Enum):
    """Trackable student skills."""

    ACADEMICS = "academics"
    ATHLETICS = "athletics"
    CREATIVITY = "creativity"
    SOCIAL = "social"
    MUSIC = "music"
    PARTY = "party"
    PROTEST = "protest"
    FLIRT = "flirt"


class StudentState(Enum):
    """What a student is doing right now.

    StudentState is the enum that drives the state machine. Each student always has
    exactly one (1) state.
    """

    IDLE = "idle"  # Standing around unoccupied
    TRAVELING = "traveling"  # moving between rooms
    STUDYING = "studying"
    EXERCISING = "exercising"
    CREATING = "creating"  # Art, painting, etc
    SOCIALIZING = "socializing"
    CHATTING = "chatting"  # 1-on-1 interaction with another student
    RESTING = "resting"  # recovering energy


# Map rooms' skill types to activity states
SKILL_TO_ACTIVITY: dict[Skill, StudentState] = {
    Skill.ACADEMICS: StudentState.STUDYING,
    Skill.ATHLETICS: StudentState.EXERCISING,
    Skill.CREATIVITY: StudentState.CREATING,
    Skill.SOCIAL: StudentState.SOCIALIZING,
}


@dataclass
class Room:
    """A location on campus where students can be assigned."""

    name: str
    skill_boost: Skill
    boost_per_tick: float = (
        10.0  # base points added to relevant skill per activity tick
    )
    mood_per_tick: float = 5.0  # base mood delta per activity tick
    capacity: int = 8
    description: str = ""

    # For travel time calculation (like a grid position)
    position: tuple[int, int] = (0, 0)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Room):
            return NotImplemented
        return self.name == other.name


@dataclass
class Student:
    """A single student in the simulation."""

    name: str
    student_id: int

    # Stats (0-100 scale)
    mood_value: float = 70.0
    energy: float = 100.0

    # Skills (0-100 scale)
    skills: dict[Skill, float] = field(default_factory=dict)

    # Preferences: {Skill: multiplier 0.4–1.2}
    # High = loves it (mood boost, faster skill gain)
    # Low = hates it (mood drain, slower gain)
    preferences: dict[Skill, float] = field(default_factory=dict)

    # Current state
    state: StudentState = StudentState.IDLE
    location: Room | None = None  # Current location
    destination: Room | None = None  # Where they're headed (if travelling)
    activity_ticks_left: int = 0  # Ticks remaining on current activity - countdown
    travel_ticks_left: int = 0  # Ticks remaining in transit - countdown
    chat_partner_id: int | None = None  # Who they're talking with

    # Journal
    journal: list[tuple[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.skills:
            self.skills = {s: 0.0 for s in Skill}
        if not self.preferences:
            self.preferences = {s: round(random.uniform(0.4, 1.2), 2) for s in Skill}

    @property
    def mood(self) -> Mood:
        """Derive Mood enum from raw values."""
        if self.energy < 20:
            return Mood.TIRED
        if self.mood_value >= 70:
            return Mood.HAPPY
        if self.mood_value < 40:
            return Mood.SAD
        return Mood.NEUTRAL

    @property
    def favorite_skill(self) -> Skill:
        return max(self.preferences, key=lambda s: self.preferences[s])

    @property
    def dreaded_skill(self) -> Skill:
        return min(self.preferences, key=lambda s: self.preferences[s])

    @property
    def is_busy(self) -> bool:
        """True if student is doing something (aka not idle)."""
        return self.state != StudentState.IDLE

    def clamp_stats(self) -> None:
        """Keep mood and energy within 0-100."""
        self.mood_value = max(0, min(100, self.mood_value))
        self.energy = max(0, min(100, self.energy))
        for skill in self.skills:
            self.skills[skill] = max(0.0, min(100.0, self.skills[skill]))

    def __hash__(self) -> int:
        return hash(self.student_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Student):
            return NotImplemented
        return self.student_id == other.student_id


class FriendshipLevel(Enum):
    """Progression stages of a friendship."""

    STRANGER = 0
    ACQUAINTANCE = 1
    FRIEND = 2
    CLOSE_FRIEND = 3
    BEST_FRIEND = 4

    @property
    def next(self) -> "FriendshipLevel | None":
        vals = list(FriendshipLevel)
        idx = vals.index(self)
        return vals[idx + 1] if idx < len(vals) - 1 else None


@dataclass
class Friendship:
    """The platonic bond between two students."""

    student_id1: int
    student_id2: int
    level: FriendshipLevel = FriendshipLevel.STRANGER
    affinity: int = 0  # 0–100, thresholds trigger level-ups
    history: list[str] = field(default_factory=list)

    @property
    def pair(self) -> tuple[int, int]:
        """Canonical key (lower ID first)."""
        return (
            min(self.student_id1, self.student_id2),
            max(self.student_id1, self.student_id2),
        )


class RomanceLevel(Enum):
    """Progression stages of a romance."""

    PLATONIC = 0
    CRUSH = 1
    DATING = 2

    @property
    def next(self) -> "RomanceLevel | None":
        vals = list(RomanceLevel)
        idx = vals.index(self)
        return vals[idx + 1] if idx < len(vals) - 1 else None


@dataclass
class Romance:
    """The romantic bond between two students."""

    student_id1: int
    student_id2: int
    level: RomanceLevel = RomanceLevel.PLATONIC
    affinity: int = 0  # 0–100, thresholds trigger level-ups
    history: list[str] = field(default_factory=list)

    @property
    def pair(self) -> tuple[int, int]:
        """Canonical key (lower ID first)."""
        return (
            min(self.student_id1, self.student_id2),
            max(self.student_id1, self.student_id2),
        )
