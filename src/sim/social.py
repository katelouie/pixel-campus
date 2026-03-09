"""Social system. Relationships, compatibility, interactions.

Students who share space build affinity. That affinity crosses number thresholds to
level up relationships
"""

import random
from .models import Friendship, FriendshipLevel, Romance, RomanceLevel, Skill, Student
from .thoughts import add_thought, thought_best_friend, thought_friendship_levelup

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
    """Compatibility score based on shared traits (0.3 to 1.0).

    Students with the same trait get a compatibility boost.
    Students with no traits get a neutral 0.5.
    """
    if not a.traits and not b.traits:
        return 0.5

    a_trait_names = {t.name for t in a.traits}
    b_trait_names = {t.name for t in b.traits}

    # Shared traits boost compatibility
    shared = a_trait_names & b_trait_names
    all_traits = a_trait_names | b_trait_names

    if not all_traits:
        return 0.5

    # Base compatibility + bonus for shared traits
    base = 0.4
    shared_bonus = len(shared) / len(all_traits) * 0.6
    return min(1.0, base + shared_bonus)


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
    compat = compatibility(a, b)
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
        text += f" They're now {level_name}s!"

        # Add thoughts for both students
        if rel.level == FriendshipLevel.BEST_FRIEND:
            add_thought(a.thoughts, thought_best_friend(b.name))
            add_thought(b.thoughts, thought_best_friend(a.name))
        else:
            add_thought(a.thoughts, thought_friendship_levelup(b.name))
            add_thought(b.thoughts, thought_friendship_levelup(a.name))

    rel.history.append(text)
    return text
