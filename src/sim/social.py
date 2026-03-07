"""Social system. Relationships, compatability, interactions.

Students who share space build affinity. That affinity crosses number thresholds to
level up relationships
"""

import random
from .models import Friendship, FriendshipLevel, Romance, RomanceLevel, Skill, Student

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
        # TODO: Build out best friend level descriptions
        "{a} and {b} are best friends [PLACEHOLDER]"
    ],
    RomanceLevel.PLATONIC: [
        # TODO: Build out platonic romance level descriptions
        "{a} and {b} are platonic [PLACEHOLDER]"
    ],
    RomanceLevel.CRUSH: [
        "{a} keeps glancing at {b} when they're not looking.",
        "{b} gets flustered when {a} sits next to them.",
        "{a} wrote {b}'s name in their notebook. Classic.",
    ],
    RomanceLevel.DATING: [
        "{a} and {b} are holding hands.",
        "{a} and {b} share headphones, each with one earbud.",
        "{b} left a cute note in {a}'s locker.",
    ],
}


def compatability(a: Student, b: Student) -> float:
    """Preference overlap score (0-100)."""
    if not a.preferences or not b.preferences:
        return 0.5
    total = 0.0
    count = 0
    for skill in a.preferences:
        if skill in b.preferences:
            diff = abs(a.preferences[skill] - b.preferences[skill])
            total += 1.0 - diff
            count += 1
    return total / count if count else 0.5


def get_or_create_friendship(
    friendships: dict[tuple[int, int], Friendship], a: Student, b: Student
) -> Friendship:
    """Get or create the friendship between two students."""
    key = (min(a.student_id, b.student_id), max(a.student_id, b.student_id))
    if key not in friendships:
        friendships[key] = Friendship(student_id1=key[0], student_id2=key[1])
    return friendships[key]


# TODO: Create get_or_create_romances and romance interaction function or just modify
# friendship ones to extend to romances


def maybe_interact(a: Student, b: Student, rel: Friendship) -> str | None:
    """Resolve a social interaction. Updates affinity/level, returns flavor text."""
    compat = compatability(a, b)
    gain = int(random.uniform(2, 6) * compat)
    rel.affinity = min(100, rel.affinity + gain)

    # Check for level-up
    leveled_up = False
    next_level = rel.level.next
    if next_level and rel.affinity > FRIENDSHIP_LEVEL_THRESHOLDS.get(next_level, 999):
        rel.level = next_level
        leveled_up = True

    # Generate text
    templates = TEXT_TEMPLATES.get(rel.level, TEXT_TEMPLATES[FriendshipLevel.STRANGER])
    text = random.choice(templates).format(a=a.name, b=b.name)

    if leveled_up:
        level_name = rel.level.name.lower().replace("_", " ")
        text += f"They're now {level_name}s!"

    rel.history.append(text)
    return text
