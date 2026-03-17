"""Data definitions loader -- loads game content from JSON files.

This module bridges JSON data files (src/data/) and the sim's Python objects.
The engine calls GameDefs.load() at startup to get rooms, events, social text,
and class definitions. If JSON files are missing, falls back to hardcoded defaults.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .events import SchoolEvent
from .models import Room, Skill
from .traits import Trait, load_traits_from_json


# Default data directory (relative to this file)
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_json(path: Path) -> dict | list:
    """Load and parse a JSON file."""
    with open(path) as f:
        return json.load(f)


def _skill_from_str(s: str) -> Skill:
    """Convert a string like 'academics' to a Skill enum."""
    return Skill(s)


def _load_rooms(path: Path) -> list[Room]:
    """Load rooms from a JSON file."""
    data = _load_json(path)
    rooms = []
    for entry in data:
        rooms.append(
            Room(
                name=entry["name"],
                skill_boost=_skill_from_str(entry["skill_boost"]),
                boost_per_tick=entry.get("boost_per_tick", 1.5),
                needs_satisfied=entry.get("needs_satisfied", {}),
                capacity=entry.get("capacity", 8),
                description=entry.get("description", ""),
                position=tuple(entry.get("position", [0, 0])),
                sit_prefixes=entry.get("sit_prefixes", []),
            )
        )
    return rooms


def _load_events(path: Path) -> list[SchoolEvent]:
    """Load school events from a JSON file."""
    data = _load_json(path)
    events = []
    for entry in data:
        events.append(
            SchoolEvent(
                name=entry["name"],
                required_skill=_skill_from_str(entry["required_skill"]),
                skill_threshold=entry.get("skill_threshold", 30),
                point_reward=entry.get("point_reward", 50),
                point_penalty=entry.get("point_penalty", -10),
                description=entry.get("description", ""),
            )
        )
    return events


@dataclass
class ScenarioConfig:
    """Settings loaded from a scenario JSON file."""

    name: str = "High School"
    description: str = ""
    num_students: int = 8
    graduation_target: int = 800
    ticks_per_day: int = 48
    lunch_start_tick: int = 24   # 12:00 PM (4 hours after 8 AM)
    lunch_end_tick: int = 29     # 12:50 PM
    report_card_interval: int = 7
    starting_room: str = "Cafeteria"
    student_names: list[str] = field(default_factory=list)

    # Overnight recovery ranges
    rest_recovery: tuple[float, float] = (35.0, 55.0)
    fun_recovery: tuple[float, float] = (10.0, 20.0)
    social_recovery: tuple[float, float] = (8.0, 15.0)
    minor_recovery: tuple[float, float] = (3.0, 8.0)

    # File references (relative to data_dir)
    rooms_file: str = "rooms.json"
    events_file: str = "events.json"
    traits_file: str = "traits.json"
    classes_file: str = "classes.json"
    social_text_file: str = "social_text.json"


def _load_scenario(path: Path) -> ScenarioConfig:
    """Load a scenario config from a JSON file."""
    data = _load_json(path)
    day_reset = data.get("day_reset", {})

    return ScenarioConfig(
        name=data.get("name", "High School"),
        description=data.get("description", ""),
        num_students=data.get("num_students", 8),
        graduation_target=data.get("graduation_target", 800),
        ticks_per_day=data.get("ticks_per_day", 48),
        lunch_start_tick=data.get("lunch_start_tick", 24),
        lunch_end_tick=data.get("lunch_end_tick", 29),
        report_card_interval=data.get("report_card_interval", 7),
        starting_room=data.get("starting_room", "Cafeteria"),
        student_names=data.get("student_names", []),
        rest_recovery=tuple(day_reset.get("rest_recovery", [35, 55])),
        fun_recovery=tuple(day_reset.get("fun_recovery", [10, 20])),
        social_recovery=tuple(day_reset.get("social_recovery", [8, 15])),
        minor_recovery=tuple(day_reset.get("minor_recovery", [3, 8])),
        rooms_file=data.get("rooms_file", "rooms.json"),
        events_file=data.get("events_file", "events.json"),
        traits_file=data.get("traits_file", "traits.json"),
        classes_file=data.get("classes_file", "classes.json"),
        social_text_file=data.get("social_text_file", "social_text.json"),
    )


@dataclass
class GameDefs:
    """All loaded game definitions -- content that drives the simulation."""

    rooms: list[Room] = field(default_factory=list)
    events: list[SchoolEvent] = field(default_factory=list)
    social_text: dict = field(default_factory=dict)
    classes: list[dict] = field(default_factory=list)
    traits: list[Trait] = field(default_factory=list)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)

    @classmethod
    def load(
        cls,
        data_dir: Path | None = None,
        scenario_path: Path | None = None,
    ) -> "GameDefs":
        """Load all definition files from a directory.

        If scenario_path is provided, loads the scenario config first and uses
        its file references. Falls back gracefully if files are missing.
        """
        data_dir = data_dir or DEFAULT_DATA_DIR

        # Load scenario config (if provided)
        scenario = ScenarioConfig()
        if scenario_path and scenario_path.exists():
            scenario = _load_scenario(scenario_path)

        rooms: list[Room] = []
        events: list[SchoolEvent] = []
        social_text: dict = {}
        classes: list[dict] = []

        # Rooms (using scenario's file reference)
        rooms_path = data_dir / scenario.rooms_file
        if rooms_path.exists():
            rooms = _load_rooms(rooms_path)

        # Events
        events_path = data_dir / scenario.events_file
        if events_path.exists():
            events = _load_events(events_path)

        # Social text
        social_path = data_dir / scenario.social_text_file
        if social_path.exists():
            social_text = _load_json(social_path)

        # Classes
        classes_path = data_dir / scenario.classes_file
        if classes_path.exists():
            classes = _load_json(classes_path)

        # Traits
        traits: list[Trait] = []
        traits_path = data_dir / scenario.traits_file
        if traits_path.exists():
            traits = load_traits_from_json(_load_json(traits_path))

        return cls(
            rooms=rooms,
            events=events,
            social_text=social_text,
            classes=classes,
            traits=traits,
            scenario=scenario,
        )
