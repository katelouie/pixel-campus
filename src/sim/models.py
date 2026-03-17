"""Core data models for Pixel Campus.

All game entities are defined here as dataclasses. These are pure data:
no display logic, no side effects. The engine manipulates these and
the UI reads from them.
"""

import random
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any

from .needs import Need, NeedType, compute_needs_mood, create_default_needs
from .personality import Personality
from .thoughts import Thought, sum_thought_effects
from .traits import Trait, combined_skill_mult


class Mood(Enum):
    """Emotional state that affects behaviour and point generation."""

    HAPPY = auto()
    NEUTRAL = auto()
    SAD = auto()
    TIRED = auto()

    @property
    def icon(self) -> str:
        return {
            Mood.HAPPY: "\U0001f60a",
            Mood.NEUTRAL: "\U0001f610",
            Mood.SAD: "\U0001f622",
            Mood.TIRED: "\U0001f634",
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


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"


class Year(Enum):
    FRESHMAN  = "freshman"
    SOPHOMORE = "sophomore"
    JUNIOR    = "junior"
    SENIOR    = "senior"


_BASE_AGE_BY_YEAR: dict["Year", int] = {
    Year.FRESHMAN:  14,
    Year.SOPHOMORE: 15,
    Year.JUNIOR:    16,
    Year.SENIOR:    17,
}


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
    boost_per_tick: float = 1.5
    capacity: int = 8
    description: str = ""

    # Which needs this room satisfies (and by how much per activity tick)
    # Positive = satisfies, negative = drains
    needs_satisfied: dict[str, float] = field(default_factory=dict)

    # For travel time calculation (like a grid position)
    position: tuple[int, int] = (0, 0)

    # Tiled sit/stand point name prefixes that map to this room (UI layer reads this)
    sit_prefixes: list[str] = field(default_factory=list)

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
    gender: Gender = Gender.NON_BINARY
    year: Year = Year.FRESHMAN
    personality: Personality | None = None

    # Needs system (replaces old mood_value + energy)
    needs: dict[NeedType, Need] = field(default_factory=create_default_needs)

    # Skills (0-100 scale)
    skills: dict[Skill, float] = field(default_factory=dict)

    # Personality traits (1-2 per student, assigned at creation)
    traits: list[Trait] = field(default_factory=list)

    # Current state
    state: StudentState = StudentState.IDLE
    location: Room | None = None
    destination: Room | None = None
    activity_ticks_left: int = 0
    travel_ticks_left: int = 0
    chat_partner_id: int | None = None

    # Grades (initialized by engine.py via academics.create_default_grades)
    # Typed as Any to avoid circular import with academics module
    grades: dict = field(default_factory=dict)

    # Thoughts (mood modifiers with durations)
    thoughts: list[Thought] = field(default_factory=list)

    # Journal
    journal: list[tuple[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.skills:
            self.skills = {s: 0.0 for s in Skill}

    # ------------------------------------------------------------------
    # Mood (backward-compatible properties)
    # ------------------------------------------------------------------

    @property
    def mood_value(self) -> float:
        """Overall mood computed from needs + active thoughts (0-100).

        Needs provide the baseline (centered at 50), thoughts shift it up/down.
        """
        needs_baseline = compute_needs_mood(self.needs)
        thought_sum = sum_thought_effects(self.thoughts)
        return max(0.0, min(100.0, needs_baseline + thought_sum))

    @property
    def age(self) -> int:
        """Derived from school year + zodiac sign birth-month offset.

        Signs born Jan–Aug are the 'older' cohort in their grade (already had
        their birthday before the Sep 1 school-year cutoff), so they get +1.
        Signs born Sep–Dec are the 'younger' cohort (base age).
        """
        base = _BASE_AGE_BY_YEAR[self.year]
        if self.personality is not None:
            return base + self.personality.age_offset()
        return base

    @property
    def energy(self) -> float:
        """Backward-compat alias for REST need value."""
        return self.needs[NeedType.REST].value

    @energy.setter
    def energy(self, val: float) -> None:
        self.needs[NeedType.REST].value = max(0.0, min(100.0, val))

    @property
    def mood(self) -> Mood:
        """Derive Mood enum from needs."""
        if self.energy < 20:
            return Mood.TIRED
        if self.mood_value >= 70:
            return Mood.HAPPY
        if self.mood_value < 40:
            return Mood.SAD
        return Mood.NEUTRAL

    @property
    def favorite_skill(self) -> Skill:
        """Skill with the highest combined trait multiplier."""
        core_skills = [Skill.ACADEMICS, Skill.ATHLETICS, Skill.CREATIVITY, Skill.SOCIAL, Skill.MUSIC]
        if self.traits:
            return max(core_skills, key=lambda s: combined_skill_mult(self.traits, s.value))
        return random.choice(core_skills)

    @property
    def dreaded_skill(self) -> Skill:
        """Skill with the lowest combined trait multiplier."""
        core_skills = [Skill.ACADEMICS, Skill.ATHLETICS, Skill.CREATIVITY, Skill.SOCIAL, Skill.MUSIC]
        if self.traits:
            return min(core_skills, key=lambda s: combined_skill_mult(self.traits, s.value))
        return random.choice(core_skills)

    @property
    def is_busy(self) -> bool:
        """True if student is doing something (aka not idle)."""
        return self.state != StudentState.IDLE

    def clamp_stats(self) -> None:
        """Keep all stats within bounds."""
        for need in self.needs.values():
            need.clamp()
        for skill in self.skills:
            self.skills[skill] = max(0.0, min(100.0, self.skills[skill]))

    def __hash__(self) -> int:
        return hash(self.student_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Student):
            return NotImplemented
        return self.student_id == other.student_id


class FriendshipLevel(IntEnum):
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
    affinity: int = 0  # 0-100, thresholds trigger level-ups
    history: list[str] = field(default_factory=list)

    @property
    def pair(self) -> tuple[int, int]:
        """Canonical key (lower ID first)."""
        return (
            min(self.student_id1, self.student_id2),
            max(self.student_id1, self.student_id2),
        )


class RomanceLevel(IntEnum):
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
    """The directed romantic bond between two students.

    Feelings are tracked independently — one student can have a crush before
    the other reciprocates. student_id1 is always the lower ID (canonical key).
    """

    student_id1: int
    student_id2: int
    feelings_1: RomanceLevel = RomanceLevel.PLATONIC  # how id1 feels about id2
    feelings_2: RomanceLevel = RomanceLevel.PLATONIC  # how id2 feels about id1
    affinity_1: int = 0  # id1's affinity toward id2 (0-100)
    affinity_2: int = 0  # id2's affinity toward id1 (0-100)
    history: list[str] = field(default_factory=list)

    @property
    def pair(self) -> tuple[int, int]:
        """Canonical key (lower ID first)."""
        return (
            min(self.student_id1, self.student_id2),
            max(self.student_id1, self.student_id2),
        )

    def feelings_of(self, student_id: int) -> RomanceLevel:
        """How the given student feels toward the other."""
        return self.feelings_1 if student_id == self.student_id1 else self.feelings_2

    def affinity_of(self, student_id: int) -> int:
        """Affinity score for the given student."""
        return self.affinity_1 if student_id == self.student_id1 else self.affinity_2

    def set_feelings(self, student_id: int, level: RomanceLevel) -> None:
        if student_id == self.student_id1:
            self.feelings_1 = level
        else:
            self.feelings_2 = level

    def add_affinity(self, student_id: int, amount: int) -> None:
        if student_id == self.student_id1:
            self.affinity_1 = min(100, self.affinity_1 + amount)
        else:
            self.affinity_2 = min(100, self.affinity_2 + amount)

    @property
    def is_mutual_crush(self) -> bool:
        return self.feelings_1 >= RomanceLevel.CRUSH and self.feelings_2 >= RomanceLevel.CRUSH

    @property
    def is_dating(self) -> bool:
        return self.feelings_1 == RomanceLevel.DATING and self.feelings_2 == RomanceLevel.DATING

    @property
    def is_unrequited(self) -> bool:
        """One side has feelings, the other is still platonic."""
        f1, f2 = self.feelings_1, self.feelings_2
        return (f1 > RomanceLevel.PLATONIC) != (f2 > RomanceLevel.PLATONIC)
