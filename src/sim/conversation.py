"""Conversation system — topic-driven social interactions.

When students interact socially, a topic is drawn from a pool that expands
with friendship level. Their personalities and traits are compared to
determine outcome (match / neutral / conflict), which drives affinity gains,
mood effects, skill ticks, and thoughts.

Inspired by RimWorld's interaction/opinion system.
"""

import random
from enum import Enum

from .models import Friendship, FriendshipLevel, Skill, Student
from .needs import NeedType, satisfy_need
from .personality import Worldview
from .thoughts import (
    add_thought,
    thought_disagreed_with,
    thought_found_common_ground,
    thought_friendship_levelup,
    thought_best_friend,
    thought_good_conversation,
)

FRIENDSHIP_LEVEL_THRESHOLDS: dict[FriendshipLevel, int] = {
    FriendshipLevel.STRANGER: 0,
    FriendshipLevel.ACQUAINTANCE: 15,
    FriendshipLevel.FRIEND: 35,
    FriendshipLevel.CLOSE_FRIEND: 55,
    FriendshipLevel.BEST_FRIEND: 75,
}


# ------------------------------------------------------------------
# TOPICS
# ------------------------------------------------------------------

class ConversationTopic(Enum):
    MUSIC      = "music"
    MOVIES     = "movies"
    ATHLETICS  = "athletics"
    ART        = "art"
    ACADEMICS  = "academics"
    WORLDVIEW  = "worldview"


# Topics available at each friendship level (cumulative)
_TOPIC_POOL: dict[FriendshipLevel, list[ConversationTopic]] = {
    FriendshipLevel.STRANGER:     [ConversationTopic.MUSIC, ConversationTopic.MOVIES],
    FriendshipLevel.ACQUAINTANCE: [ConversationTopic.MUSIC, ConversationTopic.MOVIES,
                                   ConversationTopic.ATHLETICS, ConversationTopic.ART],
    FriendshipLevel.FRIEND:       [ConversationTopic.MUSIC, ConversationTopic.MOVIES,
                                   ConversationTopic.ATHLETICS, ConversationTopic.ART,
                                   ConversationTopic.ACADEMICS],
    FriendshipLevel.CLOSE_FRIEND: list(ConversationTopic),
    FriendshipLevel.BEST_FRIEND:  list(ConversationTopic),
}


def draw_topic(level: FriendshipLevel) -> ConversationTopic:
    """Draw a random topic appropriate for the given friendship level."""
    pool = _TOPIC_POOL.get(level, _TOPIC_POOL[FriendshipLevel.STRANGER])
    return random.choice(pool)


# ------------------------------------------------------------------
# OUTCOME
# ------------------------------------------------------------------

class ConversationOutcome(Enum):
    MATCH    = "match"
    NEUTRAL  = "neutral"
    CONFLICT = "conflict"


# Worldview ordered from most activist to most apolitical.
# Distance drives outcome — adjacent = neutral, far apart = conflict.
_WORLDVIEW_ORDER = [
    Worldview.ACTIVIST,
    Worldview.PROGRESSIVE,
    Worldview.MODERATE,
    Worldview.TRADITIONAL,
    Worldview.APOLITICAL,
]


def _worldview_outcome(a: Worldview, b: Worldview) -> ConversationOutcome:
    i, j = _WORLDVIEW_ORDER.index(a), _WORLDVIEW_ORDER.index(b)
    dist = abs(i - j)
    if dist == 0:
        return ConversationOutcome.MATCH
    if dist == 1:
        return ConversationOutcome.NEUTRAL
    return ConversationOutcome.CONFLICT


def _skill_outcome(a_val: float, b_val: float) -> ConversationOutcome:
    """Both engaged with the skill area → match; otherwise neutral.

    Skill topics (art, athletics, academics) don't generate conflict —
    you don't argue about whether gym is good, you just either both care
    or you don't.
    """
    if a_val >= 40 and b_val >= 40:
        return ConversationOutcome.MATCH
    return ConversationOutcome.NEUTRAL


