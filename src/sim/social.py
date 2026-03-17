"""Social system. Relationships, compatibility, interactions.

Students who share space build affinity. That affinity crosses number thresholds to
level up relationships
"""

import random
from .models import Friendship, FriendshipLevel, Romance, RomanceLevel, Skill, Student
from .personality import RomanceInterest
from .thoughts import add_thought, thought_best_friend, thought_crush, thought_dating, thought_friendship_levelup
from .traits import has_trait

FRIENDSHIP_LEVEL_THRESHOLDS: dict[FriendshipLevel, int] = {
    FriendshipLevel.STRANGER: 0,
    FriendshipLevel.ACQUAINTANCE: 15,
    FriendshipLevel.FRIEND: 35,
    FriendshipLevel.CLOSE_FRIEND: 55,
    FriendshipLevel.BEST_FRIEND: 75,
}

ROMANCE_LEVEL_THRESHOLDS: dict[RomanceLevel, int] = {
    # TODO: rethink and tune romance level thresholds
    RomanceLevel.PLATONIC: 0,
    RomanceLevel.CRUSH: 25,
    RomanceLevel.DATING: 50,
}

TEXT_TEMPLATES: dict[FriendshipLevel | RomanceLevel, list[str]] = {
    FriendshipLevel.STRANGER: [
        "{a} and {b} awkwardly make eye contact.",
        "{a} nods at {b}. {b} nods back.",
        "{a} accidentally bumps into {b}. 'Oh, sorry!'",
    ],
    FriendshipLevel.ACQUAINTANCE: [
        "{a} and {b} chat about homework.",
        "{b} asks {a} about their weekend plans.",
        "{a} and {b} discover they both like the same show.",
    ],
    FriendshipLevel.FRIEND: [
        "{a} and {b} are cracking up about something.",
        "{a} saves {b} a seat.",
        "{b} shares their snacks with {a}.",
    ],
    FriendshipLevel.CLOSE_FRIEND: [
        "{a} and {b} have a deep conversation.",
        "{a} confides something personal to {b}.",
        "{b} and {a} make plans for the weekend.",
    ],
    FriendshipLevel.BEST_FRIEND: [
        "{a} and {b} share a look that says everything.",
        "{a} and {b} have their own secret handshake.",
        "{b} knows exactly what {a} is thinking.",
    ],
    RomanceLevel.PLATONIC: [
        "{a} and {b} exchange a polite smile.",
        "{a} holds the door for {b}.",
    ],
    "unrequited": [
        "{a} can't stop thinking about {b}.",
        "{a} laughs a little too hard at everything {b} says.",
        "{b} has no idea {a} has a crush on them.",
        "{a} wrote {b}'s name in their notebook. Classic.",
        "{a} keeps finding excuses to walk past {b}'s locker.",
        "{a} rehearsed what to say to {b} three times. Still said nothing.",
    ],
    RomanceLevel.CRUSH: [
        "{a} keeps glancing at {b} when they're not looking.",
        "{b} gets flustered when {a} sits next to them.",
        "{a} and {b} keep catching each other's eye across the room.",
        "{b} saved a seat for {a} without really thinking about it.",
    ],
    RomanceLevel.DATING: [
        "{a} and {b} are holding hands.",
        "{a} and {b} share headphones, each with one earbud.",
        "{b} left a cute note in {a}'s locker.",
        "{a} and {b} walk to class together every morning now.",
    ],
}

# Mapping from JSON keys to enum values for loading from defs
_FRIENDSHIP_KEY_MAP: dict[str, FriendshipLevel] = {
    "stranger": FriendshipLevel.STRANGER,
    "acquaintance": FriendshipLevel.ACQUAINTANCE,
    "friend": FriendshipLevel.FRIEND,
    "close_friend": FriendshipLevel.CLOSE_FRIEND,
    "best_friend": FriendshipLevel.BEST_FRIEND,
}

_ROMANCE_KEY_MAP: dict[str, RomanceLevel] = {
    "platonic": RomanceLevel.PLATONIC,
    "crush": RomanceLevel.CRUSH,
    "dating": RomanceLevel.DATING,
}


def load_text_from_defs(social_text: dict) -> None:
    """Replace TEXT_TEMPLATES with content from social_text.json.

    Called by engine.py during new_game() if JSON defs are available.
    """
    global TEXT_TEMPLATES

    if "friendship" in social_text:
        for key, templates in social_text["friendship"].items():
            level = _FRIENDSHIP_KEY_MAP.get(key)
            if level and templates:
                TEXT_TEMPLATES[level] = templates

    if "romance" in social_text:
        for key, templates in social_text["romance"].items():
            level = _ROMANCE_KEY_MAP.get(key)
            if level and templates:
                TEXT_TEMPLATES[level] = templates


def compatibility(a: Student, b: Student) -> float:
    """Compatibility score combining shared traits and personality preferences (0.3–1.0).

    Traits and personality preferences contribute equally when both are present.
    Falls back gracefully if either is missing.
    """
    scores = []

    # Trait compatibility
    a_trait_names = {t.name for t in a.traits}
    b_trait_names = {t.name for t in b.traits}
    all_traits = a_trait_names | b_trait_names
    if all_traits:
        shared = a_trait_names & b_trait_names
        scores.append(0.4 + len(shared) / len(all_traits) * 0.6)
    else:
        scores.append(0.5)

    # Personality preference compatibility
    if a.personality is not None and b.personality is not None:
        scores.append(a.personality.compatibility_score(b.personality))

    return min(1.0, sum(scores) / len(scores))


