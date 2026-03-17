"""Game engine. This owns the GameState and runs the ticker loop.

Engine calls behaviors.process_student() for each student, each tick, checks for
social interactions, triggers events, manages day cycle.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from .academics import (
    Subject,
    calculate_report_card_points,
    create_default_grades,
    tick_all_grades,
)
from .behaviors import process_student, send_to_room
from .clock import TICKS_PER_DAY, GameClock
from .defs import GameDefs, ScenarioConfig
from .events import SchoolEvent, check_for_event, resolve_event
from .journal import generate_journal_entry
from .models import (
    Friendship,
    FriendshipLevel,
    Mood,
    Romance,
    RomanceLevel,
    Room,
    Skill,
    Student,
    StudentState,
    Year,
)
from .personality import Personality
from .needs import NeedType, satisfy_need
from .social import get_or_create_friendship, get_or_create_romance, maybe_interact, maybe_romance
from .thoughts import (
    add_thought,
    thought_exhausted,
    thought_failing_subject,
    thought_grades_improving,
    thought_great_report_card,
    thought_slept_well,
)


REPORT_CARD_INTERVAL: int = 7  # days between report cards


@dataclass
class GameState:
    """The complete state of a Pixel Campus playthrough."""

    clock: GameClock = field(default_factory=GameClock)
    total_points: int = 0
    graduation_target: int = 800
    paused: bool = False

    students: list[Student] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    friendships: dict[tuple[int, int], Friendship] = field(default_factory=dict)
    romances: dict[tuple[int, int], Romance] = field(default_factory=dict)

    # Scenario configuration (drives game parameters)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)

    # Messages generated this tick
    tick_log: list[str] = field(default_factory=list)

    @classmethod
    def new_game(
        cls,
        num_students: int | None = None,
        data_dir: Path | None = None,
        scenario_path: Path | None = None,
    ) -> "GameState":
        """Create a fresh game.

        Loads scenario config and data definitions from JSON.
        Falls back to hardcoded defaults if files are missing.

        Args:
            num_students: Override the scenario's student count.
            data_dir: Override the data directory.
            scenario_path: Path to a scenario JSON file. If None, uses
                the default high_school.json if it exists.
        """
        # Try default scenario path if none provided
        effective_data_dir = data_dir or (
            Path(__file__).resolve().parent.parent / "data"
        )
        if scenario_path is None:
            default_scenario = effective_data_dir / "scenarios" / "high_school.json"
            if default_scenario.exists():
                scenario_path = default_scenario

        # Load data definitions (including scenario config)
        defs = GameDefs.load(data_dir, scenario_path=scenario_path)
        scenario = defs.scenario

        if not defs.rooms:
            raise ValueError("No rooms loaded — check that rooms.json exists in the data directory.")
        rooms = defs.rooms

        # Use loaded events or fall back to hardcoded defaults
        if defs.events:
            from . import events as events_module
            events_module.EVENTS = defs.events

        # Student count: explicit param > scenario > default 8
        actual_num_students = num_students or scenario.num_students

        # Load name pools: scenario override > shared names.json > empty
        if scenario.student_names:
            # Legacy flat list: treat all as unisex
            _names_data = {"male": [], "female": [], "unisex": scenario.student_names}
        else:
            names_file = effective_data_dir / "names.json"
            if names_file.exists():
                import json as _json
                _names_data = _json.loads(names_file.read_text())
            else:
                _names_data = {}

        _male_pool   = _names_data.get("male", []) + _names_data.get("unisex", [])
        _female_pool = _names_data.get("female", []) + _names_data.get("unisex", [])
        _nb_pool     = _names_data.get("male", []) + _names_data.get("female", []) + _names_data.get("unisex", [])

        from .models import Gender as _Gender
        _genders = [random.choice(list(_Gender)) for _ in range(actual_num_students)]
        _used: set[str] = set()
        names: list[str] = []
        for g in _genders:
            pool = (
                _male_pool   if g == _Gender.MALE   else
                _female_pool if g == _Gender.FEMALE else
                _nb_pool
            )
            available = [n for n in pool if n not in _used]
            if available:
                name = random.choice(available)
                _used.add(name)
                names.append(name)
            else:
                names.append(f"Student {len(names) + 1}")

        # Build the trait pool for random assignment
        available_traits = defs.traits if defs.traits else []

        students = []
        for i, (name, gender) in enumerate(zip(names, _genders)):
            student = Student(
                name=name,
                student_id=i,
                gender=gender,
                year=random.choice(list(Year)),
                personality=Personality.random(),
            )

            # Assign 1-2 random traits (if available)
            if available_traits:
                num_traits = random.choice([1, 1, 2])  # 2/3 chance of 1, 1/3 of 2
                student.traits = random.sample(
                    available_traits, min(num_traits, len(available_traits))
                )

            # Initialize grades (using class defs baseline if available)
            student.grades = create_default_grades()
            if defs.classes:
                for class_def in defs.classes:
                    try:
                        subj = Subject(class_def["subject"])
                        if subj in student.grades:
                            baseline = class_def.get("baseline", 72)
                            student.grades[subj].value = float(baseline)
                            student.grades[subj].baseline = float(baseline)
                    except (ValueError, KeyError):
                        pass

            # Apply trait grade baseline modifiers
            if student.traits:
                from .traits import combined_grade_baseline_offset
                for subj, grade in student.grades.items():
                    offset = combined_grade_baseline_offset(student.traits, subj.value)
                    if offset:
                        grade.baseline += offset
                        grade.value += offset
                        grade.clamp()

            # Start with decent rest and fun (just woke up, new school!)
            student.needs[NeedType.REST].value = 80.0
            student.needs[NeedType.FUN].value = 60.0
            student.needs[NeedType.SOCIAL].value = 50.0
            students.append(student)

        # Create the game state with scenario config
        clock = GameClock(ticks_per_day=scenario.ticks_per_day)
        state = cls(
            students=students,
            rooms=rooms,
            clock=clock,
            graduation_target=scenario.graduation_target,
            scenario=scenario,
        )

        # Store loaded social text for use by social.py
        if defs.social_text:
            from . import social as social_module
            social_module.load_text_from_defs(defs.social_text)

        # Students start at the spawn point (location = None) so all dispatches fire
        for s in students:
            s.location = None

        return state

    def tick(self) -> list[str]:
        """Advance the simulation by 1 tick. Returns log messages."""
        if self.paused:
            return []

        self.tick_log = []

        # Process each student's behavior
        for student in self.students:
            messages = process_student(student, self)
            self.tick_log.extend(messages)

            # Tick grades (drift + decay)
            tick_all_grades(student.grades)

        # Check for spontaneous social interactions
        self._process_social_encounters()

        # Check for scheduled events
        event = check_for_event(self)
        if event:
            event_messages = resolve_event(self, event)
            self.tick_log.extend(event_messages)

        # Advance clock
        day_ended = self.clock.advance()

        if day_ended:
            self.tick_log.extend(self._end_of_day())

        return self.tick_log

    def run_until_day_end(self) -> list[str]:
        """Run ticks until the current day ends."""
        all_logs: list[str] = []
        starting_day = self.clock.day
        while self.clock.day == starting_day:
            all_logs.extend(self.tick())
        return all_logs

    # --------------
    # PLAYER ACTIONS
    # --------------

    def assign_student(self, student: Student, room: Room) -> str:
        """Player action: sends a student to a room."""
        occupants = [
            s
            for s in self.students
            if s.location == room and s.state != StudentState.TRAVELING
        ]
        if len(occupants) >= room.capacity:
            return f"{room.name} is full!"
        return send_to_room(student, room)

    def free_student(self, student: Student) -> str:
        """Player action: remove a student from their current activity."""
        old_state = student.state
        student.state = StudentState.IDLE
        student.destination = None
        student.travel_ticks_left = 0
        student.activity_ticks_left = 0

        if student.chat_partner_id is not None:
            partner = self.get_student_by_id(student.chat_partner_id)
            if partner:
                partner.state = StudentState.IDLE
                partner.chat_partner_id = None
                partner.activity_ticks_left = 0
            student.chat_partner_id = None

        if old_state == StudentState.IDLE:
            return f"{student.name} is already free."

        return f"{student.name} stops {old_state.value} and is now free."

    # ------
    # SOCIAL
    # ------

    def _process_social_encounters(self) -> None:
        """Students in the same room who are idle or doing activities might chat."""
        for room in self.rooms:
            present = [
                s
                for s in self.students
                if s.location == room
                and s.state not in (StudentState.TRAVELING, StudentState.CHATTING)
            ]
            if len(present) < 2:
                continue
            for i, a in enumerate(present):
                for b in present[i + 1 :]:
                    a_social = a.state == StudentState.SOCIALIZING
                    b_social = b.state == StudentState.SOCIALIZING
                    if a_social and b_social:
                        chance = 0.5   # both actively want to socialize
                    elif a_social or b_social:
                        chance = 0.20  # one is seeking, one is available
                    else:
                        chance = 0.03  # background spontaneous chance
                    if random.random() < chance:
                        self._start_chat(a, b, room)

    def _start_chat(self, a: Student, b: Student, room: Room) -> None:
        """Make two students start to chat."""
        a_available = a.state in (StudentState.IDLE, StudentState.SOCIALIZING)
        b_available = b.state in (StudentState.IDLE, StudentState.SOCIALIZING)
        if not (a_available and b_available):
            if random.random() > 0.15:
                return

        rel = get_or_create_friendship(self.friendships, a, b)
        text = maybe_interact(a, b, rel)

        # Romance tick: runs alongside friendship, weighted by compatibility
        romance_rel = get_or_create_romance(self.romances, a, b)
        location_boost = 1.5 if room.name == "Quad" else 1.0
        romance_text = maybe_romance(a, b, romance_rel, friendship=rel, location_boost=location_boost)
        if romance_text:
            self.tick_log.append(romance_text)

        for person in [a, b]:
            person.state = StudentState.CHATTING
            duration = random.randint(2, 5)
            person.activity_ticks_left = duration
        a.chat_partner_id = b.student_id
        b.chat_partner_id = a.student_id

        if text:
            self.tick_log.append(text)

    # -----------
    # ENDING DAY
    # -----------

    def _end_of_day(self) -> list[str]:
        """Process end-of-day: tally points, report cards, generate journals, reset."""
        log: list[str] = []
        log.append(f"Day {self.clock.day} is over!")

        day_points = self._calculate_day_points()
        self.total_points += day_points
        log.append(
            f"Day earned {day_points} points. "
            f"Total: {self.total_points}/{self.graduation_target}"
        )

        # Report card every N days (from scenario config)
        interval = self.scenario.report_card_interval
        if self.clock.day > 1 and self.clock.day % interval == 0:
            log.extend(self._report_card())

        # Journal entries
        for student in self.students:
            if random.random() < 0.4:
                entry = generate_journal_entry(student, self.clock.day)
                student.journal.append((self.clock.day, entry))
                log.append(f"{student.name} wrote in their journal")

        if self.total_points >= self.graduation_target:
            log.append("GRADUATION!! Your students made it!")

        # Reset for new day
        for student in self.students:
            # Sleep quality thoughts (before we reset needs)
            if student.needs[NeedType.REST].value > 70:
                add_thought(student.thoughts, thought_slept_well())
            elif student.needs[NeedType.REST].value < 20:
                add_thought(student.thoughts, thought_exhausted())

            student.state = StudentState.IDLE
            student.destination = None
            student.travel_ticks_left = 0
            student.activity_ticks_left = 0
            student.chat_partner_id = None

            # Overnight recovery (amounts from scenario config)
            sc = self.scenario
            satisfy_need(student.needs, NeedType.REST, random.uniform(*sc.rest_recovery))
            satisfy_need(student.needs, NeedType.FUN, random.uniform(*sc.fun_recovery))
            satisfy_need(student.needs, NeedType.SOCIAL, random.uniform(*sc.social_recovery))
            satisfy_need(student.needs, NeedType.ACADEMICS, random.uniform(*sc.minor_recovery))
            satisfy_need(student.needs, NeedType.CREATIVITY, random.uniform(*sc.minor_recovery))
            satisfy_need(student.needs, NeedType.ATHLETICS, random.uniform(*sc.minor_recovery))

        # Move to next day
        self.clock.new_day()

        # Students start at the spawn point (no room yet) so all dispatches fire properly
        for s in self.students:
            s.location = None

        log.append(f"Day {self.clock.day} begins! ({self.clock.time_str})")
        return log

    def _report_card(self) -> list[str]:
        """Issue report cards for all students. Returns log messages."""
        log: list[str] = []
        log.append("REPORT CARDS are in!")

        for student in self.students:
            points = calculate_report_card_points(student.grades)
            self.total_points += points

            # Build grade summary
            grades_str = ", ".join(
                f"{subj.value.capitalize()}: {student.grades[subj].letter}"
                for subj in Subject
                if subj in student.grades
            )
            sign = "+" if points >= 0 else ""
            log.append(f"  {student.name}: {grades_str} ({sign}{points} pts)")

            # Generate thoughts from grades
            all_good = True
            has_failing = False
            for subj, grade in student.grades.items():
                if grade.letter == "F":
                    has_failing = True
                    all_good = False
                    add_thought(
                        student.thoughts,
                        thought_failing_subject(subj.value.capitalize()),
                    )
                elif grade.letter not in ("A", "B"):
                    all_good = False

            if all_good and student.grades:
                add_thought(student.thoughts, thought_great_report_card())

            # Check for improvement (compare effective grade to baseline)
            improving = any(
                grade.effective > grade.baseline + 5
                for grade in student.grades.values()
            )
            if improving and not has_failing:
                add_thought(student.thoughts, thought_grades_improving())

        return log

    def _calculate_day_points(self) -> int:
        """Daily points from average mood and skill growth."""
        if not self.students:
            return 0
        n = len(self.students)
        avg_mood = sum(s.mood_value for s in self.students) / n
        avg_skill = sum(
            sum(s.skills.values()) / len(s.skills) for s in self.students
        ) / n
        return int(avg_mood / 10 + avg_skill / 5)

    # ----------------
    # LOOKUP FUNCTIONS
    # ----------------

    def get_student_by_name(self, name: str) -> Student | None:
        name_lower = name.lower()
        for s in self.students:
            if s.name.lower() == name_lower:
                return s
        return None

    def get_student_by_id(self, student_id: int | None) -> Student | None:
        for s in self.students:
            if s.student_id == student_id:
                return s
        return None

    def get_room_by_name(self, name: str) -> Room | None:
        name_lower = name.lower()
        for r in self.rooms:
            if r.name.lower() == name_lower:
                return r
        return None

    # ------------------
    # PERSIST GAME STATE
    # ------------------

    def save(self, path: str | Path) -> None:
        # TODO: expand stub
        data = {
            "day": self.clock.day,
            "tick": self.clock.tick,
            "total_points": self.total_points,
            "num_students": len(self.students),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "GameState":
        # TODO: expand stub
        data = json.loads(Path(path).read_text())
        state = cls.new_game(num_students=data.get("num_students", 8))
        state.clock.day = data.get("day", 1)
        state.clock.tick = data.get("tick", 0)
        state.total_points = data.get("total_points", 0)
        return state
