"""Save/load serialization for Pixel Campus.

Converts the full GameState to/from a JSON-compatible dict. Each dataclass
gets a to_dict/from_dict pair. Enums serialize as their .value strings.
Rooms and traits are NOT serialized — they're reloaded from data files and
matched by name.

Usage:
    from src.sim.serialization import save_game, load_game
    save_game(state, "saves/slot1.json")
    state = load_game("saves/slot1.json")
"""

import json
from pathlib import Path
from typing import Any

from .academics import Grade, Subject
from .clock import GameClock
from .models import (
    CharacterAppearance, Friendship, FriendshipLevel, Gender, JournalEntry,
    Romance, RomanceLevel, Room, Skill, Student, StudentState, Year,
)
from .needs import Need, NeedType
from .personality import (
    MusicGenre, MovieGenre, Personality, RomanceInterest,
    TimeOfDay, Weather, Worldview, ZodiacSign,
)
from .thoughts import Thought
from .traits import Trait


# ── Primitive serializers ───────────────────────────────────────────


def _need_to_dict(need: Need) -> dict:
    return {
        "need_type": need.need_type.value,
        "value": need.value,
        "decay_per_tick": need.decay_per_tick,
        "weight": need.weight,
    }


def _need_from_dict(d: dict) -> Need:
    return Need(
        need_type=NeedType(d["need_type"]),
        value=d["value"],
        decay_per_tick=d.get("decay_per_tick", 0.5),
        weight=d.get("weight", 1.0),
    )


def _thought_to_dict(t: Thought) -> dict:
    return {
        "label": t.label,
        "mood_effect": t.mood_effect,
        "duration_ticks": t.duration_ticks,
        "ticks_remaining": t.ticks_remaining,
        "category": t.category,
        "stackable": t.stackable,
        "source_id": t.source_id,
    }


def _thought_from_dict(d: dict) -> Thought:
    return Thought(
        label=d["label"],
        mood_effect=d["mood_effect"],
        duration_ticks=d["duration_ticks"],
        ticks_remaining=d["ticks_remaining"],
        category=d.get("category", ""),
        stackable=d.get("stackable", False),
        source_id=d.get("source_id", ""),
    )


def _grade_to_dict(g: Grade) -> dict:
    return {
        "subject": g.subject.value,
        "value": g.value,
        "baseline": g.baseline,
        "recent_bonus": g.recent_bonus,
    }


def _grade_from_dict(d: dict) -> Grade:
    return Grade(
        subject=Subject(d["subject"]),
        value=d["value"],
        baseline=d["baseline"],
        recent_bonus=d.get("recent_bonus", 0.0),
    )


def _personality_to_dict(p: Personality) -> dict:
    return {
        "zodiac": p.zodiac.value,
        "music_genre": p.music_genre.value,
        "movie_genre": p.movie_genre.value,
        "time_of_day": p.time_of_day.value,
        "weather": p.weather.value,
        "romance_interest": [ri.value for ri in p.romance_interest],
        "worldview": p.worldview.value,
    }


def _personality_from_dict(d: dict) -> Personality:
    return Personality(
        zodiac=ZodiacSign(d["zodiac"]),
        music_genre=MusicGenre(d["music_genre"]),
        movie_genre=MovieGenre(d["movie_genre"]),
        time_of_day=TimeOfDay(d["time_of_day"]),
        weather=Weather(d["weather"]),
        romance_interest=[RomanceInterest(ri) for ri in d["romance_interest"]],
        worldview=Worldview(d["worldview"]),
    )


def _appearance_to_dict(a: CharacterAppearance) -> dict:
    return {
        "body": a.body, "eyes": a.eyes,
        "outfit": a.outfit, "outfit_color": a.outfit_color,
        "hairstyle": a.hairstyle, "hair_color": a.hair_color,
        "accessory": a.accessory, "accessory_color": a.accessory_color,
    }


