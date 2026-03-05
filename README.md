# Pixel Campus

A nostalgic pixel-art student life simulator inspired by the Flash-era campus sims of the late 2000s.

Manage students, boost their skills, navigate social drama, and guide them through school events — from homeroom to graduation.

## Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install -e ".[dev]"

# Run the CLI test harness
python -m src.main_cli

# Run tests
pytest
```

## Project Structure

```txt
src/
├── sim/          # Pure simulation logic (no display code)
│   ├── models.py # Student, Room, Relationship dataclasses
│   ├── engine.py # GameState, day simulation, assignment
│   ├── events.py # School events (Prom, Finals, Art Show...)
│   ├── journal.py# Journal entry generation
│   └── social.py # Relationship system, compatibility
├── ui/           # Arcade visual layer (Phase 3+)
├── data/         # Static game data (JSON configs)
├── main_cli.py   # CLI testing harness
└── main_arcade.py# Arcade graphical client
```
