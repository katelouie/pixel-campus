"""Student behavior. The state machine that drives moment-to-moment life.

Each tick, process_student() advances one student by one step.
Students transition between states: IDLE -> TRAVELING -> ACTIVITY -> IDLE.
The engine calls this for every student every tick.
"""

import random
from typing import TYPE_CHECKING

from models import SKILL_TO_ACTIVITY, Room, Skill, Student, StudentState

if TYPE_CHECKING:
    from .engine import GameState


def travel_time(from_room: Room | None, to_room: Room) -> int:
    """Calculate ticks needed to travel between two rooms.

    Uses simple Manhattan distance on the room grid.
    Minimum 1 tick.
    """
    if from_room is None:
        return 2  # Wandering -> any room
    dx = abs(from_room.position[0] - to_room.position[0])
    dy = abs(from_room.position[1] - to_room.position[1])

    return max(1, dx + dy)


def send_to_room(student: Student, room: Room) -> str:
    """Player directs a student to a room. Starts travel."""
    if student.location == room and student.state != StudentState.TRAVELING:
        # Already there, just start the activity
        return start_activity(student, room)

    ticks = travel_time(student.location, room)
    student.state = StudentState.TRAVELING
    student.destination = room
    student.travel_ticks_left = ticks
    student.chat_partner_id = None
    return f"{student.name} heads toward the {room.name} ({ticks * 10} min walk)."


def start_activity(student: Student, room: Room) -> str:
    """Begin the room's activity. Called when travel completes."""
    activity = SKILL_TO_ACTIVITY.get(room.skill_boost, StudentState.SOCIALIZING)
    student.state = activity
    student.location = room
    student.destination = None
    student.travel_ticks_left = 0

    # Activity duration: 4-8 ticks (40-80 in-game minutes)
    student.activity_ticks_left = random.randint(4, 8)

    return f"{student.name} starts {activity.value} in the {room.name}."


def process_student(student: Student, state: GameState) -> list[str]:
    """Advance 1 student by 1 tick. Returns log messages.

    Called by the engine for every student * every tick.
    """
    log: list[str] = []

    match student.state:
        case StudentState.IDLE:
            log.extend(_process_idle(student, state))

        case StudentState.TRAVELING:
            log.extend(_process_traveling(student))

        case StudentState.RESTING:
            log.extend(_process_resting(student))

        case (
            StudentState.STUDYING
            | StudentState.EXERCISING
            | StudentState.CREATING
            | StudentState.SOCIALIZING
        ):
            log.extend(_process_activity(student))

        case StudentState.CHATTING:
            log.extend(_process_chatting(student, state))

    # Universal: small energy decrease every tick
    student.energy -= random.uniform(0.3, 0.8)
    student.clamp_stats()

    return log


# ---------------
# STATE HANDLERS
# ---------------


def _process_idle(student: Student, state: GameState) -> list[str]:
    """Idle students might decide to do something on their own."""
    log: list[str] = []

    # Recover a little mood and energy while idle
    student.mood_value += random.uniform(0.2, 0.8)
    student.energy += random.uniform(0.5, 1.5)

    # Autonomous decision-making
    if random.random() < 0.06:  # ~6% per tick -> expected value = once every 15 ticks
        log.extend(_autonomous_decision(student, state))

    return log


def _process_traveling(student: Student) -> list[str]:
    """Count down travel ticks. Arrive when done."""
    log: list[str] = []
    student.travel_ticks_left -= 1

    if student.travel_ticks_left <= 0:
        if student.destination:
            msg = start_activity(student, student.destination)
            log.append(msg)
        else:
            student.state = StudentState.IDLE

    return log


def _process_activity(student: Student) -> list[str]:
    """Process 1 tick of an ongoing activity (studying, exercising, etc.)"""
    log: list[str] = []
    room = student.location
    if room is None:
        student.state = StudentState.IDLE
        return log

    # Apply per-tick skill and mood effects
    pref_mult = student.preferences.get(room.skill_boost, 0.7)
    skill_gain = room.boost_per_tick * pref_mult
    student.skills[room.skill_boost] += skill_gain

    # Mood change: positive if likes it, negative if dislikes it
    mood_delta = room.mood_per_tick * pref_mult
    if pref_mult < 0.55:
        mood_delta = -abs(mood_delta) * 1.5  # really miserable
    student.mood_value += mood_delta

    # Add extra energy drain for physical activities
    if student.state == StudentState.EXERCISING:
        student.energy -= random.uniform(0.5, 1.0)

    # Count down
    student.activity_ticks_left -= 1
    if student.activity_ticks_left <= 0:
        log.append(f"{student.name} finishes {student.state.value} in the {room.name}.")
        student.state = StudentState.IDLE

    return log


def _process_chatting(student: Student, state: GameState) -> list[str]:
    """Process a 1-on-1 chat tick.

    Both participants tick together but we only process from 1 perspective (lower ID)
    to prevent double-counting.
    """
    log: list[str] = []

    # only process from the perspective of the lower student ID
    if (
        student.chat_partner_id is not None
        and student.student_id > student.chat_partner_id
    ):
        return log  # Let the partner handle it

    student.activity_ticks_left -= 1

    # Both partners get a small social/mood boost
    partner = _find_student(state, student.chat_partner_id)
    if partner:
        for person in [student, partner]:
            person.mood_value += random.uniform(0.5, 1.5)
            person.skills[Skill.SOCIAL] += 0.5

    if student.activity_ticks_left <= 0:
        if partner:
            log.append(f"{student.name} and {partner.name} finish their conversation.")
            partner.state = StudentState.IDLE
            partner.chat_partner_id = None
            partner.activity_ticks_left = 0
        student.state = StudentState.IDLE
        student.chat_partner_id = None

    return log


def _process_resting(student: Student) -> list[str]:
    """Resting recovers energy fast."""
    log: list[str] = []
    student.energy += random.uniform(2.0, 4.0)
    student.mood_value += random.uniform(0.2, 0.5)
    student.activity_ticks_left -= 1

    if student.activity_ticks_left <= 0:
        log.append(f"{student.name} feels rested.")
        student.state = StudentState.IDLE

    return log


# --------------------
# AUTONOMOUS BEHAVIORS
# --------------------


def _autonomous_decision(student: Student, state: GameState) -> list[str]:
    """A student decides to do something on their own -- AI decision."""
    log: list[str] = []

    # Rest if energy is low
    if student.energy < 25:
        student.state = StudentState.RESTING
        student.activity_ticks_left = random.randint(3, 6)
        log.append(f"{student.name} is tired and sits down to rest.")
        return log

    # Otherwise: wander to a room they like
    favorite = student.favorite_skill
    matching_rooms = [r for r in state.rooms if r.skill_boost == favorite]
    if matching_rooms:
        room = random.choice(matching_rooms)
        send_to_room(student, room)
        log.append(f"{student.name} decides on their own to head to the {room.name}.")
    else:
        # Just pick a random room to go to
        room = random.choice(state.rooms)
        send_to_room(student, room)
        log.append(f"{student.name} wanders toward the {room.name}")

    return log


# ----------------
# HELPER FUNCTIONS
# ----------------


def _find_student(state: GameState, student_id: int | None) -> Student | None:
    """Look up a student by ID."""
    if student_id is None:
        return None
    for s in state.students:
        if s.student_id == student_id:
            return s
    return None
