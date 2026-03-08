"""Game engine. This owns the GameState and runs the ticker loop.

Engine calls behaviors.process_student() for each student, each tick, checks for
social interactions, triggers events, manages day cycle.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from .behaviors import process_student, send_to_room
from .clock import TICKS_PER_DAY, GameClock
from .events import check_for_event, resolve_event
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
)
from .social import get_or_create_friendship, maybe_interact

DEFAULT_ROOMS: list[Room] = [
    Room(
        name="Library",
        skill_boost=Skill.ACADEMICS,
        boost_per_tick=1.5,
        mood_per_tick=0.4,
        description="Quiet study spot. Academics soar, but restless students get bored.",
        position=(0, 0),
    ),
    Room(
        name="Art Room",
        skill_boost=Skill.CREATIVITY,
        boost_per_tick=1.5,
        mood_per_tick=0.7,
        description="Paints, clay, and self-expression.",
        position=(2, 0),
    ),
    Room(
        name="Gym",
        skill_boost=Skill.ATHLETICS,
        boost_per_tick=1.5,
        mood_per_tick=0.5,
        description="Hoops, laps, and pickup games.",
        position=(0, 2),
    ),
    Room(
        name="Cafeteria",
        skill_boost=Skill.SOCIAL,
        boost_per_tick=1.0,
        mood_per_tick=1.0,
        description="Lunch tables and gossip. Everyone's mood lifts. Drama brews.",
        position=(2, 2),
    ),
]

DEFAULT_NAMES: list[str] = [
    "Alex",
    "Jordan",
    "Casey",
    "Morgan",
    "Riley",
    "Quinn",
    "Sage",
    "Rowan",
]


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

    # Messages generated this tick
    tick_log: list[str] = field(default_factory=list)

    @classmethod
    def new_game(cls, num_students: int = 8) -> "GameState":
        """Create a fresh game with default settings."""
        names = random.sample(DEFAULT_NAMES, min(num_students, len(DEFAULT_NAMES)))
        while len(names) < num_students:
            # Fill out the rest of the list with placeholder names
            names.append(f"Student {len(names) + 1}")

        students = [Student(name=name, student_id=i) for i, name in enumerate(names)]

        state = cls(students=students, rooms=list(DEFAULT_ROOMS))

        # Start the day with all students in the cafeteria
        cafeteria = state.get_room_by_name("Cafeteria")
        if cafeteria:
            for s in students:
                s.location = cafeteria

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
        """Run ticks until the current day ends.

        Useful for 'skip day'. Returns all accumulated log messages."""
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
        """Students in the same room who are idle or doing activities might start
        chatting."""
        for room in self.rooms:
            # Find students in this room (not traveling)
            present = [
                s
                for s in self.students
                if s.location == room
                and s.state not in (StudentState.TRAVELING, StudentState.CHATTING)
            ]
            if len(present) < 2:  # Only 1 person in the room
                continue
            # Set small chance per pair per tick
            for i, a in enumerate(present):
                for b in present[i + 1 :]:
                    if random.random() < 0.03:  # 3% chance
                        self._start_chat(a, b, room)

    def _start_chat(self, a: Student, b: Student, room: Room) -> None:
        """Make two students start to chat."""
        # Don't interrupt their activities (except idling)
        if a.state != StudentState.IDLE or b.state != StudentState.IDLE:
            # Small chance (15%) to interrupt their activity for a chat
            if random.random() > 0.15:
                return

        rel = get_or_create_friendship(self.friendships, a, b)
        text = maybe_interact(a, b, rel)

        for person in [a, b]:
            person.state = StudentState.CHATTING
            duration = random.randint(2, 5)  # 20–50 game minutes
            person.activity_ticks_left = duration
        a.chat_partner_id = b.student_id
        b.chat_partner_id = a.student_id

        if text:
            self.tick_log.append(text)

    # -----------
    # ENDING DAY
    # -----------

    def _end_of_day(self) -> list[str]:
        """Process end-of-day: tally points, generate journals, reset."""
        log: list[str] = []
        log.append(f"Day {self.clock.day} is over!")

        day_points = self._calculate_day_points()
        self.total_points += day_points
        log.append(
            f"Day earned {day_points} points. Total: {self.total_points}/{self.graduation_target}"
        )

        for student in self.students:
            if random.random() < 0.4:
                entry = generate_journal_entry(student, self.clock.day)
                student.journal.append((self.clock.day, entry))
                log.append(f"{student.name} wrote in their journal")

        if self.total_points >= self.graduation_target:
            log.append("GRADUATION!! Your students made it!")

        # Reset all
        for student in self.students:
            student.state = StudentState.IDLE
            student.destination = None
            student.travel_ticks_left = 0
            student.activity_ticks_left = 0
            student.chat_partner_id = None
            # Recover energy overnight
            student.energy = min(100, student.energy + random.randint(30, 50))

        # Move to next day
        self.clock.new_day()

        # Everyone starts in the cafeteria
        cafeteria = self.get_room_by_name("Cafeteria")
        if cafeteria:
            for s in self.students:
                s.location = cafeteria

        log.append(f"Day {self.clock.day} begins! ({self.clock.time_str})")
        return log

    def _calculate_day_points(self) -> int:
        if not self.students:
            return 0
        n = len(self.students)
        avg_mood = sum(s.mood_value for s in self.students) / n
        avg_skill = sum(
            sum(s.skills.values()) / len(s.skills) for s in self.students
        ) / n
        # Mood contributes base points, skill growth adds bonus
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
