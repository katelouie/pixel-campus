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
from .events import (
    SchoolEvent, ScheduledEvent, get_event_by_name,
    resolve_party_event, resolve_standard_event, tick_scheduled_event,
)
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

    # Event system — player-driven scheduling
    scheduled_event: ScheduledEvent | None = None
    completed_events: set[str] = field(default_factory=set)
    school_year: int = 1  # increments at each graduation

    # Event bus — reactive systems subscribe here at startup
    bus: GameEventBus = field(default_factory=GameEventBus)

    # Today's weather — rolled fresh each day
    current_weather: Weather = field(default_factory=lambda: random.choice(list(Weather)))

    # Messages generated this tick
    tick_log: list[str] = field(default_factory=list)

    # Journal subscriber — set by new_game(), used for tick checks & activity hooks
    _journal_sub: Any = field(default=None, repr=False)

    # Pending event — set when a countdown hits zero, consumed by UI to show results modal
    _pending_event: SchoolEvent | None = field(default=None, repr=False)

    # Day summary — populated at end of day, consumed by UI to show summary card
    _day_summary: dict | None = field(default=None, repr=False)

    # Skill snapshot — captured at day start for computing deltas
    _skill_snapshot: dict[int, dict[str, float]] = field(default_factory=dict, repr=False)

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
        _surname_pool = _names_data.get("surnames", [])

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

        # Assign unique surnames
        _used_surnames: set[str] = set()
        surnames: list[str] = []
        for _ in range(actual_num_students):
            available = [s for s in _surname_pool if s not in _used_surnames]
            if available:
                surname = random.choice(available)
                _used_surnames.add(surname)
                surnames.append(surname)
            else:
                surnames.append("")

        students = []
        for i, (name, surname, gender) in enumerate(zip(names, surnames, _genders)):
            student = Student(
                name=name,
                last_name=surname,
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

        # Check for scheduled event countdown (fires at start of day)
        if self.clock.tick == 0 and self.scheduled_event is not None:
            ready_event = tick_scheduled_event(self)
            if ready_event:
                # Event fires! Resolution handled by the UI layer (shows modal)
                self._pending_event = ready_event

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

        # Build day summary for the UI
        self._day_summary = self._build_day_summary(day_points, log)

        self.bus.emit(GameEvent(
            GameEventType.DAY_ENDED,
            data={"day": self.clock.day, "points": day_points},
        ))

        # Roll tomorrow's weather (season-weighted)
        from .clock import get_season
        season = get_season(self.clock.day + 1)
        _WEATHER_WEIGHTS: dict[str, dict[Weather, int]] = {
            "fall":   {Weather.SUNNY: 3, Weather.CLOUDY: 4, Weather.RAIN: 3, Weather.WINDY: 2, Weather.STORM: 1, Weather.SNOW: 0},
            "winter": {Weather.SUNNY: 2, Weather.CLOUDY: 4, Weather.RAIN: 3, Weather.WINDY: 2, Weather.STORM: 2, Weather.SNOW: 3},
            "spring": {Weather.SUNNY: 5, Weather.CLOUDY: 3, Weather.RAIN: 2, Weather.WINDY: 1, Weather.STORM: 1, Weather.SNOW: 0},
            "summer": {Weather.SUNNY: 6, Weather.CLOUDY: 2, Weather.RAIN: 1, Weather.WINDY: 1, Weather.STORM: 1, Weather.SNOW: 0},
        }
        weights = _WEATHER_WEIGHTS.get(season, {w: 1 for w in Weather})
        weathers = list(weights.keys())
        probs = [weights[w] for w in weathers]
        self.current_weather = random.choices(weathers, weights=probs, k=1)[0]
        log.append(f"Tomorrow: {self.current_weather.value} ({season}).")

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

        # Snapshot skills for end-of-day delta computation
        self._skill_snapshot = {
            s.student_id: {sk.value: v for sk, v in s.skills.items()}
            for s in self.students
        }

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

    def compute_school_stats(self) -> dict:
        """Compute school-wide averages for skills and mood.

        Returns a dict with:
          skills: {skill_name: avg_value}
          mood: avg_mood_value
          moods: [(name, mood_name, mood_value), ...]
        """
        from .models import Skill
        _DISPLAY_SKILLS = [Skill.ACADEMICS, Skill.ATHLETICS, Skill.CREATIVITY, Skill.SOCIAL, Skill.MUSIC]
        n = len(self.students) or 1

        skill_avgs = {}
        for skill in _DISPLAY_SKILLS:
            total = sum(s.skills.get(skill, 0.0) for s in self.students)
            skill_avgs[skill.value] = round(total / n, 1)

        mood_avg = round(sum(s.mood_value for s in self.students) / n, 1)
        moods = [(s.name, s.mood.name, int(s.mood_value)) for s in self.students]

        return {
            "skills": skill_avgs,
            "mood": mood_avg,
            "moods": moods,
        }

    def _build_day_summary(self, day_points: int, log: list[str]) -> dict:
        """Build a structured summary of today's activity for the UI."""
        from .clock import get_season
        from .models import Skill
        day = self.clock.day
        season = get_season(day)

        # School-wide skill averages (current)
        stats = self.compute_school_stats()

        # Compute school-wide skill deltas from snapshot
        _DISPLAY_SKILLS = [Skill.ACADEMICS, Skill.ATHLETICS, Skill.CREATIVITY, Skill.SOCIAL, Skill.MUSIC]
        n = len(self.students) or 1
        skill_deltas: dict[str, float] = {}
        for skill in _DISPLAY_SKILLS:
            prev_total = sum(
                self._skill_snapshot.get(s.student_id, {}).get(skill.value, 0.0)
                for s in self.students
            )
            prev_avg = prev_total / n
            current_avg = stats["skills"][skill.value]
            delta = round(current_avg - prev_avg, 1)
            if abs(delta) >= 0.1:
                skill_deltas[skill.value] = delta

        # Relationship changes (scan log for friendship/romance messages)
        rel_changes: list[str] = []
        for msg in log:
            if any(kw in msg.lower() for kw in ["crush", "dating", "friend", "best friend", "close friend"]):
                if "journal" not in msg.lower():
                    rel_changes.append(msg)

        # Conversations (conflicts and matches)
        conversations: list[str] = []
        for msg in log:
            if any(kw in msg.lower() for kw in ["conflict", "match", "chatted", "argued", "snapped"]):
                conversations.append(msg)

        # Event countdown
        event_info = None
        if self.scheduled_event:
            event_info = {
                "name": self.scheduled_event.event_name,
                "days_remaining": self.scheduled_event.days_remaining,
            }

        return {
            "day": day,
            "season": season,
            "weather": self.current_weather.value,
            "tomorrow_weather": self.current_weather.value,  # already rolled
            "points_today": day_points,
            "points_total": self.total_points,
            "school_stats": stats,
            "skill_deltas": skill_deltas,
            "rel_changes": rel_changes,
            "conversations": conversations,
            "event_info": event_info,
        }

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
        """Save the full game state to a JSON file."""
        from .serialization import save_game
        save_game(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "GameState":
        """Load a full game state from a JSON file."""
        from .serialization import load_game
        return load_game(path)
