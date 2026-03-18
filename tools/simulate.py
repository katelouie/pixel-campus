"""Headless simulation harness for tuning Pixel Campus magic numbers.

Runs N games for T days and reports per-day aggregate statistics:
  - Mood trajectory (mean ± stddev)
  - Romance progression (% with crush, % dating)
  - Friendship progression (% of pairs at each level)
  - Grade trajectory (mean per subject)
  - Thought pressure (% of students with critical-need thoughts active)

Run from the project root:
    python -m tools.simulate
    python -m tools.simulate --days 14 --runs 200
    python -m tools.simulate --days 7 --runs 100 --every 1
"""

import argparse
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Allow running from project root as `python -m tools.simulate`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sim.academics import Subject
from src.sim.engine import GameState
from src.sim.models import FriendshipLevel, RomanceLevel
from src.sim.needs import NeedType


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _snapshot(state: GameState, day: int, buckets: dict) -> None:
    """Snapshot all relevant statistics for the current day-end state."""
    students = state.students
    n = len(students)
    if n == 0:
        return

    # --- Mood ---
    moods = [s.mood_value for s in students]
    buckets["mood"][day].extend(moods)

    # --- Needs (raw values) ---
    for need_type in NeedType:
        vals = [s.needs[need_type].value for s in students if need_type in s.needs]
        buckets[f"need_{need_type.value}"][day].extend(vals)

    # --- Critical need pressure: % of students with any critical need thought ---
    critical_labels = {
        "Running on fumes", "So bored...",
        "Feeling really lonely...", "Falling behind on everything",
    }
    critical_count = sum(
        1 for s in students
        if any(t.label in critical_labels for t in s.thoughts)
    )
    buckets["critical_pct"][day].append(critical_count / n * 100)

    # --- Romance ---
    student_ids = {s.student_id for s in students}
    crush_students: set[int] = set()
    dating_students: set[int] = set()
    for (a_id, b_id), rel in state.romances.items():
        for sid in (a_id, b_id):
            if sid not in student_ids:
                continue
            level = rel.feelings_of(sid)
            if level >= RomanceLevel.CRUSH:
                crush_students.add(sid)
            if level >= RomanceLevel.DATING:
                dating_students.add(sid)
    buckets["crush_pct"][day].append(len(crush_students) / n * 100)
    buckets["dating_pct"][day].append(len(dating_students) / n * 100)

    # --- Friendship ---
    pairs = list(state.friendships.values())
    if pairs:
        level_counts = {lvl: 0 for lvl in FriendshipLevel}
        for rel in pairs:
            level_counts[rel.level] += 1
        total_pairs = len(pairs)
        for lvl in FriendshipLevel:
            buckets[f"friendship_{lvl.name}"][day].append(
                level_counts[lvl] / total_pairs * 100
            )
        # Convenience: % of pairs that are FRIEND or better
        friend_plus = sum(
            level_counts[lvl]
            for lvl in (FriendshipLevel.FRIEND, FriendshipLevel.CLOSE_FRIEND, FriendshipLevel.BEST_FRIEND)
        )
        buckets["friend_plus_pct"][day].append(friend_plus / total_pairs * 100)
    else:
        for lvl in FriendshipLevel:
            buckets[f"friendship_{lvl.name}"][day].append(0.0)
        buckets["friend_plus_pct"][day].append(0.0)

    # --- Grades (mean across all students per subject) ---
    for subj in Subject:
        vals = [
            s.grades[subj].value
            for s in students
            if subj in s.grades
        ]
        if vals:
            buckets[f"grade_{subj.value}"][day].extend(vals)

    # --- Skills (mean per skill) ---
    from src.sim.models import Skill
    for skill in Skill:
        vals = [s.skills.get(skill, 0.0) for s in students]
        buckets[f"skill_{skill.value}"][day].extend(vals)


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def run_simulation(t_days: int, n_runs: int, snapshot_every: int = 1) -> dict:
    """Run n_runs games for t_days each, collecting daily snapshots."""
    buckets: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    snapshot_days = set(range(snapshot_every, t_days + 1, snapshot_every))
    snapshot_days.add(t_days)  # always include final day

    for run_i in range(n_runs):
        if (run_i + 1) % max(1, n_runs // 10) == 0:
            print(f"  run {run_i + 1}/{n_runs}...", flush=True)

        state = GameState.new_game()
        for day in range(1, t_days + 1):
            state.run_until_day_end()
            if day in snapshot_days:
                _snapshot(state, day, buckets)

    return buckets


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt(values: list[float], pct: bool = False) -> str:
    if not values:
        return "    —    "
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    suffix = "%" if pct else ""
    return f"{mean:5.1f}{suffix} ±{std:4.1f}"


def _grade_letter(value: float) -> str:
    if value >= 93: return "A"
    if value >= 90: return "A-"
    if value >= 87: return "B+"
    if value >= 83: return "B"
    if value >= 80: return "B-"
    if value >= 77: return "C+"
    if value >= 73: return "C"
    if value >= 70: return "C-"
    if value >= 67: return "D+"
    if value >= 60: return "D"
    return "F"


def print_report(buckets: dict, days: list[int], n_runs: int) -> None:
    print()
    print(f"{'='*72}")
    print(f"  PIXEL CAMPUS SIMULATION REPORT  ({n_runs} runs)")
    print(f"{'='*72}")

    # --- Mood & Need pressure ---
    print()
    print("MOOD & PRESSURE")
    print(f"  {'Day':>4}  {'Mood':^14}  {'Critical%':^12}  {'REST':^12}  {'SOCIAL':^12}")
    print(f"  {'-'*4}  {'-'*14}  {'-'*12}  {'-'*12}  {'-'*12}")
    for day in days:
        mood     = _fmt(buckets["mood"][day])
        crit     = _fmt(buckets["critical_pct"][day], pct=True)
        rest     = _fmt(buckets["need_rest"][day])
        social   = _fmt(buckets["need_social"][day])
        print(f"  {day:>4}  {mood:^14}  {crit:^12}  {rest:^12}  {social:^12}")

    # --- Romance ---
    print()
    print("ROMANCE")
    print(f"  {'Day':>4}  {'Crush%':^14}  {'Dating%':^14}")
    print(f"  {'-'*4}  {'-'*14}  {'-'*14}")
    for day in days:
        crush  = _fmt(buckets["crush_pct"][day], pct=True)
        dating = _fmt(buckets["dating_pct"][day], pct=True)
        print(f"  {day:>4}  {crush:^14}  {dating:^14}")

    # --- Friendship ---
    print()
    print("FRIENDSHIP  (% of known pairs at each level)")
    print(f"  {'Day':>4}  {'Stranger':^12}  {'Acquaint':^12}  {'Friend':^12}  {'Close':^12}  {'Best':^12}  {'Friend+%':^12}")
    print(f"  {'-'*4}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}")
    for day in days:
        s = _fmt(buckets[f"friendship_{FriendshipLevel.STRANGER.name}"][day], pct=True)
        a = _fmt(buckets[f"friendship_{FriendshipLevel.ACQUAINTANCE.name}"][day], pct=True)
        f = _fmt(buckets[f"friendship_{FriendshipLevel.FRIEND.name}"][day], pct=True)
        c = _fmt(buckets[f"friendship_{FriendshipLevel.CLOSE_FRIEND.name}"][day], pct=True)
        b = _fmt(buckets[f"friendship_{FriendshipLevel.BEST_FRIEND.name}"][day], pct=True)
        fp = _fmt(buckets["friend_plus_pct"][day], pct=True)
        print(f"  {day:>4}  {s:^12}  {a:^12}  {f:^12}  {c:^12}  {b:^12}  {fp:^12}")

    # --- Grades ---
    print()
    print("GRADES  (mean score → letter)")
    subj_header = "  ".join(f"{s.value[:5]:^14}" for s in Subject)
    print(f"  {'Day':>4}  {subj_header}")
    print(f"  {'-'*4}  " + "  ".join(["-"*14]*len(list(Subject))))
    for day in days:
        row_parts = []
        for subj in Subject:
            vals = buckets[f"grade_{subj.value}"][day]
            if vals:
                mean = statistics.mean(vals)
                std = statistics.stdev(vals) if len(vals) > 1 else 0.0
                row_parts.append(f"{mean:4.1f}({_grade_letter(mean)}) ±{std:3.1f}")
            else:
                row_parts.append("      —      ")
        print(f"  {day:>4}  " + "  ".join(f"{p:^14}" for p in row_parts))

    # --- Skills ---
    print()
    print("SKILLS  (mean across all students)")
    from src.sim.models import Skill
    skill_list = list(Skill)
    skill_header = "  ".join(f"{sk.value[:6]:^12}" for sk in skill_list)
    print(f"  {'Day':>4}  {skill_header}")
    print(f"  {'-'*4}  " + "  ".join(["-"*12]*len(skill_list)))
    for day in days:
        row_parts = [_fmt(buckets[f"skill_{sk.value}"][day]) for sk in skill_list]
        print(f"  {day:>4}  " + "  ".join(f"{p:^12}" for p in row_parts))

    print()
    print(f"{'='*72}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Pixel Campus simulation harness")
    parser.add_argument("--days",  type=int, default=10,  help="Days to simulate (default: 10)")
    parser.add_argument("--runs",  type=int, default=100, help="Number of independent runs (default: 100)")
    parser.add_argument("--every", type=int, default=2,   help="Snapshot every N days (default: 2)")
    args = parser.parse_args()

    print(f"\nRunning {args.runs} simulations × {args.days} days "
          f"(snapshot every {args.every} day(s))...")
    buckets = run_simulation(args.days, args.runs, args.every)

    snapshot_days = sorted(set(
        list(range(args.every, args.days + 1, args.every)) + [args.days]
    ))
    print_report(buckets, snapshot_days, args.runs)


if __name__ == "__main__":
    main()
