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


# Map NeedType to the room skills that satisfy it (list to support multiple room types per need).
# CREATIVITY covers both Art Room and Music Room — students autonomously pick either.
# FUN maps to SOCIAL rooms because cafeteria/quad satisfies both needs via socializing.
NEED_TO_SKILLS: dict[NeedType, list[Skill]] = {
    NeedType.ACADEMICS: [Skill.ACADEMICS],
    NeedType.ATHLETICS: [Skill.ATHLETICS],
    NeedType.CREATIVITY: [Skill.CREATIVITY, Skill.MUSIC],  # Art Room or Music Room
    NeedType.SOCIAL:     [Skill.SOCIAL],
    NeedType.FUN:        [Skill.SOCIAL],  # cafeteria / socializing is fun
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
            log.extend(_process_activity(student, state=state))
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


def _process_activity(student: Student, state: "GameState | None" = None) -> list[str]:
    """Process 1 tick of an ongoing activity (studying, exercising, etc.)"""
    bus = state.bus if state is not None else None
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
            # Journal: skill milestone entry
            if state is not None and hasattr(state, '_journal_sub') and state._journal_sub is not None:
                from .journal import generate_event_entry
                j_entry = generate_event_entry(
                    student, state.clock.day, state.clock.tick,
                    "skill_milestone", skill=room.skill_boost.value,
                )
                if j_entry:
                    student.journal.append(j_entry)

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

        # Journal: activity reflection hook
        if state is not None and hasattr(state, '_journal_sub') and state._journal_sub is not None:
            state._journal_sub.on_activity_complete(student, room.skill_boost, room.name)

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
    """A student decides where to go based on needs + social pull.

    Each room is scored by:
    1. Need satisfaction — does this room's skill match my lowest needs?
    2. Social pull — are my friends, crush, or partner here?

    The highest-scoring room wins. This creates organic clique formation
    (friends drift toward each other) and crush-seeking (drama intensifies).
    """
    from .models import FriendshipLevel, RomanceLevel

    log: list[str] = []

    # Rest if REST need is critically low
    if student.needs[NeedType.REST].value < 25:
        student.state = StudentState.RESTING
        student.activity_ticks_left = random.randint(3, 6)
        log.append(f"{student.name} is tired and sits down to rest.")
        return log

    sid = student.student_id

    # ── Score each room ──────────────────────────────────────────

    # Need scores: which needs are low and which rooms satisfy them
    sorted_needs = sorted(student.needs.values(), key=lambda n: n.value)
    lowest_need = sorted_needs[0]

    # Build a set of "desirable" skills from the bottom 3 needs
    desirable_skills: set[Skill] = set()
    for need in sorted_needs[:3]:
        skills = NEED_TO_SKILLS.get(need.need_type)
        if skills:
            desirable_skills.update(skills)

    # Pre-compute who is in each room
    students_in_room: dict[str, list[Student]] = {}
    for s in state.students:
        if s.student_id != sid and s.location is not None:
            students_in_room.setdefault(s.location.name, []).append(s)

    # Social pull scores per room
    _SOCIAL_SCORES = {
        FriendshipLevel.BEST_FRIEND: 15,
        FriendshipLevel.CLOSE_FRIEND: 10,
        FriendshipLevel.FRIEND: 5,
    }

    room_scores: dict[str, float] = {}
    room_reasons: dict[str, str] = {}  # for log messages

    for room in state.rooms:
        score = 0.0
        reason = ""

        # Need satisfaction score
        if room.skill_boost in desirable_skills:
            # Higher score if it matches the LOWEST need specifically
            primary_skills = NEED_TO_SKILLS.get(lowest_need.need_type, [])
            if room.skill_boost in primary_skills:
                score += 20.0  # primary need match
            else:
                score += 10.0  # secondary need match
            reason = f"{lowest_need.need_type.value} is low"

        # Social pull: check who's in this room
        occupants = students_in_room.get(room.name, [])
        social_bonus = 0.0
        social_reason = ""

        for other in occupants:
            key = (min(sid, other.student_id), max(sid, other.student_id))

            # Friendship pull
            fri = state.friendships.get(key)
            if fri:
                bonus = _SOCIAL_SCORES.get(fri.level, 0)
                if bonus > social_bonus:
                    social_bonus = bonus
                    social_reason = f"{other.name} is there"

            # Crush/dating pull (stronger than friendship)
            rom = state.romances.get(key)
            if rom:
                my_feelings = rom.feelings_of(sid)
                if my_feelings == RomanceLevel.DATING:
                    social_bonus = max(social_bonus, 20.0)
                    social_reason = f"{other.name} is there"
                elif my_feelings == RomanceLevel.CRUSH:
                    social_bonus = max(social_bonus, 12.0)
                    social_reason = f"{other.name} is there"

        score += social_bonus

        # Small random jitter to prevent deterministic lock-in
        score += random.uniform(0, 3.0)

        room_scores[room.name] = score
        if social_reason and social_bonus > 5:
            room_reasons[room.name] = social_reason
        elif reason:
            room_reasons[room.name] = reason

    # ── Pick the best room ───────────────────────────────────────

    if room_scores:
        best_room_name = max(room_scores, key=room_scores.get)
        best_room = next(r for r in state.rooms if r.name == best_room_name)
        reason = room_reasons.get(best_room_name, "")

        send_to_room(student, best_room)
        if reason:
            log.append(f"{student.name} heads to the {best_room.name} ({reason}).")
        else:
            log.append(f"{student.name} wanders toward the {best_room.name}.")
    else:
        room = random.choice(state.rooms)
        send_to_room(student, room)
        log.append(f"{student.name} wanders toward the {room.name}.")

    return log
