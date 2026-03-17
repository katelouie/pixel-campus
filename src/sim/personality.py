"""Student personality attributes for Pixel Campus.

Holds enums for all preference/taste categories, the Personality dataclass,
and a compatibility_score method that scaffolds the future conversation/
friendship-bonus system.
"""

import random
from dataclasses import dataclass
from enum import Enum


class ZodiacSign(Enum):
    ARIES       = "aries"
    TAURUS      = "taurus"
    GEMINI      = "gemini"
    CANCER      = "cancer"
    LEO         = "leo"
    VIRGO       = "virgo"
    LIBRA       = "libra"
    SCORPIO     = "scorpio"
    SAGITTARIUS = "sagittarius"
    CAPRICORN   = "capricorn"
    AQUARIUS    = "aquarius"
    PISCES      = "pisces"


class MusicGenre(Enum):
    POP        = "pop"
    ROCK       = "rock"
    PUNK       = "punk"
    HIP_HOP    = "hip_hop"
    CLASSICAL  = "classical"
    JAZZ       = "jazz"
    ELECTRONIC = "electronic"
    COUNTRY    = "country"
    R_AND_B    = "r_and_b"
    INDIE      = "indie"


class MovieGenre(Enum):
    ACTION      = "action"
    COMEDY      = "comedy"
    ROMANCE     = "romance"
    HORROR      = "horror"
    DOCUMENTARY = "documentary"
    ANIMATION   = "animation"
    THRILLER    = "thriller"
    SCI_FI      = "sci_fi"


class TimeOfDay(Enum):
    MORNING   = "morning"
    AFTERNOON = "afternoon"
    EVENING   = "evening"
    NIGHT     = "night"


class Weather(Enum):
    SUNNY  = "sunny"
    CLOUDY = "cloudy"
    RAIN   = "rain"
    SNOW   = "snow"
    WINDY  = "windy"
    STORM  = "storm"


class RomanceInterest(Enum):
    BOYS       = "boys"
    GIRLS      = "girls"
    NON_BINARY = "non_binary"


class Worldview(Enum):
    """Broad values alignment — intentionally flavor-y rather than partisan."""
    ACTIVIST    = "activist"
    PROGRESSIVE = "progressive"
    MODERATE    = "moderate"
    TRADITIONAL = "traditional"
    APOLITICAL  = "apolitical"


def _random_romance_interests() -> list[RomanceInterest]:
    """Generate a random romance interest list. ~10% nobody, rest 1-3 genders."""
    if random.random() < 0.10:
        return []
    all_ri = list(RomanceInterest)
    k = random.choices([1, 2, 3], weights=[65, 28, 7])[0]
    return random.sample(all_ri, k=k)


def fmt_romance_interests(interests: list[RomanceInterest]) -> str:
    """Human-readable romance interest string for display."""
    if not interests:
        return "Nobody"
    if len(interests) == len(RomanceInterest):
        return "Everyone"
    return ", ".join(i.value.replace("_", " ").title() for i in interests)


# Signs whose peak birth month falls before the Sep 1 school-year cutoff.
# Students with these signs are the "older" cohort in their grade (base_age + 1).
_OLDER_IN_GRADE: frozenset[ZodiacSign] = frozenset({
    ZodiacSign.CAPRICORN,   # Dec 22 – Jan 19
    ZodiacSign.AQUARIUS,    # Jan 20 – Feb 18
    ZodiacSign.PISCES,      # Feb 19 – Mar 20
    ZodiacSign.ARIES,       # Mar 21 – Apr 19
    ZodiacSign.TAURUS,      # Apr 20 – May 20
    ZodiacSign.GEMINI,      # May 21 – Jun 20
    ZodiacSign.CANCER,      # Jun 21 – Jul 22
    ZodiacSign.LEO,         # Jul 23 – Aug 22
})

# Preferences that are compared for compatibility scoring.
# Romance interest and zodiac are handled separately (not simple equality checks).
_COMPAT_FIELDS = ("music_genre", "movie_genre", "time_of_day", "weather", "worldview")


@dataclass
class Personality:
    """All flavor/preference attributes for a student."""

    zodiac:           ZodiacSign
    music_genre:      MusicGenre
    movie_genre:      MovieGenre
    time_of_day:      TimeOfDay
    weather:          Weather
    romance_interest: list[RomanceInterest]
    worldview:        Worldview

    def age_offset(self) -> int:
        """Returns 1 if this sign is the 'older' cohort in their grade, else 0."""
        return 1 if self.zodiac in _OLDER_IN_GRADE else 0

    def compatibility_score(self, other: "Personality") -> float:
        """Shared-preference score between two students (0.0 – 1.0).

        Used to scaffold friendship/romance bonuses during socializing ticks.
        Each matching preference contributes equally. Romance interest compatibility
        is checked separately (not counted here — handled by the romance system).
        """
        matches = sum(
            getattr(self, f) == getattr(other, f)
            for f in _COMPAT_FIELDS
        )
        return matches / len(_COMPAT_FIELDS)

    @staticmethod
    def random() -> "Personality":
        """Generate a fully randomised personality."""
        return Personality(
            zodiac=random.choice(list(ZodiacSign)),
            music_genre=random.choice(list(MusicGenre)),
            movie_genre=random.choice(list(MovieGenre)),
            time_of_day=random.choice(list(TimeOfDay)),
            weather=random.choice(list(Weather)),
            romance_interest=_random_romance_interests(),
            worldview=random.choice(list(Worldview)),
        )
