"""Journal system where students write about their feelings.

Reading journals reveals hidden preferences and hints about what a student needs to be happy.
If a student has active thoughts, the journal entry is driven by the strongest thought.
Otherwise, falls back to mood-based templates.
"""

import random
from .models import Mood, Student

TEXT_TEMPLATES: dict[Mood, list] = {
    Mood.HAPPY: [
        "Today was amazing! I'm really getting into {fav_skill}.",
        "Can't stop smiling. {loc} Everything just clicked today.",
        "I think I'm starting to really find my thing here. {fav_skill} feels RIGHT.",
        "Good vibes only today.",
        "I love days like this. {loc} More of this please.",
        "Honestly feeling myself today. {fav_skill} is my whole personality at this point.",
        "Everything just felt easy today. I don't know, I'm just happy.",
        "Had the best conversation at lunch. This place is growing on me.",
        "{loc} I came in dreading {dread_skill} and somehow still ended up smiling.",
        "Okay I'm not going to overthink it. Today was just a good day.",
    ],
    Mood.NEUTRAL: [
        "Pretty normal day. {loc} Nothing to write home about.",
        "Meh. I wish I could do more {fav_skill} instead of {dread_skill}.",
        "Going through the motions. Could be worse, could be better.",
        "I guess today was okay? Whatever.",
        "{loc} Fine. Everything is fine.",
        "Not much to say. Did stuff, ate lunch, here I am.",
        "I keep waiting for something to happen. {loc}",
        "Feeling kind of invisible today. Not bad, just... there.",
        "I need to figure out what I actually want. {dread_skill} is definitely not it.",
        "Some days you're just... in the middle of everything and nothing.",
    ],
    Mood.SAD: [
        "Ugh. Why do I have to do {dread_skill}? It's the WORST.",
        "Feeling really down today. {loc} I just want to be left alone.",
        "Nobody gets me. I wish someone would notice I hate {dread_skill}.",
        "Bad day. Can someone PLEASE just let me do {fav_skill}?",
        "I don't know. Everything just felt off today.",
        "{loc} I was hoping things would be different but whatever.",
        "I sat alone at lunch and I don't really want to talk about it.",
        "I keep thinking about how much I miss doing {fav_skill} properly.",
        "Why is {dread_skill} always the thing they make me do? It's exhausting.",
        "Hard to explain. I'm just sad. Nothing happened. I'm just sad.",
    ],
    Mood.TIRED: [
        "So... exhausted... can barely write this...",
        "Running on fumes. When do we get a break?",
        "Too tired to think. Too tired to care. Just tired.",
        "Everything is blurry. I need a nap, not more {dread_skill}.",
        "My body hurts and my brain is gone. {loc} I survived, barely.",
        "I think I'm the only person here who is actually this tired.",
        "Could not tell you what happened today. All I know is I'm tired.",
        "Please. Just one good night of sleep. That's all I'm asking.",
        "I tried to focus on {fav_skill} but I couldn't even manage that today.",
        "Zero thoughts. Head empty. Bed please.",
    ],
}

# Templates driven by thought categories -- used when a strong thought is active
THOUGHT_JOURNAL_TEMPLATES: dict[str, list[str]] = {
    "event": [
        "Can't stop thinking about the {thought}.",
        "The {thought} is still on my mind.",
        "I keep replaying the {thought}. Over and over.",
        "After the {thought} I don't know how to feel. Just sitting with it.",
    ],
    "social": [
        "{thought}. I'm still smiling about it.",
        "Thinking about {thought}.",
        "{thought} I didn't expect today to go like that.",
        "Something shifted today. {thought}",
        "{thought} I haven't felt this way in a while.",
        "I couldn't focus on anything because I kept thinking — {thought}",
    ],
    "academic": [
        "{thought} School stuff is really on my mind.",
        "Report cards came back... {thought}",
        "{thought} I need to figure out a plan.",
        "{thought} It's stressing me out more than I want to admit.",
        "I've been trying not to spiral but... {thought}",
    ],
    "activity": [
        "{thought} It's the little things.",
        "{thought}",
        "{thought} I didn't expect to care this much.",
        "Something clicked today. {thought}",
        "{thought} I want more days like this.",
    ],
    "rest": [
        "{thought} My body is telling me something.",
        "{thought}",
        "{thought} I need to actually take care of myself.",
        "I keep pushing through when I should probably just stop. {thought}",
    ],
    "fun": [
        "{thought} I need to actually do something fun.",
        "{thought} This place gets so monotonous sometimes.",
        "{thought} When was the last time I actually laughed?",
    ],
}

# Personality-flavor snippets that can be injected into mood-based entries
_ZODIAC_MOOD_TAGS: dict[str, list[str]] = {
    "aries":       ["I want to DO something, not just sit here."],
    "taurus":      ["I just want things to stay the same for five minutes."],
    "gemini":      ["I keep starting things and not finishing them."],
    "cancer":      ["I need to feel like I'm somewhere safe."],
    "leo":         ["I want to matter to someone today."],
    "virgo":       ["I made a list. It helped a little."],
    "libra":       ["I keep going back and forth and can't decide anything."],
    "scorpio":     ["I notice everything. Too much, maybe."],
    "sagittarius": ["I feel cooped up. I want to go somewhere."],
    "capricorn":   ["If I can just stay on track, everything will be fine."],
    "aquarius":    ["Sometimes I feel like nobody here thinks like I do."],
    "pisces":      ["I got lost in my head again today."],
}


def _personality_flavor(student: Student) -> str | None:
    """Return a personality-specific flavor line, or None."""
    if not student.personality:
        return None
    zodiac = student.personality.zodiac.value
    tags = _ZODIAC_MOOD_TAGS.get(zodiac, [])
    return random.choice(tags) if tags and random.random() < 0.4 else None


def generate_journal_entry(student: Student, day: int) -> str:
    """Generate a journal entry reflecting the student's current state.

    If the student has active thoughts, picks the strongest one and writes about it.
    Otherwise, falls back to mood-based templates, occasionally flavored with
    personality details.
    """
    # Try thought-driven entry first
    if student.thoughts:
        strongest = max(student.thoughts, key=lambda t: abs(t.mood_effect))
        templates = THOUGHT_JOURNAL_TEMPLATES.get(strongest.category)
        if templates:
            entry = random.choice(templates).format(thought=strongest.label)
            flavor = _personality_flavor(student)
            if flavor:
                entry = f"{entry} {flavor}"
            return entry

    # Fallback: mood-based entry
    pool = TEXT_TEMPLATES[student.mood]

    if student.location:
        loc = f"Spent time in the {student.location.name}."
    else:
        loc = "Just wandered around campus."

    entry = random.choice(pool).format(
        fav_skill=student.favorite_skill.value,
        dread_skill=student.dreaded_skill.value,
        loc=loc,
    )

    flavor = _personality_flavor(student)
    if flavor:
        entry = f"{entry} {flavor}"

    return entry