def _appearance_from_dict(d: dict) -> CharacterAppearance:
    return CharacterAppearance(
        body=d["body"], eyes=d["eyes"],
        outfit=d["outfit"], outfit_color=d["outfit_color"],
        hairstyle=d["hairstyle"], hair_color=d["hair_color"],
        accessory=d.get("accessory"), accessory_color=d.get("accessory_color"),
    )


def _journal_to_dict(j: JournalEntry) -> dict:
    return {
        "text": j.text,
        "day": j.day,
        "tick": j.tick,
        "trigger": j.trigger,
    }


def _journal_from_dict(d: dict) -> JournalEntry:
    return JournalEntry(
        text=d["text"],
        day=d["day"],
        tick=d["tick"],
        trigger=d["trigger"],
    )


# ── Student ─────────────────────────────────────────────────────────


def _student_to_dict(s: Student) -> dict:
    return {
        "name": s.name,
        "student_id": s.student_id,
        "gender": s.gender.value,
        "year": s.year.value,
        "personality": _personality_to_dict(s.personality) if s.personality else None,
        "appearance": _appearance_to_dict(s.appearance) if s.appearance else None,
        "needs": {nt.value: _need_to_dict(n) for nt, n in s.needs.items()},
        "skills": {sk.value: val for sk, val in s.skills.items()},
        "traits": [t.name for t in s.traits],  # save trait NAMES, reload from data
        "state": s.state.value,
        "activity_ticks_left": s.activity_ticks_left,
        "travel_ticks_left": s.travel_ticks_left,
        "chat_partner_id": s.chat_partner_id,
        "grades": {subj.value: _grade_to_dict(g) for subj, g in s.grades.items()},
        "thoughts": [_thought_to_dict(t) for t in s.thoughts],
        "journal": [_journal_to_dict(j) for j in s.journal],
    }


def _student_from_dict(d: dict, trait_pool: list[Trait]) -> Student:
    """Reconstruct a Student from a dict. Traits are matched by name from the trait pool."""
    # Build trait lookup
    trait_by_name = {t.name: t for t in trait_pool}

    # Reconstruct needs
    needs = {}
    for nt_str, need_data in d.get("needs", {}).items():
        needs[NeedType(nt_str)] = _need_from_dict(need_data)

    # Reconstruct skills
    skills = {}
    for sk_str, val in d.get("skills", {}).items():
        skills[Skill(sk_str)] = val

    # Reconstruct grades
    grades = {}
    for subj_str, grade_data in d.get("grades", {}).items():
        grades[Subject(subj_str)] = _grade_from_dict(grade_data)

    # Reconstruct traits from names
    traits = [trait_by_name[name] for name in d.get("traits", []) if name in trait_by_name]

    student = Student(
        name=d["name"],
        student_id=d["student_id"],
        gender=Gender(d["gender"]),
        year=Year(d["year"]),
        personality=_personality_from_dict(d["personality"]) if d.get("personality") else None,
        appearance=_appearance_from_dict(d["appearance"]) if d.get("appearance") else None,
        needs=needs,
        skills=skills,
        traits=traits,
        state=StudentState(d.get("state", "idle")),
        activity_ticks_left=d.get("activity_ticks_left", 0),
        travel_ticks_left=d.get("travel_ticks_left", 0),
        chat_partner_id=d.get("chat_partner_id"),
        grades=grades,
        thoughts=[_thought_from_dict(t) for t in d.get("thoughts", [])],
        journal=[_journal_from_dict(j) for j in d.get("journal", [])],
    )
    return student


# ── Friendship / Romance ────────────────────────────────────────────


def _friendship_to_dict(f: Friendship) -> dict:
    return {
        "student_id1": f.student_id1,
        "student_id2": f.student_id2,
        "level": f.level.value,
        "affinity": f.affinity,
        "history": f.history,
    }


def _friendship_from_dict(d: dict) -> Friendship:
    return Friendship(
        student_id1=d["student_id1"],
        student_id2=d["student_id2"],
        level=FriendshipLevel(d["level"]),
        affinity=d["affinity"],
        history=d.get("history", []),
    )


