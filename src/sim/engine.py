"""Game engine. This owns the GameState and runs the ticker loop.

Engine calls behaviors.process_student() for each student, each tick, checks for
social interactions, triggers events, manages day cycle.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .academics import (
    Subject,
    calculate_report_card_points,
    create_default_grades,
    tick_all_grades,
)
from .behaviors import _autonomous_decision, process_student, send_to_room
from .clock import TICKS_PER_DAY, GameClock
from .defs import GameDefs, ScenarioConfig
from .events import SchoolEvent, check_for_event, resolve_event
from .game_events import GameEvent, GameEventBus, GameEventType
from .journal import (
    JournalSubscriber,
    generate_boring_day_entry,
    generate_journal_entry,
    generate_prospective_entry,
)
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
from .personality import Personality, TimeOfDay, Weather
from .needs import NeedType, satisfy_need
from .social import get_or_create_friendship, get_or_create_romance, maybe_interact, maybe_romance
from .thoughts import (
    add_thought,
    thought_charmed_by,
    thought_exhausted,
    thought_jealous,
    thought_failing_subject,
    thought_grades_improving,
    thought_great_report_card,
    thought_great_sleep,
    thought_lunch_social,
    thought_morning_person_boost,
    thought_not_a_morning_person,
    thought_slept_well,
    thought_snow_day,
    thought_sunny_day,
    thought_terrible_sleep,
    thought_weather_match,
    thought_weather_mismatch,
    thought_weather_storm,
)
from .traits import has_trait


REPORT_CARD_INTERVAL: int = 7  # days between report cards

# Sleep quality tiers: (label, weight, rest_range, thought_factory_or_None)
# Weight is relative — Anxious trait shifts toward worse tiers.
_SLEEP_TIERS = [
    ("terrible", 10, (4,  12), thought_terrible_sleep),
    ("poor",     20, (12, 20), thought_exhausted),
    ("okay",     35, (20, 28), None),
    ("good",     25, (28, 38), thought_slept_well),
    ("great",    10, (38, 48), thought_great_sleep),
]


def _roll_sleep_quality(
    sc: "ScenarioConfig", traits: list
) -> tuple[float, "Thought | None"]:
    """Roll overnight sleep quality for one student. Returns (rest_gain, thought_or_None).

    Anxious trait shifts the distribution toward poor/terrible.
    Overachiever also sleeps slightly worse (mind won't stop).
    """
    from .traits import has_trait
    weights = [t[1] for t in _SLEEP_TIERS]

    if has_trait(traits, "Anxious"):
        # Shift 12 weight from good/great into poor/terrible
        weights = [w + 6 if i < 2 else w - 6 if i >= 3 else w
                   for i, w in enumerate(weights)]
    if has_trait(traits, "Overachiever"):
        weights = [w + 4 if i < 2 else w - 4 if i >= 3 else w
                   for i, w in enumerate(weights)]

    weights = [max(1, w) for w in weights]  # no negative weights
    tier = random.choices(_SLEEP_TIERS, weights=weights, k=1)[0]
    rest_gain = random.uniform(*tier[2])
    thought = tier[3]() if tier[3] is not None else None
    return rest_gain, thought


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

    # Event bus — reactive systems subscribe here at startup
    bus: GameEventBus = field(default_factory=GameEventBus)

    # Today's weather — rolled fresh each day
    current_weather: Weather = field(default_factory=lambda: random.choice(list(Weather)))

    # Messages generated this tick
    tick_log: list[str] = field(default_factory=list)

    # Journal subscriber — set by new_game(), used for tick checks & activity hooks
    _journal_sub: Any = field(default=None, repr=False)

    # Lunch tracking — reset each new day
    _lunch_dispatched: bool = False

    @property
    def is_lunch_period(self) -> bool:
        """True during the scheduled lunch window."""
        return self.scenario.lunch_start_tick <= self.clock.tick < self.scenario.lunch_end_tick

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

            # Assign 1-2 random traits (if available), respecting mutual exclusions
            if available_traits:
                num_traits = random.choice([1, 1, 2])  # 2/3 chance of 1, 1/3 of 2
                first = random.choice(available_traits)
                student.traits = [first]
                if num_traits == 2:
                    excluded = set(first.excludes) | {
                        t.name for t in available_traits if first.name in t.excludes
                    }
                    compatible = [t for t in available_traits if t.name != first.name and t.name not in excluded]
                    if compatible:
                        student.traits.append(random.choice(compatible))

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

        # Wire journal EventBus subscriber
        journal_sub = JournalSubscriber(state)
        journal_sub.subscribe(state.bus)
        state._journal_sub = journal_sub

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

        # Lunch bell — dispatch everyone to cafeteria once at the start of lunch
        if self.clock.tick == self.scenario.lunch_start_tick and not self._lunch_dispatched:
            self.tick_log.extend(self._start_lunch_period())

        # Post-lunch bell — nudge all idle students to find their next activity
        if self.clock.tick == self.scenario.lunch_end_tick:
            self.tick_log.extend(self._end_lunch_period())

        # Check for spontaneous social interactions
        self._process_social_encounters()

        # Check for scheduled events
        event = check_for_event(self)
        if event:
            event_messages = resolve_event(self, event)
            self.tick_log.extend(event_messages)

        # Journal tick checks (mood threshold, loneliness, new room)
        if self._journal_sub is not None:
            self._journal_sub.tick_check()

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

    def _start_lunch_period(self) -> list[str]:
        """Send every student to the cafeteria for lunch."""
        self._lunch_dispatched = True
        cafeteria = self.get_room_by_name("Cafeteria")
        if cafeteria is None:
            return []
        log: list[str] = ["** Lunch bell! Everyone heads to the Cafeteria. **"]
        for student in self.students:
            if student.location != cafeteria:
                send_to_room(student, cafeteria)
        return log

    def _end_lunch_period(self) -> list[str]:
        """Force idle students out of the cafeteria to their next activity."""
        cafeteria = self.get_room_by_name("Cafeteria")
        nudged = 0
        for student in self.students:
            if student.state in (StudentState.IDLE, StudentState.SOCIALIZING):
                # Give a small mood boost to students who made it to lunch
                if student.location == cafeteria and random.random() < 0.7:
                    add_thought(student.thoughts, thought_lunch_social())
                _autonomous_decision(student, self)
                nudged += 1
        return [f"** Lunch over! {nudged} students head back to their afternoon. **"] if nudged else []

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
        text = maybe_interact(a, b, rel, bus=self.bus)

        # Romance tick: runs alongside friendship, weighted by compatibility
        romance_rel = get_or_create_romance(self.romances, a, b)
        location_boost = 1.5 if room.name == "Quad" else 1.0
        romance_text = maybe_romance(a, b, romance_rel, friendship=rel, location_boost=location_boost, bus=self.bus)
        if romance_text:
            self.tick_log.append(romance_text)

        # Flirt + Attractive interaction: Flirt gets a special charmed thought
        for flirt, other in ((a, b), (b, a)):
            if has_trait(flirt, "Flirt") and has_trait(other, "Attractive"):
                add_thought(flirt.thoughts, thought_charmed_by(other.name))

        for person in [a, b]:
            person.state = StudentState.CHATTING
            duration = random.randint(2, 5)
            person.activity_ticks_left = duration
        a.chat_partner_id = b.student_id
        b.chat_partner_id = a.student_id

        if text:
            self.tick_log.append(text)

        # Jealousy: other students who have a crush on A or B may feel a pang.
        self._trigger_jealousy(a, b, room)

    def _trigger_jealousy(self, a: Student, b: Student, room: Room) -> None:
        """Fire jealousy thoughts for bystanders who have a crush on A or B.

        Global trigger — C doesn't need to witness the chat. Being in the same
        room raises the chance (90%) vs. hearing about it later (25%).
        Only fires if the chat partner is a gender C is attracted to.
        """
        from .models import Gender
        from .personality import RomanceInterest

        _GENDER_MAP = {
            RomanceInterest.BOYS:       Gender.MALE,
            RomanceInterest.GIRLS:      Gender.FEMALE,
            RomanceInterest.NON_BINARY: Gender.NON_BINARY,
        }

        def _attracted_to(c: Student, target: Student) -> bool:
            if c.personality is None:
                return True
            return any(
                _GENDER_MAP.get(ri) == target.gender
                for ri in c.personality.romance_interest
            )

        for c in self.students:
            if c.student_id in (a.student_id, b.student_id):
                continue
            for crush, interloper in ((a, b), (b, a)):
                key = (min(c.student_id, crush.student_id), max(c.student_id, crush.student_id))
                romance = self.romances.get(key)
                if romance is None:
                    continue
                if romance.feelings_of(c.student_id) < RomanceLevel.CRUSH:
                    continue
                if not _attracted_to(c, interloper):
                    continue
                prob = 0.90 if (c.location is not None and c.location == room) else 0.25
                if random.random() < prob:
                    add_thought(c.thoughts, thought_jealous(crush.name, interloper.name), bus=self.bus)
                    # Journal: jealousy entry
                    from .journal import generate_event_entry as _gen_event
                    j_entry = _gen_event(c, self.clock.day, self.clock.tick,
                                         "jealous", crush=crush.name, other=interloper.name)
                    if j_entry:
                        c.journal.append(j_entry)
                break  # fire at most once per chat (first crush found wins)

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
            if self._journal_sub is not None:
                self._journal_sub.on_report_card()

        # Journal entries (end-of-day retrospective + guaranteed minimum)
        for student in self.students:
            today_count = sum(1 for e in student.journal if e.day == self.clock.day)

            if random.random() < 0.70:
                entry = generate_journal_entry(student, self.clock.day, self.clock.tick)
                student.journal.append(entry)
                log.append(f"{student.name} wrote in their journal")
                today_count += 1

            # Guaranteed minimum: if nothing was journaled all day, write a boring-day entry
            if today_count == 0:
                entry = generate_boring_day_entry(student, self.clock.day, self.clock.tick)
                student.journal.append(entry)
                log.append(f"{student.name} wrote in their journal (quiet day)")

        if self.total_points >= self.graduation_target:
            log.append("GRADUATION!! Your students made it!")

        self.bus.emit(GameEvent(
            GameEventType.DAY_ENDED,
            data={"day": self.clock.day, "points": day_points},
        ))

        # Roll tomorrow's weather and log it
        self.current_weather = random.choice(list(Weather))
        log.append(f"Tomorrow: {self.current_weather.value}.")

        # Reset for new day
        sc = self.scenario
        for student in self.students:
            student.state = StudentState.IDLE
            student.destination = None
            student.travel_ticks_left = 0
            student.activity_ticks_left = 0
            student.chat_partner_id = None

            tr = student.traits

            # --- Sleep quality (replaces flat REST recovery) ---
            rest_gain, sleep_thought = _roll_sleep_quality(sc, tr)
            satisfy_need(student.needs, NeedType.REST, rest_gain, traits=tr)
            if sleep_thought is not None:
                add_thought(student.thoughts, sleep_thought, bus=self.bus)

            # Overnight recovery for other needs
            satisfy_need(student.needs, NeedType.FUN,        random.uniform(*sc.fun_recovery),    traits=tr)
            satisfy_need(student.needs, NeedType.SOCIAL,     random.uniform(*sc.social_recovery), traits=tr)
            satisfy_need(student.needs, NeedType.ACADEMICS,  random.uniform(*sc.minor_recovery),  traits=tr)
            satisfy_need(student.needs, NeedType.CREATIVITY, random.uniform(*sc.minor_recovery),  traits=tr)
            satisfy_need(student.needs, NeedType.ATHLETICS,  random.uniform(*sc.minor_recovery),  traits=tr)

            # --- Weather thoughts ---
            p = student.personality
            if p:
                if p.weather == self.current_weather:
                    add_thought(student.thoughts, thought_weather_match(self.current_weather.value), bus=self.bus)
                elif self.current_weather == Weather.STORM:
                    add_thought(student.thoughts, thought_weather_storm(), bus=self.bus)
                elif self.current_weather == Weather.RAIN:
                    add_thought(student.thoughts, thought_weather_mismatch("rainy"), bus=self.bus)

            # Ambient weather bonus (sunny/snow feel good for everyone)
            if self.current_weather == Weather.SUNNY:
                add_thought(student.thoughts, thought_sunny_day(), bus=self.bus)
            elif self.current_weather == Weather.SNOW:
                add_thought(student.thoughts, thought_snow_day(), bus=self.bus)

            # --- Time-of-day nudge ---
            if p:
                if p.time_of_day == TimeOfDay.MORNING:
                    add_thought(student.thoughts, thought_morning_person_boost(), bus=self.bus)
                elif p.time_of_day in (TimeOfDay.EVENING, TimeOfDay.NIGHT):
                    add_thought(student.thoughts, thought_not_a_morning_person(), bus=self.bus)

        # Move to next day
        self._lunch_dispatched = False
        if self._journal_sub is not None:
            self._journal_sub.on_day_reset()
        self.clock.new_day()

        # Students start at the spawn point (no room yet) so all dispatches fire properly
        for s in self.students:
            s.location = None

        log.append(f"Day {self.clock.day} begins! ({self.clock.time_str})")

        # Journal entries (start-of-day prospective)
        for student in self.students:
            # Find crush name if student has one
            crush_name: str | None = None
            for key, romance in self.romances.items():
                if student.student_id not in key:
                    continue
                if romance.feelings_of(student.student_id) >= RomanceLevel.CRUSH:
                    other_id = key[1] if key[0] == student.student_id else key[0]
                    for s in self.students:
                        if s.student_id == other_id:
                            crush_name = s.name
                            break
                    break

            entry = generate_prospective_entry(
                student, self.clock.day, self.clock.tick,
                crush_name=crush_name,
            )
            if entry:
                student.journal.append(entry)

        return log

    def _report_card(self) -> list[str]:
        """Issue report cards for all students. Returns log messages."""
        from .journal import generate_grade_milestone_entry

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
                        bus=self.bus,
                    )
                    self.bus.emit(GameEvent(
                        GameEventType.GRADE_FAILED,
                        student_ids=[student.student_id],
                        data={"subject": subj.value},
                    ))
                elif grade.letter not in ("A", "B"):
                    all_good = False

            if all_good and student.grades:
                add_thought(student.thoughts, thought_great_report_card(), bus=self.bus)

            # Check for improvement (compare effective grade to baseline)
            improving = any(
                grade.effective > grade.baseline + 5
                for grade in student.grades.values()
            )
            if improving and not has_failing:
                add_thought(student.thoughts, thought_grades_improving(), bus=self.bus)

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