def get_or_create_friendship(
    friendships: dict[tuple[int, int], Friendship], a: Student, b: Student
) -> Friendship:
    """Get or create the friendship between two students."""
    key = (min(a.student_id, b.student_id), max(a.student_id, b.student_id))
    if key not in friendships:
        friendships[key] = Friendship(student_id1=key[0], student_id2=key[1])
    return friendships[key]


def _romance_interest_compatible(a: Student, b: Student) -> bool:
    """True if both students' romance interests are mutually compatible."""
    if a.personality is None or b.personality is None:
        return False

    from .models import Gender
    _GENDER_MAP = {
        RomanceInterest.BOYS:       Gender.MALE,
        RomanceInterest.GIRLS:      Gender.FEMALE,
        RomanceInterest.NON_BINARY: Gender.NON_BINARY,
    }

    def interested_in(student: Student, other: Student) -> bool:
        interests = student.personality.romance_interest  # type: ignore[union-attr]
        return any(_GENDER_MAP[ri] == other.gender for ri in interests)

    return interested_in(a, b) and interested_in(b, a)


def get_or_create_romance(
    romances: dict[tuple[int, int], Romance], a: Student, b: Student
) -> Romance:
    """Get or create the Romance object between two students (lower ID first)."""
    key = (min(a.student_id, b.student_id), max(a.student_id, b.student_id))
    if key not in romances:
        romances[key] = Romance(student_id1=key[0], student_id2=key[1])
    return romances[key]


def maybe_romance(
    a: Student, b: Student, rel: Romance, friendship: Friendship | None = None,
    location_boost: float = 1.0,
) -> str | None:
    """Resolve a romantic interaction tick. Updates directed feelings/affinity.

    Returns flavor text or None if nothing notable happened.
    Two paths trigger romance development:
    - Spark: random chance weighted by personality compatibility (any friendship level)
    - Slow burn: triggered when friendship is CLOSE_FRIEND or better
    """
    if not _romance_interest_compatible(a, b):
        return None

    compat = compatibility(a, b)

    # Flirt skill boosts spark chance — average of both students', normalised 0-1
    avg_flirt = (
        a.skills.get(Skill.FLIRT, 0.0) + b.skills.get(Skill.FLIRT, 0.0)
    ) / 200.0  # 0.0–1.0

    # Determine if this tick has a romantic spark for each student independently
    slow_burn = (
        friendship is not None
        and friendship.level >= FriendshipLevel.CLOSE_FRIEND
    )
    base_threshold = 0.15 if slow_burn else 0.05
    # Attractive trait raises spark chance — anyone near them is more likely to catch feelings
    attractive_boost = 1.5 if (has_trait(a, "Attractive") or has_trait(b, "Attractive")) else 1.0
    # Flirt skill can up to double the base threshold; location + attractive stack on top
    spark_threshold = base_threshold * (1.0 + avg_flirt) * location_boost * attractive_boost

    logs = []
    for student, other in ((a, b), (b, a)):
        current = rel.feelings_of(student.student_id)
        if current == RomanceLevel.DATING:
            continue
        # Roll for affinity gain this tick
        if random.random() < spark_threshold * compat:
            gain = int(random.uniform(3, 8) * compat)
            rel.add_affinity(student.student_id, gain)
            # Check for level-up
            next_level = current.next
            threshold = ROMANCE_LEVEL_THRESHOLDS.get(next_level, 999) if next_level else 999
            if next_level and rel.affinity_of(student.student_id) >= threshold:
                rel.set_feelings(student.student_id, next_level)
                if next_level == RomanceLevel.CRUSH:
                    logs.append(f"{student.name} has developed a crush on {other.name}.")
                    add_thought(student.thoughts, thought_crush(other.name))

    # Dating: only happens when BOTH have reached CRUSH and compatibility is high
    if rel.is_mutual_crush and compat > 0.6 and random.random() < 0.1:
        rel.set_feelings(a.student_id, RomanceLevel.DATING)
        rel.set_feelings(b.student_id, RomanceLevel.DATING)
        logs.append(f"{a.name} and {b.name} are officially dating!")
        add_thought(a.thoughts, thought_dating(b.name))
        add_thought(b.thoughts, thought_dating(a.name))

    # Flavor text from templates
    if rel.is_dating:
        templates = TEXT_TEMPLATES.get(RomanceLevel.DATING, [])
        fmt_a, fmt_b = a.name, b.name
    elif rel.is_mutual_crush:
        templates = TEXT_TEMPLATES.get(RomanceLevel.CRUSH, [])
        fmt_a, fmt_b = a.name, b.name
    elif rel.is_unrequited:
        # Put the crusher as {a} so "can't stop thinking about {b}" reads correctly
        templates = TEXT_TEMPLATES.get("unrequited", [])
        crusher = a if rel.feelings_of(a.student_id) > RomanceLevel.PLATONIC else b
        other = b if crusher is a else a
        fmt_a, fmt_b = crusher.name, other.name
    else:
        templates = TEXT_TEMPLATES.get(RomanceLevel.PLATONIC, [])
        fmt_a, fmt_b = a.name, b.name

    if templates:
        logs.append(random.choice(templates).format(a=fmt_a, b=fmt_b))

    result = " ".join(logs) if logs else None
    if result:
        rel.history.append(result)
    return result


def maybe_interact(a: Student, b: Student, rel: Friendship) -> str | None:
    """Resolve a social interaction. Draws a topic and delegates to conversation system."""
    from .conversation import draw_topic, resolve_conversation
    topic = draw_topic(rel.level)
    return resolve_conversation(a, b, rel, topic)
