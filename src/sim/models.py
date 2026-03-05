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
            Mood.NEUTRAL:"😐",
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

@dataclass
class Room:
    """A location on campus where students can be assigned."""
    name: str
    skill_boost: Skill
    boost_amount: int = 10 # base points added to relevant skill
    mood_effect: int = 5 # base mood delta
    capacity: int = 8
    description: str = ""

    def __hash__(self) -> int:
        return hash(self.name)

@dataclass
class Student
    """A single student in the simulation."""
    name: str
    student_int: int