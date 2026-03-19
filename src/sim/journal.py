"""Journal system — the emotional core of Pixel Campus.

Students write about their experiences in their own voice, driven by personality
traits. Generation modes:
- End-of-day retrospective (thought-driven or mood-based, trait-voiced)
- Start-of-day prospective (forward-looking based on active state)
- Event-triggered mid-day (EventBus subscriber fires on significant moments)
- Activity reflection (after completing room activities, interacts with fav/dread)
- Mood threshold crossing (happy/sad/crisis)
- Guaranteed minimum (boring-day special text if nothing else fired)

All template text lives in src/data/journal_templates.json. This module is pure logic.
"""

import json
import random
from pathlib import Path
from typing import Any

from .game_events import GameEvent, GameEventType
from .models import JournalEntry, Mood, Skill, Student

# ── Load template data ──────────────────────────────────────────────

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "journal_templates.json"

with open(_TEMPLATE_PATH) as f:
    _TEMPLATES: dict[str, Any] = json.load(f)

_TRAIT_VOICE: dict[str, dict[str, list[str]]] = _TEMPLATES["trait_voice"]
_GENERIC_MOOD: dict[str, list[str]] = _TEMPLATES["generic_mood"]
_GENERIC_EVENT: dict[str, list[str]] = _TEMPLATES["generic_event"]
_GENERIC_PROSPECTIVE: list[str] = _TEMPLATES["generic_prospective"]
_THOUGHT_JOURNAL: dict[str, list[str]] = _TEMPLATES["thought_journal"]
_ZODIAC_FLAVOR: dict[str, list[str]] = _TEMPLATES["zodiac_flavor"]
_BORING_DAY: dict[str, Any] = _TEMPLATES["boring_day"]
_ACTIVITY_REFLECTION: dict[str, Any] = _TEMPLATES["activity_reflection"]
_MOOD_THRESHOLD: dict[str, Any] = _TEMPLATES["mood_threshold"]
_GRADE_MILESTONE: dict[str, Any] = _TEMPLATES["grade_milestone"]
_LONELINESS: dict[str, Any] = _TEMPLATES["loneliness"]
_NEW_ROOM: dict[str, Any] = _TEMPLATES["new_room"]

# ── Constants ───────────────────────────────────────────────────────

DAILY_CAP = 6               # max journal entries per student per day
ACTIVITY_REFLECTION_PROB = 0.18  # chance per activity completion
MOOD_HAPPY_THRESHOLD = 70   # mood above this → happy entry
MOOD_SAD_THRESHOLD = 35     # mood below this → sad entry
MOOD_CRISIS_THRESHOLD = 20  # mood below this → crisis entry
LONELINESS_THRESHOLD = 20   # social need below this → loneliness entry

# ── Probability table for event-triggered entries ───────────────────

_EVENT_PROBABILITY: dict[str, float] = {
    "dating":             1.00,
    "crush":              0.75,
    "friendship_levelup": 0.50,
    "conflict":           0.65,
    "match":              0.40,
    "grade_failed":       0.85,
    "grade_improved":     0.60,
    "grade_milestone":    0.70,
    "encouraged":         0.80,
    "skill_milestone":    0.55,
    "jealous":            0.45,
    "mood_happy":         0.50,
    "mood_sad":           0.60,
    "mood_crisis":        0.80,
    "loneliness":         0.50,
    "new_room":           0.40,
}

# ── Helpers ──────────────────────────────────────────────────────────


def _primary_trait_name(student: Student) -> str | None:
    """Get the student's first trait name, if any."""
    return student.traits[0].name if student.traits else None


def _try_trait_voice(student: Student, situation: str, **kwargs: str) -> str | None:
    """Try to generate a trait-voiced entry from the main trait_voice section.

    50% chance to use trait voice; falls back to None so caller can use generic.
    """
    trait_name = _primary_trait_name(student)
    if trait_name is None:
        return None

    templates = _TRAIT_VOICE.get(trait_name, {}).get(situation)
    if not templates:
        return None

    if random.random() > 0.50:
        return None

    return random.choice(templates).format_map(_safe_format(kwargs))