def evaluate_topic(
    a: Student, b: Student, topic: ConversationTopic
) -> ConversationOutcome:
    """Compare two students on a topic and return the outcome."""
    if topic == ConversationTopic.MUSIC:
        if a.personality and b.personality:
            return (
                ConversationOutcome.MATCH
                if a.personality.music_genre == b.personality.music_genre
                else ConversationOutcome.NEUTRAL
            )
        return ConversationOutcome.NEUTRAL

    if topic == ConversationTopic.MOVIES:
        if a.personality and b.personality:
            return (
                ConversationOutcome.MATCH
                if a.personality.movie_genre == b.personality.movie_genre
                else ConversationOutcome.NEUTRAL
            )
        return ConversationOutcome.NEUTRAL

    if topic == ConversationTopic.WORLDVIEW:
        if a.personality and b.personality:
            return _worldview_outcome(a.personality.worldview, b.personality.worldview)
        return ConversationOutcome.NEUTRAL

    if topic == ConversationTopic.ATHLETICS:
        return _skill_outcome(
            a.skills.get(Skill.ATHLETICS, 0.0),
            b.skills.get(Skill.ATHLETICS, 0.0),
        )

    if topic == ConversationTopic.ART:
        return _skill_outcome(
            a.skills.get(Skill.CREATIVITY, 0.0),
            b.skills.get(Skill.CREATIVITY, 0.0),
        )

    if topic == ConversationTopic.ACADEMICS:
        return _skill_outcome(
            a.skills.get(Skill.ACADEMICS, 0.0),
            b.skills.get(Skill.ACADEMICS, 0.0),
        )

    return ConversationOutcome.NEUTRAL


# ------------------------------------------------------------------
# FLAVOR TEXT
# ------------------------------------------------------------------

# (topic, outcome) → list of template strings
_TEMPLATES: dict[tuple[ConversationTopic, ConversationOutcome], list[str]] = {
    (ConversationTopic.MUSIC, ConversationOutcome.MATCH): [
        "{a} and {b} discovered they're both obsessed with the same kind of music.",
        "{a} and {b} spent way too long comparing playlists.",
        "{b} finally found someone who gets their music taste.",
    ],
    (ConversationTopic.MUSIC, ConversationOutcome.NEUTRAL): [
        "{a} and {b} compared music tastes — different, but curious.",
        "{b} showed {a} an artist they'd never heard of.",
        "{a} and {b} talked about music. Total opposite tastes.",
    ],
    (ConversationTopic.MOVIES, ConversationOutcome.MATCH): [
        "{a} and {b} bonded over their love of the same kind of movies.",
        "{a} and {b} have already planned a movie night.",
        "{b} quoted a film and {a} immediately knew exactly which one.",
    ],
    (ConversationTopic.MOVIES, ConversationOutcome.NEUTRAL): [
        "{a} recommended a movie to {b}. {b} seemed skeptical.",
        "{a} and {b} debated their favorite films.",
        "{b} can't believe {a} has never seen that movie.",
    ],
    (ConversationTopic.WORLDVIEW, ConversationOutcome.MATCH): [
        "{a} and {b} found they see the world a lot alike.",
        "{a} and {b} had one of those conversations that just keeps going.",
        "{b} said exactly what {a} was thinking.",
    ],
    (ConversationTopic.WORLDVIEW, ConversationOutcome.NEUTRAL): [
        "{a} and {b} talked about how things are. Neither fully agreed.",
        "{a} and {b} had a thoughtful disagreement about something.",
        "{b} made {a} think about things a little differently.",
    ],
    (ConversationTopic.WORLDVIEW, ConversationOutcome.CONFLICT): [
        "{a} and {b} got into it a little.",
        "{a} and {b} don't exactly see eye to eye on things.",
        "{b} said something that {a} really didn't agree with.",
        "{a} and {b} had a heated back-and-forth. Things got a little tense.",
    ],
    (ConversationTopic.ATHLETICS, ConversationOutcome.MATCH): [
        "{a} and {b} bonded over sports.",
        "{a} challenged {b} to a race. {b} accepted immediately.",
        "{a} and {b} talked trash about the other team.",
    ],
    (ConversationTopic.ATHLETICS, ConversationOutcome.NEUTRAL): [
        "{a} tried to talk sports with {b}. {b} was politely uninterested.",
        "{a} and {b} talked about gym class.",
    ],
    (ConversationTopic.ART, ConversationOutcome.MATCH): [
        "{a} and {b} discovered a shared love of making things.",
        "{a} showed {b} something they'd been working on. {b} was genuinely into it.",
        "{a} and {b} talked art for way longer than expected.",
    ],
    (ConversationTopic.ART, ConversationOutcome.NEUTRAL): [
        "{b} showed {a} some art. {a} appreciated it, more or less.",
        "{a} and {b} talked about the art class.",
    ],
    (ConversationTopic.ACADEMICS, ConversationOutcome.MATCH): [
        "{a} and {b} are both academic minded — they ended up studying together.",
        "{a} and {b} spent their break talking about class.",
        "{b} asked {a} to explain something. They both got more into it than expected.",
    ],
    (ConversationTopic.ACADEMICS, ConversationOutcome.NEUTRAL): [
        "{a} and {b} talked about homework. Neither was very enthusiastic.",
        "{b} asked {a} about the test. {a} shrugged.",
    ],
}


