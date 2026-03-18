"""Game event bus — pub/sub system for simulation events.

Emit sites announce what happened. Subscribers handle consequences.
Neither side needs to know about the other.

Named game_events.py to distinguish from events.py (school events like
Basketball Game, Art Show, etc.).
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class GameEventType(Enum):
    FRIENDSHIP_LEVEL_UP = auto()   # a friendship crossed a level threshold
    ROMANCE_SPARK       = auto()   # a student developed a crush
    ROMANCE_DATING      = auto()   # mutual crush → officially dating
    THOUGHT_ADDED       = auto()   # any thought added to a student's stack
    CHAT_CONFLICT       = auto()   # conversation outcome was CONFLICT
    CHAT_MATCH          = auto()   # conversation outcome was MATCH
    GRADE_FAILED        = auto()   # student received an F on report card
    DAY_ENDED           = auto()   # end of day processed


@dataclass
class GameEvent:
    type: GameEventType
    student_ids: list[int] = field(default_factory=list)  # affected student IDs
    data: dict = field(default_factory=dict)               # event-specific payload


class GameEventBus:
    """Simple synchronous publish/subscribe event bus.

    All handlers run immediately and synchronously when emit() is called.
    No async, no queuing — events resolve before the tick loop continues.
    """

    def __init__(self) -> None:
        self._subscribers: dict[GameEventType, list[Callable[[GameEvent], None]]] = {}

    def subscribe(self, event_type: GameEventType, handler: Callable[[GameEvent], None]) -> None:
        """Register a handler for an event type. Call at startup."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def emit(self, event: GameEvent) -> None:
        """Emit an event. All registered handlers run immediately."""
        for handler in self._subscribers.get(event.type, []):
            handler(event)