def _try_sectional_trait(
    section: dict[str, Any], trait_key: str, student: Student, **kwargs: str,
) -> str | None:
    """Try to get a trait-voiced entry from a top-level section's trait sub-dict.

    Used for sections like boring_day, activity_reflection, mood_threshold
    that have their own nested trait dicts rather than living inside _TRAIT_VOICE.
    """
    trait_name = _primary_trait_name(student)
    if trait_name is None:
        return None

    trait_dict = section.get(trait_key, {})
    templates = trait_dict.get(trait_name)
    if not templates:
        return None

    if random.random() > 0.55:
        return None

    return random.choice(templates).format_map(_safe_format(kwargs))


def _zodiac_flavor(student: Student) -> str | None:
    """Return a zodiac-flavored line (40% chance), or None."""
    if not student.personality:
        return None
    zodiac = student.personality.zodiac.value
    tags = _ZODIAC_FLAVOR.get(zodiac, [])
    return random.choice(tags) if tags and random.random() < 0.4 else None


def _mood_key(student: Student) -> str:
    """Map Mood enum to template dict key."""
    return {
        Mood.HAPPY: "happy",
        Mood.NEUTRAL: "neutral",
        Mood.SAD: "sad",
        Mood.TIRED: "tired",
    }[student.mood]


def _base_format_vars(student: Student) -> dict[str, str]:
    """Common template variables available for mood-based entries."""
    loc = (f"Spent time in the {student.location.name}."
           if student.location else "Just wandered around campus.")
    return {
        "fav_skill": student.favorite_skill.value,
        "dread_skill": student.dreaded_skill.value,
        "loc": loc,
    }


def _safe_format(kwargs: dict[str, str]) -> dict[str, str]:
    """Wrap kwargs in a defaultdict-like that returns {key} for missing keys."""
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return f"{{{key}}}"
    return _SafeDict(kwargs)


def _entries_today(student: Student, day: int) -> int:
    """Count how many journal entries a student has for the given day."""
    return sum(1 for e in student.journal if e.day == day)


def _at_cap(student: Student, day: int) -> bool:
    """True if the student has hit the daily journal entry cap."""
    return _entries_today(student, day) >= DAILY_CAP


def _append(student: Student, entry: JournalEntry) -> None:
    """Append a journal entry to a student's journal (respects daily cap)."""
    if not _at_cap(student, entry.day):
        student.journal.append(entry)


# ── End-of-day retrospective ────────────────────────────────────────


def generate_journal_entry(student: Student, day: int, tick: int) -> JournalEntry:
    """Generate an end-of-day journal entry reflecting the student's current state.

    Priority chain:
    1. Trait-voiced mood entry (50% chance if trait matches)
    2. Thought-driven entry (if strong active thought exists)
    3. Generic mood-based entry
    All optionally flavored with zodiac snippet.
    """
    base_vars = _base_format_vars(student)
    mood = _mood_key(student)

    # Try trait voice first
    text = _try_trait_voice(student, mood, **base_vars)

    # Try thought-driven entry
    if text is None and student.thoughts:
        strongest = max(student.thoughts, key=lambda t: abs(t.mood_effect))
        templates = _THOUGHT_JOURNAL.get(strongest.category)
        if templates:
            text = random.choice(templates).format_map(
                _safe_format({"thought": strongest.label, **base_vars})
            )

    # Fallback to generic mood
    if text is None:
        pool = _GENERIC_MOOD.get(mood, [])
        if pool:
            text = random.choice(pool).format_map(_safe_format(base_vars))
        else:
            text = "Nothing to write about today."

    # Zodiac flavor injection
    flavor = _zodiac_flavor(student)
    if flavor:
        text = f"{text} {flavor}"

    return JournalEntry(text=text, day=day, tick=tick, trigger="end_of_day")


