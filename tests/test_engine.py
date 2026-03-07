"""Tests for the game engine."""

import pytest
from src.sim.engine import GameState
from src.sim.models import Skill, StudentState


class TestGameStateSetup:
    def test_new_game_creates_students(self):
        state = GameState.new_game(num_students=8)
        assert len(state.students) == 8

    def test_new_game_creates_rooms(self):
        state = GameState.new_game()
        assert len(state.rooms) == 4

    def test_students_start_in_cafeteria(self):
        state = GameState.new_game()
        caf = state.get_room_by_name("Cafeteria")
        for s in state.students:
            assert s.location == caf

    def test_unique_student_ids(self):
        state = GameState.new_game()
        ids = [s.student_id for s in state.students]
        assert len(ids) == len(set(ids))


class TestTicking:
    def test_single_tick(self):
        state = GameState.new_game()
        log = state.tick()
        assert isinstance(log, list)
        assert state.clock.tick == 1

    def test_ten_ticks(self):
        state = GameState.new_game()
        for _ in range(10):
            state.tick()
        assert state.clock.tick == 10

    def test_stats_stay_bounded(self):
        state = GameState.new_game()
        for _ in range(200):
            state.tick()
        for s in state.students:
            assert 0 <= s.mood_value <= 100
            assert 0 <= s.energy <= 100
            for skill_val in s.skills.values():
                assert 0 <= skill_val <= 100


class TestAssignment:
    def test_send_student_starts_travel(self):
        state = GameState.new_game()
        student = state.students[0]
        library = state.get_room_by_name("Library")
        state.assign_student(student, library)
        assert student.state == StudentState.TRAVELING
        assert student.destination == library

    def test_student_arrives_after_travel(self):
        state = GameState.new_game()
        student = state.students[0]
        library = state.get_room_by_name("Library")
        state.assign_student(student, library)
        travel_ticks = student.travel_ticks_left
        for _ in range(travel_ticks + 1):
            state.tick()
        assert student.location == library
        assert student.state != StudentState.TRAVELING


class TestLookups:
    def test_find_student_by_name(self):
        state = GameState.new_game()
        name = state.students[0].name
        assert state.get_student_by_name(name) is not None
        assert state.get_student_by_name(name.upper()) is not None

    def test_find_room_by_name(self):
        state = GameState.new_game()
        assert state.get_room_by_name("library") is not None
        assert state.get_room_by_name("nonexistent") is None
