"""Tests for data models."""

import pytest

from src.sim.models import Mood, Room, Skill, Student, StudentState


class TestStudent:
    def test_default_skills(self):
        s = Student(name="Test", student_id=0)
        assert len(s.skills) == len(Skill)
        assert all(v == 0.0 for v in s.skills.values())

    def test_preferences_in_range(self):
        s = Student(name="Test", student_id=0)
        for v in s.preferences.values():
            assert 0.4 <= v <= 1.2

    def test_mood_derivation(self):
        s = Student(name="Test", student_id=0, mood_value=80, energy=50)
        assert s.mood == Mood.HAPPY
        s.mood_value = 50
        assert s.mood == Mood.NEUTRAL
        s.mood_value = 20
        assert s.mood == Mood.SAD
        s.energy = 10
        assert s.mood == Mood.TIRED

    def test_clamp_stats(self):
        s = Student(name="Test", student_id=0)
        s.mood_value = 150
        s.energy = -10
        s.clamp_stats()
        assert s.mood_value == 100
        assert s.energy == 0

    def test_favorite_and_dreaded(self):
        s = Student(name="Test", student_id=0)
        s.preferences = {
            Skill.ACADEMICS: 1.2,
            Skill.ATHLETICS: 0.4,
            Skill.CREATIVITY: 0.8,
            Skill.SOCIAL: 0.9,
        }
        assert s.favorite_skill == Skill.ACADEMICS
        assert s.dreaded_skill == Skill.ATHLETICS