# ── Start-of-day prospective ────────────────────────────────────────


def generate_prospective_entry(
    student: Student, day: int, tick: int,
    crush_name: str | None = None,
) -> JournalEntry | None:
    """Generate a start-of-day anticipatory entry. ~50% chance to fire.

    Scans for forward-looking material: crush, favorite skill, general anticipation.
    Returns None if the student doesn't journal this morning.
    """
    if random.random() > 0.50:
        return None

    fmt_vars = {
        "fav_skill": student.favorite_skill.value,
        "dread_skill": student.dreaded_skill.value,
    }
    if crush_name:
        fmt_vars["crush"] = crush_name

    # Try trait-voiced prospective
    text = _try_trait_voice(student, "prospective", **fmt_vars)

    # Fallback to generic
    if text is None:
        text = random.choice(_GENERIC_PROSPECTIVE).format_map(_safe_format(fmt_vars))

    return JournalEntry(text=text, day=day, tick=tick, trigger="start_of_day")


# ── Event-triggered mid-day ─────────────────────────────────────────


def generate_event_entry(
    student: Student, day: int, tick: int,
    trigger: str, **context: str,
) -> JournalEntry | None:
    """Generate a journal entry for a significant event (dating, conflict, etc.).

    Returns None if the probability roll fails, at daily cap, or no templates match.
    """
    if _at_cap(student, day):
        return None

    prob = _EVENT_PROBABILITY.get(trigger, 0.50)
    if random.random() > prob:
        return None

    # Try trait-voiced event entry
    text = _try_trait_voice(student, trigger, **context)

    # Fallback to generic event templates
    if text is None:
        pool = _GENERIC_EVENT.get(trigger, [])
        if pool:
            text = random.choice(pool).format_map(_safe_format(context))
        else:
            return None

    return JournalEntry(text=text, day=day, tick=tick, trigger=trigger)


# ── Activity reflection ─────────────────────────────────────────────


def generate_activity_reflection(
    student: Student, day: int, tick: int,
    skill: Skill, room_name: str,
) -> JournalEntry | None:
    """Generate a journal entry after completing an activity in a room.

    Interacts with favorite/dreaded skill to pick the right register.
    ~18% chance to fire per activity completion.
    """
    if _at_cap(student, day):
        return None

    if random.random() > ACTIVITY_REFLECTION_PROB:
        return None

    fav = student.favorite_skill
    dread = student.dreaded_skill
    fmt = {"skill": skill.value, "room": room_name,
           "fav_skill": fav.value, "dread_skill": dread.value}

    # Determine variant: fav, dread, improving, or neutral
    skill_level = student.skills.get(skill, 0.0)

    if skill == fav:
        variant = "fav"
    elif skill == dread:
        variant = "dread"
    elif skill_level > 50:
        variant = "improving"
    else:
        variant = "neutral"

    # Try trait-voiced from activity_reflection section
    trait_key = f"{variant}_trait"
    text = _try_sectional_trait(_ACTIVITY_REFLECTION, trait_key, student, **fmt)

    # Fallback to generic activity variant
    if text is None:
        pool = _ACTIVITY_REFLECTION.get(f"{variant}_generic", [])
        if pool:
            text = random.choice(pool).format_map(_safe_format(fmt))

    if text is None:
        return None

    return JournalEntry(text=text, day=day, tick=tick, trigger=f"activity_{variant}")


# ── Mood threshold crossing ─────────────────────────────────────────


def generate_mood_entry(
    student: Student, day: int, tick: int,
    crossing: str,
) -> JournalEntry | None:
    """Generate a journal entry when mood crosses a significant threshold.

    crossing: "happy", "sad", or "crisis"
    """
    if _at_cap(student, day):
        return None

    prob = _EVENT_PROBABILITY.get(f"mood_{crossing}", 0.50)
    if random.random() > prob:
        return None

    # Try trait voice from mood_threshold section (crisis has its own trait dict)
    text = None
    if crossing == "crisis":
        text = _try_sectional_trait(_MOOD_THRESHOLD, "crisis_trait", student)

    # Fallback to generic mood threshold
    if text is None:
        pool = _MOOD_THRESHOLD.get(f"{crossing}_generic", [])
        if pool:
            text = random.choice(pool)

    if text is None:
        return None

    return JournalEntry(text=text, day=day, tick=tick, trigger=f"mood_{crossing}")


