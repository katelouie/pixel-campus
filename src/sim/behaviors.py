"""Student behavior. The state machine that drives moment-to-moment life.

Each tick, process_student() advances one student by one step.
Students transition between states: IDLE -> TRAVELING -> ACTIVITY -> IDLE.
The engine calls this for every student every tick.
"""

import random
from typing import TYPE_CHECKING

from .academics import apply_activity_to_grades
from .game_events import GameEventBus
from .models import SKILL_TO_ACTIVITY, Room, Skill, Student, StudentState
from .needs import NeedType, satisfy_need, tick_needs
from .thoughts import (
    add_thought,
    thought_academic_pressure,
    thought_activity_dreaded,
    thought_activity_favorite,
    thought_lonely,
    thought_running_on_fumes,
    thought_skill_milestone,
    thought_so_bored,
    tick_thoughts,
)
from .traits import combined_skill_mult, combined_thought_mult

if TYPE_CHECKING:
    from .engine import GameState


# Map NeedType to the room skill that satisfies it
NEED_TO_SKILL: dict[NeedType, Skill] = {
    NeedType.ACADEMICS: Skill.ACADEMICS,
    NeedType.ATHLETICS: Skill.ATHLETICS,
    NeedType.CREATIVITY: Skill.CREATIVITY,
    NeedType.SOCIAL: Skill.SOCIAL,
    NeedType.FUN: Skill.SOCIAL,  # cafeteria / socializing is fun
}


def travel_time(from_room: Room | None, to_room: Room) -> int:
    """Calculate ticks needed to travel between two rooms.

    Uses simple Manhattan distance on the room grid. Minimum 1 tick.
    """
    if from_room is None:
        return 2
    dx = abs(from_room.position[0] - to_room.position[0])
    dy = abs(from_room.position[1] - to_room.position[1])
    return max(1, dx + dy)


def send_to_room(student: Student, room: Room) -> str:
    """Player directs a student to a room. Starts travel."""
    if student.location == room and student.state != StudentState.TRAVELING:
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
    student.activity_ticks_left = random.randint(4, 8)
    return f"{student.name} starts {activity.value} in the {room.name}."


def process_student(student: Student, state: "GameState") -> list[str]:
    """Advance 1 student by 1 tick. Returns log messages."""
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
            log.extend(_process_activity(student, bus=state.bus))
        case StudentState.CHATTING:
            log.extend(_process_chatting(student, state))

    # Universal: decay all needs each tick (traits modify decay rates)
    tick_needs(student.needs, traits=student.traits)
    student.clamp_stats()

    # Tick thoughts (expire old ones)
    student.thoughts = tick_thoughts(student.thoughts)

    # Critical need thoughts (refresh while need stays low)
    if student.needs[NeedType.REST].value < 10:
        add_thought(student.thoughts, thought_running_on_fumes(), bus=state.bus)
    if student.needs[NeedType.FUN].value < 15:
        add_thought(student.thoughts, thought_so_bored(), bus=state.bus)
    if student.needs[NeedType.SOCIAL].value < 20:
        add_thought(student.thoughts, thought_lonely(), bus=state.bus)
    if student.needs[NeedType.ACADEMICS].value < 15:
        add_thought(student.thoughts, thought_academic_pressure(), bus=state.bus)

    return log


# ---------------
# STATE HANDLERS
# ---------------


def _process_idle(student: Student, state: "GameState") -> list[str]:
    """Idle students recover slightly and might decide to do something."""
    log: list[str] = []

    # Small recovery while idle — being free is restful and mildly fun,
    # but not as much as actual resting. REST 0.3 means idle alone won't
    # keep REST from slowly declining — students need real sleep or rest rooms.
    satisfy_need(student.needs, NeedType.REST, 0.3)
    satisfy_need(student.needs, NeedType.FUN, 0.5)

    # Autonomous decision-making (suppressed during lunch — cafeteria dispatch handles it)
    if not state.is_lunch_period and random.random() < 0.06:
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