def _romance_to_dict(r: Romance) -> dict:
    return {
        "student_id1": r.student_id1,
        "student_id2": r.student_id2,
        "feelings_1": r.feelings_1.value,
        "feelings_2": r.feelings_2.value,
        "affinity_1": r.affinity_1,
        "affinity_2": r.affinity_2,
        "history": r.history,
    }


def _romance_from_dict(d: dict) -> Romance:
    return Romance(
        student_id1=d["student_id1"],
        student_id2=d["student_id2"],
        feelings_1=RomanceLevel(d["feelings_1"]),
        feelings_2=RomanceLevel(d["feelings_2"]),
        affinity_1=d["affinity_1"],
        affinity_2=d["affinity_2"],
        history=d.get("history", []),
    )


# ── Full GameState ──────────────────────────────────────────────────


def state_to_dict(state: "GameState") -> dict:
    """Serialize a GameState to a JSON-compatible dict."""
    return {
        "version": 1,  # save format version for future migration
        "clock": {
            "day": state.clock.day,
            "tick": state.clock.tick,
            "ticks_per_day": state.clock.ticks_per_day,
        },
        "total_points": state.total_points,
        "graduation_target": state.graduation_target,
        "current_weather": state.current_weather.value,
        "students": [_student_to_dict(s) for s in state.students],
        "friendships": [_friendship_to_dict(f) for f in state.friendships.values()],
        "romances": [_romance_to_dict(r) for r in state.romances.values()],
    }


def state_from_dict(data: dict) -> "GameState":
    """Reconstruct a GameState from a saved dict.

    Rooms, traits, and scenario config are reloaded from data files.
    Students, friendships, romances, and all their nested data are
    fully restored from the save.
    """
    from .engine import GameState
    from .defs import GameDefs
    from .game_events import GameEventBus
    from .journal import JournalSubscriber

    # Load game definitions (rooms, traits, scenario) from data files
    defs = GameDefs.load()

    # Build trait pool for student deserialization
    trait_pool = defs.traits if defs.traits else []

    # Reconstruct students
    students = [_student_from_dict(sd, trait_pool) for sd in data.get("students", [])]

    # Reconstruct clock
    clock_data = data.get("clock", {})
    clock = GameClock(
        day=clock_data.get("day", 1),
        tick=clock_data.get("tick", 0),
        ticks_per_day=clock_data.get("ticks_per_day", 84),
    )

    # Reconstruct friendships (keyed by canonical pair)
    friendships: dict[tuple[int, int], Friendship] = {}
    for fd in data.get("friendships", []):
        f = _friendship_from_dict(fd)
        friendships[f.pair] = f

    # Reconstruct romances (keyed by canonical pair)
    romances: dict[tuple[int, int], Romance] = {}
    for rd in data.get("romances", []):
        r = _romance_from_dict(rd)
        romances[r.pair] = r

    # Build the state
    state = GameState(
        clock=clock,
        total_points=data.get("total_points", 0),
        graduation_target=data.get("graduation_target", 800),
        students=students,
        rooms=defs.rooms if defs.rooms else [],
        friendships=friendships,
        romances=romances,
        scenario=defs.scenario,
        current_weather=Weather(data.get("current_weather", "sunny")),
    )

    # Wire the EventBus and JournalSubscriber (same as new_game does)
    journal_sub = JournalSubscriber(state)
    journal_sub.subscribe(state.bus)
    state._journal_sub = journal_sub

    # Reload social text if available
    if defs.social_text:
        from . import social as social_module
        social_module.load_text_from_defs(defs.social_text)

    # Students start with location = None (they'll be dispatched on next tick)
    for s in students:
        s.location = None
        s.destination = None

    return state


# ── Public API ──────────────────────────────────────────────────────


def save_game(state: "GameState", path: str | Path) -> None:
    """Save the full game state to a JSON file."""
    data = state_to_dict(state)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_game(path: str | Path) -> "GameState":
    """Load a full game state from a JSON file."""
    data = json.loads(Path(path).read_text())
    return state_from_dict(data)