# ── Grade milestone ─────────────────────────────────────────────────


def generate_grade_milestone_entry(
    student: Student, day: int, tick: int,
    subject: str, grade: str,
) -> JournalEntry | None:
    """Generate a journal entry when grade crosses a base letter threshold upward."""
    if _at_cap(student, day):
        return None

    prob = _EVENT_PROBABILITY.get("grade_milestone", 0.70)
    if random.random() > prob:
        return None

    fmt = {"subject": subject, "grade": grade}

    # Try sectional trait
    text = _try_sectional_trait(_GRADE_MILESTONE, "trait", student, **fmt)

    # Fallback to generic
    if text is None:
        pool = _GRADE_MILESTONE.get("generic", [])
        if pool:
            text = random.choice(pool).format_map(_safe_format(fmt))

    if text is None:
        return None

    return JournalEntry(text=text, day=day, tick=tick, trigger="grade_milestone")


# ── Loneliness ──────────────────────────────────────────────────────


def generate_loneliness_entry(
    student: Student, day: int, tick: int,
) -> JournalEntry | None:
    """Generate a journal entry when social need drops critically low."""
    if _at_cap(student, day):
        return None

    prob = _EVENT_PROBABILITY.get("loneliness", 0.50)
    if random.random() > prob:
        return None

    text = _try_sectional_trait(_LONELINESS, "trait", student)

    if text is None:
        pool = _LONELINESS.get("generic", [])
        if pool:
            text = random.choice(pool)

    if text is None:
        return None

    return JournalEntry(text=text, day=day, tick=tick, trigger="loneliness")


# ── New room discovery ──────────────────────────────────────────────


def generate_new_room_entry(
    student: Student, day: int, tick: int,
    room_name: str,
) -> JournalEntry | None:
    """Generate a journal entry on first visit to a room."""
    if _at_cap(student, day):
        return None

    prob = _EVENT_PROBABILITY.get("new_room", 0.40)
    if random.random() > prob:
        return None

    fmt = {"room": room_name}
    text = _try_sectional_trait(_NEW_ROOM, "trait", student, **fmt)

    if text is None:
        pool = _NEW_ROOM.get("generic", [])
        if pool:
            text = random.choice(pool).format_map(_safe_format(fmt))

    if text is None:
        return None

    return JournalEntry(text=text, day=day, tick=tick, trigger="new_room")


# ── Guaranteed minimum (boring day) ─────────────────────────────────


def generate_boring_day_entry(student: Student, day: int, tick: int) -> JournalEntry:
    """Generate the guaranteed minimum entry when nothing else fired all day.

    Always succeeds — no probability roll. This is the fallback that ensures
    every student has at least one journal entry per day.
    """
    trait_name = _primary_trait_name(student)

    # Try trait-specific boring day text
    text = None
    if trait_name:
        templates = _BORING_DAY.get(trait_name)
        if templates:
            text = random.choice(templates)

    # Fallback to generic boring day
    if text is None:
        text = random.choice(_BORING_DAY["generic"])

    return JournalEntry(text=text, day=day, tick=tick, trigger="boring_day")


# ── EventBus subscriber ────────────────────────────────────────────


