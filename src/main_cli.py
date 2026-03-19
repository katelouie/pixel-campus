"""Pixel Campus CLI Testing Harness

Run with: python -m src.main_cli
"""

from src.sim.engine import GameState
from src.sim.models import StudentState, FriendshipLevel


# -------------------------------------------------------------------
# Display helpers
# -------------------------------------------------------------------


def show_status(state: GameState) -> None:
    """Print all students and their current state."""
    print(
        f"Day {state.clock.day} | {state.clock.time_str} "
        f"| Tick {state.clock.tick} "
        f"| Points: {state.total_points}/{state.graduation_target}"
    )
    print("  ─" * 30)
    for s in state.students:
        loc = s.location.name if s.location else "???"
        state_str = s.state.value

        # Add context to the state
        if s.state == StudentState.TRAVELING and s.destination:
            state_str = f"→ {s.destination.name} ({s.travel_ticks_left}t)"
        elif s.state == StudentState.CHATTING:
            partner = state.get_student_by_id(s.chat_partner_id)
            pname = partner.name if partner else "???"
            state_str = f"chatting w/ {pname} ({s.activity_ticks_left}t)"
        elif s.activity_ticks_left > 0:
            state_str = f"{s.state.value} ({s.activity_ticks_left}t)"

        print(
            f"  {s.mood.icon} {s.name:<8} "
            f"| mood:{s.mood_value:>3.0f} nrg:{s.energy:>3.0f} "
            f"| {loc:<10} | {state_str}"
        )


def show_rooms(state: GameState) -> None:
    """Show rooms and their occupants."""
    print()
    for r in state.rooms:
        occupants = [s.name for s in state.students if s.location == r]
        names = ", ".join(occupants) if occupants else "(empty)"
        print(
            f"  {r.name:<12} [{len(occupants)}/{r.capacity}] "
            f"({r.skill_boost.value}) — {names}"
        )


def show_skills(state: GameState) -> None:
    """Show all students' skill levels."""
    print()
    for s in state.students:
        skills = " | ".join(
            f"{sk.value[:4]}: {lv:>5.1f}" for sk, lv in s.skills.items()
        )
        fav = s.favorite_skill.value
        dread = s.dreaded_skill.value
        print(f"  {s.name:<8}: {skills}  (♥ {fav}, ✗ {dread})")


def show_journal(state: GameState, name: str) -> None:
    """Print a student's journal entries."""
    student = state.get_student_by_name(name)
    if not student:
        print(f"No student named '{name}'.")
        return
    if not student.journal:
        print(f"{student.name}'s journal is empty.")
        return
    print(f"{student.name}'s Journal:")
    for entry in student.journal[-8:]:
        print(f"    Day {entry.day} — {entry.period_label}: {entry.text}")


def show_friendships(state: GameState) -> None:
    """Show all non-stranger friendships."""
    print()
    found = False
    for (a_id, b_id), rel in state.friendships.items():
        if rel.level != FriendshipLevel.STRANGER:
            a = state.get_student_by_id(a_id)
            b = state.get_student_by_id(b_id)
            if a and b:
                lvl = rel.level.name.replace("_", " ").title()
                print(f"  {a.name} & {b.name}: {lvl} (affinity: {rel.affinity})")
                found = True
    if not found:
        print("  Everyone's still strangers. Get them in rooms together!")


def show_help() -> None:
    print("""
  ── Time ──────────────────────────────────────
  t / tick          Advance 1 tick (~10 min)
  t5 / tick 5       Advance 5 ticks
  hour              Advance 6 ticks (1 hour)
  day               Skip to end of day
  pause / unpause   Toggle auto-advance

  ── Info ──────────────────────────────────────
  s / status        Show all students
  r / rooms         Show rooms + occupants
  sk / skills       Show skill levels
  j NAME            Read student's journal
  rels              Show relationships

  ── Actions ───────────────────────────────────
  send NAME ROOM    Send student to a room
  free NAME         Stop student's current activity

  ── Game ──────────────────────────────────────
  save FILENAME     Save game
  load FILENAME     Load game
  help / h          This message
  quit / q          Exit
    """)


# -------------------------------------------------------------------
# Main loop
# -------------------------------------------------------------------


def main() -> None:
    print("=" * 52)
    print("  🏫 PIXEL CAMPUS — CLI Testing Harness")
    print("=" * 52)

    state = GameState.new_game()
    print(f"\n  New game! {len(state.students)} students, Day 1.")
    print(f"  Goal: {state.graduation_target} points to graduate.")
    print("  Type 'help' for commands.\n")
    show_status(state)

    while True:
        try:
            raw = input(f"\n[Day {state.clock.day} {state.clock.time_str}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        # ── Time ──
        if cmd in ("t", "tick"):
            n = 1
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                except ValueError:
                    # Handle "t5" format
                    try:
                        n = int(cmd[1:]) if len(cmd) > 1 else 1
                    except ValueError:
                        n = 1
            elif len(cmd) > 1:
                # Handle "t5" format
                try:
                    n = int(cmd[1:])
                except ValueError:
                    n = 1

            for _ in range(n):
                log = state.tick()
                for msg in log:
                    print(f"  {msg}")
                if state.total_points >= state.graduation_target:
                    print("\n  🎓🎉 GRADUATION!")
                    break
            show_status(state)

        elif cmd == "hour":
            for _ in range(6):
                log = state.tick()
                for msg in log:
                    print(f"  {msg}")
            show_status(state)

        elif cmd == "day":
            log = state.run_until_day_end()
            for msg in log:
                print(f"  {msg}")
            show_status(state)

        # ── Info ──
        elif cmd in ("s", "status"):
            show_status(state)

        elif cmd in ("r", "rooms"):
            show_rooms(state)

        elif cmd in ("sk", "skills"):
            show_skills(state)

        elif cmd in ("j", "journal") and len(parts) >= 2:
            show_journal(state, parts[1])

        elif cmd == "rels":
            show_friendships(state)

        # ── Actions ──
        elif cmd == "send" and len(parts) >= 3:
            name = parts[1]
            room_name = " ".join(parts[2:])
            student = state.get_student_by_name(name)
            room = state.get_room_by_name(room_name)
            if not student:
                print(f"  No student named '{name}'.")
            elif not room:
                names = [r.name for r in state.rooms]
                print(f"  No room named '{room_name}'. Rooms: {names}")
            else:
                result = state.assign_student(student, room)
                print(f"  {result}")

        elif cmd == "free" and len(parts) >= 2:
            student = state.get_student_by_name(parts[1])
            if student:
                print(f"  {state.free_student(student)}")
            else:
                print(f"  No student named '{parts[1]}'.")

        # ── Game ──
        elif cmd == "save" and len(parts) >= 2:
            path = f"saves/{parts[1]}.json"
            state.save(path)
            print(f"  Saved to {path}")

        elif cmd == "load" and len(parts) >= 2:
            path = f"saves/{parts[1]}.json"
            try:
                state = GameState.load(path)
                print(f"  Loaded from {path}")
            except FileNotFoundError:
                print(f"  No save file at {path}")

        elif cmd in ("h", "help"):
            show_help()

        elif cmd in ("q", "quit"):
            print("  Goodbye!")
            break

        else:
            print(f"  Unknown: '{raw}'. Type 'help' for commands.")


if __name__ == "__main__":
    main()