def _process_activity(student: Student, bus: GameEventBus | None = None) -> list[str]:
    """Process 1 tick of an ongoing activity (studying, exercising, etc.)"""
    log: list[str] = []
    room = student.location
    if room is None:
        student.state = StudentState.IDLE
        return log

    # Apply skill growth (modified by traits and current mood)
    # Mood multiplier: 0.5x at mood 0, 1.0x at mood 50, 1.5x at mood 100.
    # Creates the core cascade: bad mood → slower growth → worse grades → worse thoughts → worse mood.
    trait_skill_mult = combined_skill_mult(student.traits, room.skill_boost.value)
    mood_mult = 0.5 + (student.mood_value / 100.0)
    skill_gain = room.boost_per_tick * trait_skill_mult * mood_mult
    old_skill = student.skills.get(room.skill_boost, 0.0)
    student.skills[room.skill_boost] = old_skill + skill_gain
    new_skill = student.skills[room.skill_boost]
    for threshold in (25, 50, 75, 100):
        if old_skill < threshold <= new_skill:
            add_thought(student.thoughts, thought_skill_milestone(room.skill_boost.value, threshold), bus=bus)

    # Apply need satisfaction from this room (traits modify satisfaction amounts)
    for need_key, amount in room.needs_satisfied.items():
        try:
            need_type = NeedType(need_key)
            satisfy_need(student.needs, need_type, amount, traits=student.traits)
        except ValueError:
            pass  # unknown need key, skip

    # Apply grade contributions for related subjects
    apply_activity_to_grades(student.grades, room.skill_boost, skill_gain)

    # Count down
    student.activity_ticks_left -= 1
    if student.activity_ticks_left <= 0:
        log.append(
            f"{student.name} finishes {student.state.value} in the {room.name}."
        )
        # Activity completion thoughts based on trait-derived preferences
        if room.skill_boost == student.favorite_skill:
            thought = thought_activity_favorite(room.skill_boost.value)
            thought.mood_effect *= combined_thought_mult(
                student.traits, thought.category, thought.mood_effect
            )
            add_thought(student.thoughts, thought, bus=bus)
        elif room.skill_boost == student.dreaded_skill:
            thought = thought_activity_dreaded(room.skill_boost.value)
            thought.mood_effect *= combined_thought_mult(
                student.traits, thought.category, thought.mood_effect
            )
            add_thought(student.thoughts, thought, bus=bus)
        student.state = StudentState.IDLE

    return log


def _process_chatting(student: Student, state: "GameState") -> list[str]:
    """Process a 1-on-1 chat tick."""
    log: list[str] = []

    # Only process from the lower student ID's perspective
    if (
        student.chat_partner_id is not None
        and student.student_id > student.chat_partner_id
    ):
        return log

    student.activity_ticks_left -= 1

    partner = state.get_student_by_id(student.chat_partner_id)
    if partner:
        for person in [student, partner]:
            skill_mult = combined_skill_mult(person.traits, Skill.SOCIAL.value)
            person.skills[Skill.SOCIAL] += 0.5 * skill_mult
            satisfy_need(person.needs, NeedType.SOCIAL, 1.5, traits=person.traits)
            satisfy_need(person.needs, NeedType.FUN, 0.5, traits=person.traits)

    if student.activity_ticks_left <= 0:
        if partner:
            log.append(
                f"{student.name} and {partner.name} finish their conversation."
            )
            partner.state = StudentState.IDLE
            partner.chat_partner_id = None
            partner.activity_ticks_left = 0
        student.state = StudentState.IDLE
        student.chat_partner_id = None

    return log


def _process_resting(student: Student) -> list[str]:
    """Resting recovers REST need fast."""
    log: list[str] = []
    satisfy_need(student.needs, NeedType.REST, 3.0)
    satisfy_need(student.needs, NeedType.FUN, 0.2)
    student.activity_ticks_left -= 1

    if student.activity_ticks_left <= 0:
        log.append(f"{student.name} feels rested.")
        student.state = StudentState.IDLE

    return log


# --------------------
# AUTONOMOUS BEHAVIORS
# --------------------


def _autonomous_decision(student: Student, state: "GameState") -> list[str]:
    """A student decides to do something on their own based on their most depleted need."""
    log: list[str] = []

    # Rest if REST need is critically low
    if student.needs[NeedType.REST].value < 25:
        student.state = StudentState.RESTING
        student.activity_ticks_left = random.randint(3, 6)
        log.append(f"{student.name} is tired and sits down to rest.")
        return log

    # Find the most depleted need (weighted by preference for variety)
    lowest_need = min(
        student.needs.values(),
        key=lambda n: n.value,
    )

    # Find a room that satisfies this need
    target_skill = NEED_TO_SKILL.get(lowest_need.need_type)
    if target_skill:
        matching_rooms = [
            r for r in state.rooms if r.skill_boost == target_skill
        ]
        if matching_rooms:
            room = random.choice(matching_rooms)
            send_to_room(student, room)
            log.append(
                f"{student.name} decides to head to the {room.name} "
                f"({lowest_need.need_type.value} is low)."
            )
            return log

    # Fallback: pick a random room
    room = random.choice(state.rooms)
    send_to_room(student, room)
    log.append(f"{student.name} wanders toward the {room.name}.")
    return log