def _make_text(
    a: Student, b: Student, topic: ConversationTopic, outcome: ConversationOutcome
) -> str:
    key = (topic, outcome)
    templates = _TEMPLATES.get(key, ["{a} and {b} talked about something."])
    return random.choice(templates).format(a=a.name, b=b.name)


# ------------------------------------------------------------------
# RESOLVE
# ------------------------------------------------------------------

def resolve_conversation(
    a: Student, b: Student, rel: Friendship, topic: ConversationTopic
) -> str:
    """Resolve a topic-driven conversation between two students.

    Updates affinity, skills, social need, and thoughts. Returns flavor text.
    """
    # First meeting: talking to anyone moves you from Stranger to Acquaintance immediately
    if rel.level == FriendshipLevel.STRANGER:
        rel.level = FriendshipLevel.ACQUAINTANCE

    outcome = evaluate_topic(a, b, topic)

    # Affinity gain
    gain = {
        ConversationOutcome.MATCH:    random.randint(4, 8),
        ConversationOutcome.NEUTRAL:  random.randint(2, 4),
        ConversationOutcome.CONFLICT: random.randint(0, 1),
    }[outcome]
    rel.affinity = min(100, rel.affinity + gain)

    # Social skill tick for both
    for student in (a, b):
        student.skills[Skill.SOCIAL] = min(
            100.0, student.skills.get(Skill.SOCIAL, 0.0) + random.uniform(0.3, 0.8)
        )

    # Satisfy SOCIAL need
    social_amount = {
        ConversationOutcome.MATCH:    random.uniform(6.0, 10.0),
        ConversationOutcome.NEUTRAL:  random.uniform(3.0, 6.0),
        ConversationOutcome.CONFLICT: random.uniform(0.0, 2.0),
    }[outcome]
    for student in (a, b):
        satisfy_need(student.needs, NeedType.SOCIAL, social_amount)

    # Check for friendship level-up
    leveled_up = False
    next_level = rel.level.next
    if next_level and rel.affinity > FRIENDSHIP_LEVEL_THRESHOLDS.get(next_level, 999):
        rel.level = next_level
        leveled_up = True

    # Generate thoughts
    if outcome == ConversationOutcome.MATCH:
        if topic == ConversationTopic.WORLDVIEW:
            add_thought(a.thoughts, thought_found_common_ground(b.name))
            add_thought(b.thoughts, thought_found_common_ground(a.name))
        else:
            add_thought(a.thoughts, thought_good_conversation(b.name))
            add_thought(b.thoughts, thought_good_conversation(a.name))
    elif outcome == ConversationOutcome.CONFLICT:
        add_thought(a.thoughts, thought_disagreed_with(b.name))
        add_thought(b.thoughts, thought_disagreed_with(a.name))

    if leveled_up:
        if rel.level == FriendshipLevel.BEST_FRIEND:
            add_thought(a.thoughts, thought_best_friend(b.name))
            add_thought(b.thoughts, thought_best_friend(a.name))
        else:
            add_thought(a.thoughts, thought_friendship_levelup(b.name))
            add_thought(b.thoughts, thought_friendship_levelup(a.name))

    # Build flavor text
    text = _make_text(a, b, topic, outcome)
    if leveled_up:
        level_name = rel.level.name.lower().replace("_", " ")
        text += f" They're now {level_name}s!"

    rel.history.append(text)
    return text
