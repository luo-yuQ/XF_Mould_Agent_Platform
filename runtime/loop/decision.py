"""Replaceable next-decision boundary for the Runtime Core."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from schemas.runtime import ActionDecision, StateSnapshot


class DecisionProvider(Protocol):
    """Produces one validated next decision from the current canonical State."""

    def decide(self, state: StateSnapshot, step_index: int) -> ActionDecision:
        """Return the next Core ActionDecision."""


class ScriptedDecisionProvider:
    """Deterministic provider used by the Core vertical slice and tests."""

    def __init__(self, decisions: Iterable[ActionDecision | dict[str, Any]]) -> None:
        self._decisions = list(decisions)
        self.observed_states: list[StateSnapshot] = []
        self.observed_step_indexes: list[int] = []

    def decide(self, state: StateSnapshot, step_index: int) -> ActionDecision:
        self.observed_states.append(state.model_copy(deep=True))
        self.observed_step_indexes.append(step_index)
        offset = len(self.observed_states) - 1
        if offset >= len(self._decisions):
            raise RuntimeError("scripted decision sequence is exhausted")
        return ActionDecision.model_validate(self._decisions[offset])
