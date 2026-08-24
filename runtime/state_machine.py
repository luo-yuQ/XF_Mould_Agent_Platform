"""Run lifecycle transitions shared by API and worker code."""

from __future__ import annotations

from schemas.runtime import RunStatus


class InvalidRunTransition(ValueError):
    """Raised when a Run status transition is not part of the Runtime contract."""


_ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_FOR_USER,
            RunStatus.WAITING_FOR_APPROVAL,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.WAITING_FOR_USER: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.WAITING_FOR_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.TIMED_OUT: frozenset(),
}

_TERMINAL_STATES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }
)


class RunStateMachine:
    """Pure transition rules; persistence belongs to a later Runtime slice."""

    @staticmethod
    def is_terminal(status: RunStatus | str) -> bool:
        return RunStatus(status) in _TERMINAL_STATES

    @staticmethod
    def can_transition(current: RunStatus | str, target: RunStatus | str) -> bool:
        current_status = RunStatus(current)
        target_status = RunStatus(target)
        if current_status == target_status:
            return RunStateMachine.is_terminal(current_status)
        return target_status in _ALLOWED_TRANSITIONS[current_status]

    @staticmethod
    def transition(current: RunStatus | str, target: RunStatus | str) -> RunStatus:
        current_status = RunStatus(current)
        target_status = RunStatus(target)
        if not RunStateMachine.can_transition(current_status, target_status):
            raise InvalidRunTransition(
                f"cannot transition Run from {current_status.value} to {target_status.value}"
            )
        return target_status