class JournalSubscriber:
    """Subscribes to GameEventBus and generates mid-day journal entries.

    Holds a reference to the GameState so it can look up the current day/tick
    and resolve student names. Also tracks per-student state for mood thresholds,
    visited rooms, and loneliness detection.
    """

    def __init__(self, state: Any) -> None:
        # state is GameState — typed as Any to avoid circular import
        self._state = state
        self._students: dict[int, Student] = {s.student_id: s for s in state.students}

        # Per-student tracking
        self._last_mood_bracket: dict[int, str] = {}  # sid -> "high"/"mid"/"low"/"crisis"
        self._visited_rooms: dict[int, set[str]] = {s.student_id: set() for s in state.students}
        self._loneliness_fired_today: dict[int, bool] = {}  # reset each day
        # Grade letter snapshot: {sid: {subject_str: "C"}} — updated on report card
        self._last_grade_letters: dict[int, dict[str, str]] = {}

        # Initialize mood brackets and grade snapshots
        for s in state.students:
            self._last_mood_bracket[s.student_id] = self._mood_bracket(s)
            self._last_grade_letters[s.student_id] = {
                subj.value: grade.letter for subj, grade in s.grades.items()
            }

    @staticmethod
    def _mood_bracket(student: Student) -> str:
        """Classify mood into brackets for threshold detection."""
        mv = student.mood_value
        if mv >= MOOD_HAPPY_THRESHOLD:
            return "high"
        if mv < MOOD_CRISIS_THRESHOLD:
            return "crisis"
        if mv < MOOD_SAD_THRESHOLD:
            return "low"
        return "mid"

    def _student(self, sid: int) -> Student | None:
        return self._students.get(sid)

    def _day(self) -> int:
        return self._state.clock.day

    def _tick(self) -> int:
        return self._state.clock.tick

    def _other_name(self, event: GameEvent, for_sid: int) -> str:
        """Resolve the 'other' student's name in a two-student event."""
        for sid in event.student_ids:
            if sid != for_sid:
                other = self._student(sid)
                return other.name if other else "someone"
        return "someone"

    # ── Tick-driven checks (called from engine each tick) ───────────

    def tick_check(self) -> None:
        """Run per-tick checks: mood threshold crossings, loneliness, new rooms.

        Called from engine.tick() after processing all students.
        """
        from .needs import NeedType

        day, tick = self._day(), self._tick()

        for s in self._state.students:
            sid = s.student_id

            # Mood threshold crossing
            new_bracket = self._mood_bracket(s)
            old_bracket = self._last_mood_bracket.get(sid, "mid")
            if new_bracket != old_bracket:
                self._last_mood_bracket[sid] = new_bracket
                # Only fire on significant crossings
                if new_bracket == "high" and old_bracket != "high":
                    entry = generate_mood_entry(s, day, tick, "happy")
                    if entry:
                        _append(s, entry)
                elif new_bracket == "crisis" and old_bracket != "crisis":
                    entry = generate_mood_entry(s, day, tick, "crisis")
                    if entry:
                        _append(s, entry)
                elif new_bracket == "low" and old_bracket in ("mid", "high"):
                    entry = generate_mood_entry(s, day, tick, "sad")
                    if entry:
                        _append(s, entry)

            # Loneliness (social need critically low, once per day)
            if not self._loneliness_fired_today.get(sid, False):
                social = s.needs.get(NeedType.SOCIAL)
                if social and social.value < LONELINESS_THRESHOLD:
                    entry = generate_loneliness_entry(s, day, tick)
                    if entry:
                        _append(s, entry)
                        self._loneliness_fired_today[sid] = True

            # New room discovery
            if s.location is not None:
                room_name = s.location.name
                if room_name not in self._visited_rooms[sid]:
                    self._visited_rooms[sid].add(room_name)
                    entry = generate_new_room_entry(s, day, tick, room_name)
                    if entry:
                        _append(s, entry)

    def on_activity_complete(self, student: Student, skill: Skill, room_name: str) -> None:
        """Called when a student completes an activity in a room."""
        entry = generate_activity_reflection(
            student, self._day(), self._tick(), skill, room_name,
        )
        if entry:
            _append(student, entry)

    def on_day_reset(self) -> None:
        """Called at start of new day to reset daily tracking."""
        self._loneliness_fired_today.clear()

    def on_report_card(self) -> None:
        """Called after report cards. Detects grade milestone crossings (D→C, C→B, B→A).

        Compares current grade letters to the snapshot taken at the last report card.
        """
        _BASE_LETTERS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        day, tick = self._day(), self._tick()

        for s in self._state.students:
            sid = s.student_id
            old_letters = self._last_grade_letters.get(sid, {})

            for subj, grade in s.grades.items():
                new_letter = grade.letter[0]  # "B+" -> "B"
                old_letter = old_letters.get(subj.value, new_letter)
                old_letter = old_letter[0] if old_letter else new_letter

                new_rank = _BASE_LETTERS.get(new_letter, 0)
                old_rank = _BASE_LETTERS.get(old_letter, 0)

                if new_rank > old_rank:
                    entry = generate_grade_milestone_entry(
                        s, day, tick, subj.value.capitalize(), new_letter,
                    )
                    if entry:
                        _append(s, entry)

            # Update snapshot
            self._last_grade_letters[sid] = {
                subj.value: grade.letter for subj, grade in s.grades.items()
            }

    # ── EventBus handlers ───────────────────────────────────────────

    def handle_romance_dating(self, event: GameEvent) -> None:
        for sid in event.student_ids:
            s = self._student(sid)
            if s is None:
                continue
            partner = self._other_name(event, sid)
            entry = generate_event_entry(s, self._day(), self._tick(),
                                         "dating", partner=partner)
            if entry:
                _append(s, entry)

    def handle_romance_spark(self, event: GameEvent) -> None:
        if len(event.student_ids) < 2:
            return
        crusher = self._student(event.student_ids[0])
        target = self._student(event.student_ids[1])
        if crusher and target:
            entry = generate_event_entry(crusher, self._day(), self._tick(),
                                         "crush", crush=target.name)
            if entry:
                _append(crusher, entry)

    def handle_friendship_levelup(self, event: GameEvent) -> None:
        for sid in event.student_ids:
            s = self._student(sid)
            if s is None:
                continue
            friend = self._other_name(event, sid)
            entry = generate_event_entry(s, self._day(), self._tick(),
                                         "friendship_levelup", friend=friend)
            if entry:
                _append(s, entry)

    def handle_chat_conflict(self, event: GameEvent) -> None:
        for sid in event.student_ids:
            s = self._student(sid)
            if s is None:
                continue
            other = self._other_name(event, sid)
            entry = generate_event_entry(s, self._day(), self._tick(),
                                         "conflict", other=other)
            if entry:
                _append(s, entry)

    def handle_chat_match(self, event: GameEvent) -> None:
        for sid in event.student_ids:
            s = self._student(sid)
            if s is None:
                continue
            other = self._other_name(event, sid)
            entry = generate_event_entry(s, self._day(), self._tick(),
                                         "match", other=other)
            if entry:
                _append(s, entry)

    def handle_grade_failed(self, event: GameEvent) -> None:
        for sid in event.student_ids:
            s = self._student(sid)
            if s is None:
                continue
            subject = event.data.get("subject", "a subject")
            entry = generate_event_entry(s, self._day(), self._tick(),
                                         "grade_failed", subject=subject)
            if entry:
                _append(s, entry)

    def subscribe(self, bus: "GameEventBus") -> None:
        """Register all handlers on the event bus."""
        bus.subscribe(GameEventType.ROMANCE_DATING, self.handle_romance_dating)
        bus.subscribe(GameEventType.ROMANCE_SPARK, self.handle_romance_spark)
        bus.subscribe(GameEventType.FRIENDSHIP_LEVEL_UP, self.handle_friendship_levelup)
        bus.subscribe(GameEventType.CHAT_CONFLICT, self.handle_chat_conflict)
        bus.subscribe(GameEventType.CHAT_MATCH, self.handle_chat_match)
        bus.subscribe(GameEventType.GRADE_FAILED, self.handle_grade_failed)
