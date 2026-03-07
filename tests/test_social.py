"""Tests for the social system."""

import pytest
from src.sim.models import Friendship, FriendshipLevel, Skill, Student
from src.sim.social import compatability, get_or_create_friendship, maybe_interact


@pytest.fixture
def two_students():
    a = Student(name="Alex", student_id=0)
    b = Student(name="Jordan", student_id=1)
    return a, b


class TestCompatability:
    def test_identical_prefs(self, two_students):
        a, b = two_students
        shared = {s: 0.8 for s in Skill}
        a.preferences = shared.copy()
        b.preferences = shared.copy()
        assert compatability(a, b) == pytest.approx(1.0)

    def test_opposite_prefs(self, two_students):
        a, b = two_students
        a.preferences = {s: 0.4 for s in Skill}
        b.preferences = {s: 1.2 for s in Skill}
        assert compatability(a, b) < 0.5


class TestFriendships:
    def test_canonical_key(self, two_students):
        a, b = two_students
        rels: dict = {}
        r1 = get_or_create_friendship(rels, a, b)
        r2 = get_or_create_friendship(rels, b, a)
        assert r1 is r2

    def test_interaction_builds_affinity(self, two_students):
        a, b = two_students
        rel = Friendship(student_id1=0, student_id2=1)
        old = rel.affinity
        maybe_interact(a, b, rel)
        assert rel.affinity >= old
