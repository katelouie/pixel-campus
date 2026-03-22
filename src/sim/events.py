"""Events — player-driven school events with scheduling and resolution.

The player picks events from a menu, pays a point cost, and a countdown
starts. When the countdown hits zero the event resolves based on the
team's total skill in the relevant area. Completing enough events unlocks
graduation.

Special event: "The Big Party" — a student hosts and invites others based
on relationships, traits, and compatibility.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import GameState

from .models import Skill
from .needs import NeedType, satisfy_need
from .thoughts import add_thought, thought_event_failure, thought_event_success
from .traits import combined_thought_mult


@dataclass
class SchoolEvent:
    """A campus event that the player can schedule."""

    name: str
    required_skill: Skill
    description: str = ""
    point_cost: int = 30          # cost to schedule
    countdown_days: int = 5       # days of preparation before event fires
    team_threshold: int = 250     # sum of all students' relevant skill must meet this
    is_party: bool = False        # special party resolution


# ── Default event catalog ──────────────────────────────────────────

EVENTS: list[SchoolEvent] = [
    SchoolEvent(
        name="Basketball Game",
        required_skill=Skill.ATHLETICS,
        description="The big game! Get your athletes ready.",
        point_cost=25,
        team_threshold=200,
    ),
    SchoolEvent(
        name="Art Show",
        required_skill=Skill.CREATIVITY,
        description="Students display their best creative work.",
        point_cost=25,
        team_threshold=200,
    ),
    SchoolEvent(
        name="Finals Week",
        required_skill=Skill.ACADEMICS,
        description="Cramming time. Hit the books!",
        point_cost=30,
        team_threshold=250,
    ),
    SchoolEvent(
        name="Science Fair",
        required_skill=Skill.ACADEMICS,
        description="Hypotheses, experiments, poster boards.",
        point_cost=30,
        team_threshold=220,
    ),
    SchoolEvent(
        name="Talent Show",
        required_skill=Skill.MUSIC,
        description="Time to shine on stage.",
        point_cost=25,
        team_threshold=180,
    ),
    SchoolEvent(
        name="Prom",
        required_skill=Skill.SOCIAL,
        description="The social event of the year!",
        point_cost=35,
        team_threshold=200,
    ),
    SchoolEvent(
        name="The Big Party",
        required_skill=Skill.SOCIAL,
        description="Pick a host. Send invitations. Hope people show up.",
        point_cost=20,
        team_threshold=0,  # not used — party has special resolution
        is_party=True,
    ),
]

# Number of events required to unlock graduation (out of total)
EVENTS_REQUIRED_FOR_GRADUATION = 5


@dataclass
class ScheduledEvent:
    """An event that has been scheduled and is counting down."""

    event_name: str
    days_remaining: int
    host_student_id: int | None = None  # party only
    invitations: dict[int, bool] = field(default_factory=dict)  # student_id → accepted (party only)


# ── Catalog lookup ─────────────────────────────────────────────────

def get_event_by_name(name: str) -> SchoolEvent | None:
    """Look up an event by name."""
    for e in EVENTS:
        if e.name == name:
            return e
    return None


# ── Scheduling ─────────────────────────────────────────────────────

def schedule_event(
    state: "GameState", event_name: str, host_id: int | None = None
) -> str | None:
    """Schedule an event. Returns an error message, or None on success."""
    if state.scheduled_event is not None:
        return "An event is already scheduled."

    event = get_event_by_name(event_name)
    if not event:
        return f"Unknown event: {event_name}"

    if event_name in state.completed_events:
        return f"{event_name} is already completed."

    if state.total_points < event.point_cost:
        return f"Not enough points ({state.total_points}/{event.point_cost})."

    if event.is_party and host_id is None:
        return "The Big Party requires a host student."

    # Pay the cost
    state.total_points -= event.point_cost

    state.scheduled_event = ScheduledEvent(
        event_name=event_name,
        days_remaining=event.countdown_days,
        host_student_id=host_id,
    )
    return None


def cancel_event(state: "GameState") -> str | None:
    """Cancel the scheduled event with a 50% point refund. Returns error or None."""
    if state.scheduled_event is None:
        return "No event scheduled."

    event = get_event_by_name(state.scheduled_event.event_name)
    if event:
        refund = event.point_cost // 2
        state.total_points += refund

    state.scheduled_event = None
    return None


def tick_scheduled_event(state: "GameState") -> SchoolEvent | None:
    """Called at the start of each day. Decrements countdown, returns event if it fires."""
    sched = state.scheduled_event
    if sched is None:
        return None

    sched.days_remaining -= 1
    if sched.days_remaining <= 0:
        event = get_event_by_name(sched.event_name)
        return event  # caller should resolve and clear scheduled_event

    return None


# ── Party invitation logic ─────────────────────────────────────────

def process_party_invitation(state: "GameState", host_id: int, target_id: int) -> bool:
    """Determine if a target student accepts a party invitation from the host.

    Factors: friendship level, romance, trait compatibility, random chance.
    Returns True if accepted.
    """
    import random
    from .models import FriendshipLevel, RomanceLevel
    from .traits import has_trait

    host = next((s for s in state.students if s.student_id == host_id), None)
    target = next((s for s in state.students if s.student_id == target_id), None)
    if not host or not target:
        return False

    # Base acceptance rate
    accept_chance = 0.30

    # Friendship bonus
    key = (min(host_id, target_id), max(host_id, target_id))
    fri = state.friendships.get(key)
    if fri:
        accept_chance += {
            FriendshipLevel.ACQUAINTANCE: 0.15,
            FriendshipLevel.FRIEND: 0.35,
            FriendshipLevel.CLOSE_FRIEND: 0.55,
            FriendshipLevel.BEST_FRIEND: 0.65,
        }.get(fri.level, 0.0)

    # Romance bonus
    rom = state.romances.get(key)
    if rom:
        if rom.is_dating:
            accept_chance = 0.99  # basically auto-accept
        elif rom.feelings_of(target_id) >= RomanceLevel.CRUSH:
            accept_chance += 0.40  # crush on the host? definitely going

    # Trait modifiers
    if has_trait(target, "Social Butterfly"):
        accept_chance += 0.25
    if has_trait(target, "Loner"):
        accept_chance -= 0.30
    if has_trait(target, "Anxious"):
        accept_chance -= 0.10
    if has_trait(target, "Rebel"):
        accept_chance += 0.10  # rebels love parties

    # Compatibility
    if host.personality and target.personality:
        compat = host.personality.compatibility_score(target.personality)
        accept_chance += compat * 0.15

    return random.random() < max(0.05, min(0.95, accept_chance))


# ── Resolution ─────────────────────────────────────────────────────

def resolve_standard_event(state: "GameState", event: SchoolEvent) -> dict:
    """Resolve a standard (non-party) event. Returns results dict."""
    skill_totals: list[tuple[str, float]] = []
    team_total = 0.0

    for student in state.students:
        val = student.skills.get(event.required_skill, 0.0)
        skill_totals.append((student.name, val))
        team_total += val

    passed = team_total >= event.team_threshold

    # Apply effects to students
    for student in state.students:
        if passed:
            satisfy_need(student.needs, NeedType.FUN, 10)
            satisfy_need(student.needs, NeedType.SOCIAL, 5)
            t = thought_event_success(event.name)
            t.mood_effect *= combined_thought_mult(student.traits, t.category, t.mood_effect)
            add_thought(student.thoughts, t, bus=state.bus)
        else:
            satisfy_need(student.needs, NeedType.FUN, -5)
            t = thought_event_failure(event.name)
            t.mood_effect *= combined_thought_mult(student.traits, t.category, t.mood_effect)
            add_thought(student.thoughts, t, bus=state.bus)

    if passed:
        state.completed_events.add(event.name)

    state.scheduled_event = None

    # Find MVP (highest skill)
    skill_totals.sort(key=lambda x: x[1], reverse=True)
    mvp = skill_totals[0] if skill_totals else None

    return {
        "event_name": event.name,
        "skill_name": event.required_skill.value,
        "team_total": team_total,
        "threshold": event.team_threshold,
        "passed": passed,
        "per_student": skill_totals,
        "mvp": mvp,
    }


def resolve_party_event(state: "GameState", event: SchoolEvent) -> dict:
    """Resolve The Big Party. Returns results dict."""
    sched = state.scheduled_event
    if not sched:
        return {"event_name": event.name, "passed": False, "attendees": 0, "total": 0}

    host_id = sched.host_student_id
    host = next((s for s in state.students if s.student_id == host_id), None)

    # Process any remaining invitations
    others = [s for s in state.students if s.student_id != host_id]
    for other in others:
        if other.student_id not in sched.invitations:
            accepted = process_party_invitation(state, host_id, other.student_id)
            sched.invitations[other.student_id] = accepted

    attendees = [sid for sid, accepted in sched.invitations.items() if accepted]
    total_others = len(others)
    attendance_ratio = len(attendees) / total_others if total_others > 0 else 0
    passed = attendance_ratio >= 0.6

    # Effects
    for student in state.students:
        is_attendee = student.student_id in attendees or student.student_id == host_id
        if is_attendee:
            satisfy_need(student.needs, NeedType.FUN, 15)
            satisfy_need(student.needs, NeedType.SOCIAL, 10)
            t = thought_event_success(event.name)
            t.mood_effect *= combined_thought_mult(student.traits, t.category, t.mood_effect)
            add_thought(student.thoughts, t, bus=state.bus)

    # Host always gets a mood boost (they tried!)
    if host:
        satisfy_need(host.needs, NeedType.FUN, 8)

    if passed:
        state.completed_events.add(event.name)

    state.scheduled_event = None

    return {
        "event_name": event.name,
        "host_name": host.name if host else "???",
        "host_id": host_id,
        "attendees": [(s.name, True) for s in state.students if s.student_id in attendees],
        "declined": [(s.name, False) for s in others if s.student_id not in attendees],
        "attendance_count": len(attendees) + 1,  # +1 for host
        "total_students": len(state.students),
        "passed": passed,
    }
