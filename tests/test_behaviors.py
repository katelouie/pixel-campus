"""Tests for the student behavior state machine."""

from src.sim.engine import GameState
from src.sim.behaviors import send_to_room, process_student
from src.sim.models import StudentState, Skill


class TestTravel:
    def test_send_starts_traveling(self):
        state = GameState.new_game()
        student = state.students[0]
        gym = state.get_room_by_name("Gym")
        send_to_room(student, gym)
        assert student.state == StudentState.TRAVELING
        assert student.destination == gym
        assert student.travel_ticks_left > 0

    def test_arrival_starts_activity(self):
        state = GameState.new_game()
        student = state.students[0]
        gym = state.get_room_by_name("Gym")
        send_to_room(student, gym)
        # Tick until arrived
        for _ in range(student.travel_ticks_left + 1):
            process_student(student, state)
        assert student.location == gym
        assert student.state == StudentState.EXERCISING


class TestActivity:
    def test_activity_builds_skill(self):
        state = GameState.new_game()
        student = state.students[0]
        library = state.get_room_by_name("Library")
        student.location = library
        student.state = StudentState.STUDYING
        student.activity_ticks_left = 5
        old_skill = student.skills[Skill.ACADEMICS]
        for _ in range(3):
            process_student(student, state)
        assert student.skills[Skill.ACADEMICS] > old_skill

    def test_activity_ends(self):
        state = GameState.new_game()
        student = state.students[0]
        library = state.get_room_by_name("Library")
        student.location = library
        student.state = StudentState.STUDYING
        student.activity_ticks_left = 2
        process_student(student, state)  # ticks_left = 1
        process_student(student, state)  # ticks_left = 0 → IDLE
        assert student.state == StudentState.IDLE
