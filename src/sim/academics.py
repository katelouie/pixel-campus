"""Academics system -- classes, grades, and report cards.

Students take classes. Each class has a grade that's driven by:
- A baseline (what the grade drifts toward without effort)
- Skill growth from doing related activities
- A "recent study" bonus that decays if you stop
Grades feed into the points system via periodic report cards.
"""

from dataclasses import dataclass
from enum import Enum

from .models import Skill


class Subject(Enum):
    MATH = "math"
    ENGLISH = "english"
    SCIENCE = "science"
    ART = "art"
    PE = "pe"
    MUSIC = "music"


# Which skill category feeds into each subject's grade
SUBJECT_SKILLS: dict[Subject, Skill] = {
    Subject.MATH: Skill.ACADEMICS,
    Subject.ENGLISH: Skill.ACADEMICS,
    Subject.SCIENCE: Skill.ACADEMICS,
    Subject.ART: Skill.CREATIVITY,
    Subject.PE: Skill.ATHLETICS,
    Subject.MUSIC: Skill.MUSIC,
}


# Points awarded per letter grade on report card day
GRADE_POINTS: dict[str, int] = {
    "A": 15,
    "B": 10,
    "C": 3,
    "D": -5,
    "F": -10,
}


@dataclass
class Grade:
    """A student's grade in one subject."""

    subject: Subject
    value: float = 72.0        # raw grade (0-100), starts at C
    baseline: float = 72.0     # what the grade drifts toward without effort
    recent_bonus: float = 0.0  # temporary boost from recent activity

    # Tuning constants
    DRIFT_RATE: float = 0.01       # 1% drift toward baseline per tick
    BONUS_DECAY: float = 0.3       # recent_bonus decays this much per tick
    BONUS_ON_ACTIVITY: float = 2.0  # bonus added when doing related activity
    MAX_BONUS: float = 10.0        # cap on recent_bonus
    SKILL_TO_GRADE: float = 0.15   # multiplier: skill_gain * this = grade gain

    @property
    def letter(self) -> str:
        """Base letter grade (no +/-). Used for report card points lookup."""
        v = self.effective
        if v >= 90:
            return "A"
        if v >= 80:
            return "B"
        if v >= 70:
            return "C"
        if v >= 60:
            return "D"
        return "F"

    @property
    def letter_full(self) -> str:
        """Letter grade with +/- modifier for display."""
        v = self.effective
        if v >= 97: return "A+"
        if v >= 93: return "A"
        if v >= 90: return "A-"
        if v >= 87: return "B+"
        if v >= 83: return "B"
        if v >= 80: return "B-"
        if v >= 77: return "C+"
        if v >= 73: return "C"
        if v >= 70: return "C-"
        if v >= 67: return "D+"
        if v >= 63: return "D"
        if v >= 60: return "D-"
        return "F"

    @property
    def effective(self) -> float:
        """The displayed grade value (raw + recent bonus, clamped)."""
        return max(0.0, min(100.0, self.value + self.recent_bonus))

    @property
    def report_card_points(self) -> int:
        """Points this grade contributes on report card day."""
        return GRADE_POINTS.get(self.letter, 0)

    def clamp(self) -> None:
        self.value = max(0.0, min(100.0, self.value))
        self.recent_bonus = max(0.0, min(self.MAX_BONUS, self.recent_bonus))


def create_default_grades() -> dict[Subject, Grade]:
    """Create a fresh set of grades for a new student."""
    return {subj: Grade(subject=subj) for subj in Subject}


def tick_grade(grade: Grade) -> None:
    """Per-tick grade maintenance: drift toward baseline, decay recent bonus."""
    # Drift toward baseline (without effort, grades regress to the mean)
    grade.value += (grade.baseline - grade.value) * grade.DRIFT_RATE

    # Decay recent activity bonus
    grade.recent_bonus = max(0.0, grade.recent_bonus - grade.BONUS_DECAY)

    grade.clamp()


def tick_all_grades(grades: dict[Subject, Grade]) -> None:
    """Tick all grades for one student."""
    for grade in grades.values():
        tick_grade(grade)


def apply_activity_to_grades(
    grades: dict[Subject, Grade], skill: Skill, skill_gain: float
) -> None:
    """When a student does an activity, boost grades for related subjects.

    Args:
        grades: The student's grade dict.
        skill: Which skill the activity trained.
        skill_gain: How much skill was gained this tick.
    """
    for subject, related_skill in SUBJECT_SKILLS.items():
        if related_skill == skill and subject in grades:
            grade = grades[subject]
            # Permanent grade growth from skill gain
            grade.value += skill_gain * grade.SKILL_TO_GRADE
            # Temporary "studied recently" bonus
            grade.recent_bonus = min(
                grade.MAX_BONUS, grade.recent_bonus + grade.BONUS_ON_ACTIVITY
            )
            grade.clamp()


def calculate_report_card_points(grades: dict[Subject, Grade]) -> int:
    """Total points from all grades on report card day."""
    return sum(g.report_card_points for g in grades.values())
