"""Traits system -- personality modifiers that make each student unique.

Each student has 1-2 traits that modify:
- Need decay rates (how fast needs drain)
- Need satisfaction rates (how much activities fill needs)
- Thought intensity (how strongly events affect mood)
- Skill growth rates (how fast skills improve)
- Grade baselines (starting academic performance)

Traits replace the flat `preferences` dict with named, visible personalities.
"""

from dataclasses import dataclass, field


@dataclass
class Trait:
    """A personality trait that modifies a student's behavior and stats."""

    name: str
    description: str = ""

    # {need_type_str: {"decay_mult": float, "satisfy_mult": float}}
    # decay_mult: multiplier on how fast the need drains (>1 = faster, <1 = slower)
    # satisfy_mult: multiplier on how much activities fill the need
    need_modifiers: dict[str, dict[str, float]] = field(default_factory=dict)

    # {thought_category: multiplier} -- scales mood_effect of thoughts in that category
    # Special keys: "_positive" applies to all positive thoughts, "_negative" to all negative
    thought_modifiers: dict[str, float] = field(default_factory=dict)

    # {skill_str: multiplier} -- scales skill growth rate
    skill_multipliers: dict[str, float] = field(default_factory=dict)

    # {subject_str: offset} -- added to grade baseline at student creation
    grade_baseline_modifiers: dict[str, int] = field(default_factory=dict)

    def get_need_decay_mult(self, need_type_str: str) -> float:
        """Get the decay multiplier for a need type. Returns 1.0 if no modifier."""
        mods = self.need_modifiers.get(need_type_str, {})
        return mods.get("decay_mult", 1.0)

    def get_need_satisfy_mult(self, need_type_str: str) -> float:
        """Get the satisfaction multiplier for a need type. Returns 1.0 if no modifier."""
        mods = self.need_modifiers.get(need_type_str, {})
        return mods.get("satisfy_mult", 1.0)

    def get_skill_mult(self, skill_str: str) -> float:
        """Get the skill growth multiplier. Returns 1.0 if no modifier."""
        return self.skill_multipliers.get(skill_str, 1.0)

    def get_thought_mult(self, category: str, mood_effect: float) -> float:
        """Get the thought mood_effect multiplier for a category.

        Checks category-specific modifier first, then falls back to
        _positive/_negative global modifiers.
        """
        # Category-specific modifier takes priority
        if category in self.thought_modifiers:
            return self.thought_modifiers[category]

        # Fall back to positive/negative global modifiers
        if mood_effect > 0 and "_positive" in self.thought_modifiers:
            return self.thought_modifiers["_positive"]
        if mood_effect < 0 and "_negative" in self.thought_modifiers:
            return self.thought_modifiers["_negative"]

        return 1.0

    def get_grade_baseline_offset(self, subject_str: str) -> int:
        """Get the grade baseline offset for a subject. Returns 0 if no modifier."""
        return self.grade_baseline_modifiers.get(subject_str, 0)


def load_traits_from_json(data: list[dict]) -> list[Trait]:
    """Parse a list of trait dicts (from traits.json) into Trait objects."""
    traits = []
    for entry in data:
        traits.append(
            Trait(
                name=entry["name"],
                description=entry.get("description", ""),
                need_modifiers=entry.get("need_modifiers", {}),
                thought_modifiers=entry.get("thought_modifiers", {}),
                skill_multipliers=entry.get("skill_multipliers", {}),
                grade_baseline_modifiers=entry.get("grade_baseline_modifiers", {}),
            )
        )
    return traits


def combined_need_decay_mult(traits: list[Trait], need_type_str: str) -> float:
    """Combined decay multiplier from all traits. Multiplicative."""
    result = 1.0
    for trait in traits:
        result *= trait.get_need_decay_mult(need_type_str)
    return result


def combined_need_satisfy_mult(traits: list[Trait], need_type_str: str) -> float:
    """Combined satisfaction multiplier from all traits. Multiplicative."""
    result = 1.0
    for trait in traits:
        result *= trait.get_need_satisfy_mult(need_type_str)
    return result


def combined_skill_mult(traits: list[Trait], skill_str: str) -> float:
    """Combined skill growth multiplier from all traits. Multiplicative."""
    result = 1.0
    for trait in traits:
        result *= trait.get_skill_mult(skill_str)
    return result


def combined_thought_mult(
    traits: list[Trait], category: str, mood_effect: float
) -> float:
    """Combined thought multiplier from all traits. Multiplicative."""
    result = 1.0
    for trait in traits:
        result *= trait.get_thought_mult(category, mood_effect)
    return result


def combined_grade_baseline_offset(traits: list[Trait], subject_str: str) -> int:
    """Combined grade baseline offset from all traits. Additive."""
    return sum(t.get_grade_baseline_offset(subject_str) for t in traits)
