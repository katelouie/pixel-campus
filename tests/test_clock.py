"""Tests for the game clock."""

from src.sim.clock import GameClock, TICKS_PER_DAY


class TestGameClock:
    def test_initial_state(self):
        c = GameClock()
        assert c.day == 1
        assert c.tick == 0
        assert c.time_str == "8:00 AM"

    def test_advance(self):
        c = GameClock()
        ended = c.advance()
        assert not ended
        assert c.tick == 1
        assert c.time_str == "8:10 AM"

    def test_time_formatting(self):
        c = GameClock()
        c.tick = 24  # 4 hours = 12:00 PM
        assert c.hour == 12
        assert c.time_str == "12:00 PM"

        c.tick = 30  # 5 hours = 1:00 PM
        assert c.time_str == "1:00 PM"

    def test_day_end(self):
        c = GameClock()
        c.tick = TICKS_PER_DAY - 1
        ended = c.advance()
        assert ended
        assert c.is_day_over

    def test_new_day(self):
        c = GameClock()
        c.tick = TICKS_PER_DAY
        c.new_day()
        assert c.day == 2
        assert c.tick == 0

    def test_day_progress(self):
        c = GameClock()
        assert c.day_progress == 0.0
        c.tick = TICKS_PER_DAY // 2
        assert 0.49 < c.day_progress < 0.51
