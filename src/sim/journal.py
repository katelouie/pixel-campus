"""Journal system where students write about their feelings.

Reading journals reveals hidden preferences and hints about what a student needs to be happy.
"""

import random
from .models import Mood, Student

TEXT_TEMPLATES: dict[Mood, list] = {
    Mood.HAPPY: [
        "Today was amazing! I'm really getting into {fav_skill}.",
        "Can't stop smiling. {loc} Everything just clicked today.",
        "I think I'm starting to really find my thing here. {fav_skill} feels RIGHT.",
        "Good vibes only today.",
    ],
    Mood.NEUTRAL: [
        "Pretty normal day. {loc} Nothing to write home about.",
        "Meh. I wish I could do more {fav_skill} instead of {dread_skill}.",
        "Going through the motions. Could be worse, could be better.",
        "I guess today was okay? Whatever.",
    ],
    Mood.SAD: [
        "Ugh. Why do I have to do {dread_skill}? It's the WORST.",
        "Feeling really down today. {loc} I just want to be left alone.",
        "Nobody gets me. I wish someone would notice I hate {dread_skill}.",
        "Bad day. Can someone PLEASE just let me do {fav_skill}?",
    ],
    Mood.TIRED: [
        "So... exhausted... can barely write this...",
        "Running on fumes. When do we get a break?",
        "Too tired to think. Too tired to care. Just tired.",
        "Everything is blurry. I need a nap, not more {dread_skill}.",
    ],
}


def generate_journal_entry(student: Student, day: int) -> str:
    """Generate a journal entry reflecting the student's current state."""
    pool = TEXT_TEMPLATES[student.mood]

    if student.location:
        loc = f"Spent time in the {student.location.name}."
    else:
        loc = "Just wandered around campus."

    return random.choice(pool).format(
        fav_skill=student.favorite_skill.value,
        dread_skill=student.dreaded_skill.value,
        loc=loc,
    )
