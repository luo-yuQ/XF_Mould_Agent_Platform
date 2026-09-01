"""Synchronous application service for the Agent Runtime Core."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from runtime.capabilities import CapabilityRunner
from runtime.loop import DecisionProvider
from runtime.repositories import RuntimeRepository
from runtime.tenant_context import (
    TenantBoundaryError,
    TenantContext,
    ensure_same_tenant,
    require_tenant_context,
)
from schemas.runtime import (
    ActionDecision,
    ActionKind,
    AgentStep,
    AgentStepStatus,
    AuditEvent,
    AuditOperation,
    AuditOutcome,
    CapabilityResult,
    CapabilityResultStatus,
    Run,
    RunStatus,
    StateSnapshot,
    TraceEvent,
    TraceEventKind,
)
from time_utils import utc_now


IdFactory = Callable[[str], str]
Clock = Callable[[], datetime]


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _safe_raw_decision(value: object) -> dict[str, Any]:
    if isinstance(value, ActionDecision):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        normalized = {str(key): item for key, item in value.items()}
        return json.loads(json.dumps(normalized, default=str))
    return {"raw_type": type(value).__name__, "raw_value": str(value)[:1000]}


class RuntimeCoreService:
    """Owns synchronous Core execution and its durable transaction boundaries."""

    def __init__(
        self,
        decision_provider: DecisionProvider,
        capability_runner: CapabilityRunner,
        repository: RuntimeRepository | None = None,
        *,
        max_steps: int = 2,
        clock: Clock = utc_now,
        id_factory: IdFactory = _default_id_factory,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.decision_provider = decision_provider
        self.capability_runner = capability_runner
        self.repository = repository or RuntimeRepository()
        self.max_steps = max_steps
        self.clock = clock
        self.id_factory = id_factory

    @staticmethod
    def _actor_id(context: TenantContext) -> str:
        return context.principal_id or "system"

    @staticmethod
    def _run_contract(record: object) -> Run:
        return Run(
            runtime_run_id=record.runtime_run_id,
            tenant_id=record.tenant_id,
            goal=record.goal,
            status=RunStatus(record.status),
            termination_reason=record.termination_reason,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )

    def _next_trace_sequence(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> int:
        return len(self.repository.list_trace_events(session, context, runtime_run_id)) + 1

    def _next_audit_sequence(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> int:
        return len(self.repository.list_audit_events(session, context, runtime_run_id)) + 1

    def initialize_run(
        self,
        session: Session,
        context: TenantContext,
        goal: str,
        *,
        runtime_run_id: str | None = None,
    ) -> StateSnapshot:
        """Atomically persist the queued Run and its initial State/Trace/Audit."""

        context = require_tenant_context(context)
        run_id = runtime_run_id or self.id_factory("run")
        occurred_at = self.clock()
        run = Run(
            runtime_run_id=run_id,
            tenant_id=context.tenant_id,
            goal=goal,
            status=RunStatus.QUEUED,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        state = StateSnapshot(
            snapshot_id=self.id_factory("state"),
            runtime_run_id=run_id,
            tenant_id=context.tenant_id,
            version=1,
            goal=goal,
            status=RunStatus.QUEUED,
            updated_at=occurred_at,
        )
        trace = TraceEvent(
            event_id=self.id_factory("trace"),
            runtime_run_id=run_id,
            tenant_id=context.tenant_id,
            sequence=1,
            event_type=TraceEventKind.LIFECYCLE,
            payload={"status": RunStatus.QUEUED.value},
            occurred_at=occurred_at,
        )
        audit = AuditEvent(
            audit_id=self.id_factory("audit"),
            runtime_run_id=run_id,
            tenant_id=context.tenant_id,
            sequence=1,
            actor_id=self._actor_id(context),
            operation=AuditOperation.RUN_CREATED,
            target_type="run",
            target_id=run_id,
            outcome=AuditOutcome.SUCCEEDED,
            occurred_at=occurred_at,
        )

        with session.begin():
            self.repository.create_run(session, context, run)
            self.repository.save_state_snapshot(session, context, state)
            self.repository.append_trace_event(session, context, trace)
            self.repository.append_audit_event(session, context, audit)
        return state

    def execute(
        self,
        session: Session,
        context: TenantContext,
        goal: str,
        *,
        runtime_run_id: str | None = None,
    ) -> Run:
        """Create and synchronously execute one bounded Runtime Core Run."""

        context = require_tenant_context(context)
        state = self.initialize_run(
            session, context, goal, runtime_run_id=runtime_run_id
        )

        for step_index in range(1, self.max_steps + 1):
            raw_decision: object | None = None
            try:
                raw_decision = self.decision_provider.decide(state, step_index)
                decision = ActionDecision.model_validate(raw_decision)
                ensure_same_tenant(context, decision.tenant_id)
                if decision.runtime_run_id != state.runtime_run_id:
                    raise ValueError("decision belongs to another Run")
            except Exception as exc:
                return self._fail_run(
                    session,
                    context,
                    state,
                    step_index=step_index,
                    raw_decision=_safe_raw_decision(raw_decision),
                    error_code=(
                        "decision_tenant_mismatch"
                        if isinstance(exc, TenantBoundaryError)
                        else "invalid_action_decision"
                    ),
                    error_message=str(exc),
                )

            if decision.action_kind is ActionKind.INVOKE_CAPABILITY:
                state, terminal = self._invoke_capability_step(
                    session, context, state, step_index, decision
                )
                if terminal:
                    record = self.repository.get_run(
                        session, context, state.runtime_run_id
                    )
                    assert record is not None
                    return self._run_contract(record)
                if step_index == self.max_steps:
                    return self._fail_run(
                        session,
                        context,
                        state,
                        step_index=None,
                        raw_decision={},
                        error_code="max_steps_exhausted",
                        error_message="Run reached max_steps before finish",
                    )
                continue

            if decision.action_kind is ActionKind.FINISH:
                if not state.capability_results:
                    return self._fail_run(
                        session,
                        context,
                        state,
                        step_index=step_index,
                        raw_decision=decision.model_dump(mode="json"),
                        error_code="finish_before_capability",
                        error_message="finish requires one successful capability result",
                    )
                return self._finish_step(session, context, state, step_index, decision)

            return self._fail_run(
                session,
                context,
                state,
                step_index=step_index,
                raw_decision=decision.model_dump(mode="json"),
                error_code="unsupported_action",
                error_message=f"unsupported action: {decision.action_kind}",
            )

        return self._fail_run(
            session,
            context,
            state,
            step_index=None,
            raw_decision={},
            error_code="max_steps_exhausted",
            error_message="Run reached max_steps before finish",
        )

    def _invoke_capability_step(
        self,
        session: Session,
        context: TenantContext,
        state: StateSnapshot,
        step_index: int,
        decision: ActionDecision,
    ) -> tuple[StateSnapshot, bool]:
        occurred_at = self.clock()
        step_id = self.id_factory("step")
        pending = AgentStep(
            step_id=step_id,
            runtime_run_id=state.runtime_run_id,
            tenant_id=state.tenant_id,
            step_index=step_index,
            idempotency_key=decision.idempotency_key,
            input_state_version=state.version,
            decision=decision,
            status=AgentStepStatus.RUNNING,
            started_at=occurred_at,
        )

        try:
            with session.begin():
                run_record = self.repository.get_run(
                    session, context, state.runtime_run_id
                )
                assert run_record is not None
                if RunStatus(run_record.status) is RunStatus.QUEUED:
                    self.repository.update_run_status(
                        session,
                        context,
                        state.runtime_run_id,
                        RunStatus.RUNNING,
                        occurred_at,
                    )
                persisted = self.repository.create_agent_step(
                    session, context, pending
                )
                existing_result = (
                    CapabilityResult.model_validate(persisted.result_json)
                    if persisted.result_json is not None
                    else None
                )
                result = self.capability_runner.invoke(
                    context, decision, existing_result=existing_result
                )
                ensure_same_tenant(context, result.tenant_id)
                if result.runtime_run_id != state.runtime_run_id:
                    raise ValueError("CapabilityResult belongs to another Run")

                succeeded = result.status is CapabilityResultStatus.SUCCEEDED
                terminal_status = (
                    AgentStepStatus.SUCCEEDED if succeeded else AgentStepStatus.FAILED
                )
                next_status = RunStatus.RUNNING if succeeded else RunStatus.FAILED
                termination_reason = None if succeeded else result.error_code
                next_state = StateSnapshot(
                    snapshot_id=self.id_factory("state"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    version=state.version + 1,
                    goal=state.goal,
                    capability_results=[*state.capability_results, result],
                    status=next_status,
                    latest_step_id=step_id,
                    termination_reason=termination_reason,
                    updated_at=occurred_at,
                )
                completed_step = AgentStep(
                    **{
                        **pending.model_dump(),
                        "output_state_version": next_state.version,
                        "capability_result": result,
                        "status": terminal_status,
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                        "finished_at": occurred_at,
                        "duration_ms": result.duration_ms,
                    }
                )
                self.repository.finalize_agent_step(session, context, completed_step)
                self.repository.save_state_snapshot(session, context, next_state)

                trace_sequence = self._next_trace_sequence(
                    session, context, state.runtime_run_id
                )
                self.repository.append_trace_event(
                    session,
                    context,
                    TraceEvent(
                        event_id=self.id_factory("trace"),
                        runtime_run_id=state.runtime_run_id,
                        tenant_id=state.tenant_id,
                        sequence=trace_sequence,
                        event_type=TraceEventKind.ACTION_DECISION,
                        step_id=step_id,
                        payload={
                            "action_kind": decision.action_kind.value,
                            "target": decision.target,
                        },
                        occurred_at=occurred_at,
                    ),
                )
                self.repository.append_trace_event(
                    session,
                    context,
                    TraceEvent(
                        event_id=self.id_factory("trace"),
                        runtime_run_id=state.runtime_run_id,
                        tenant_id=state.tenant_id,
                        sequence=trace_sequence + 2,
                        event_type=TraceEventKind.STATE_UPDATED,
                        step_id=step_id,
                        payload={"state_version": next_state.version},
                        occurred_at=occurred_at,
                    ),
                )
                self.repository.append_trace_event(
                    session,
                    context,
                    TraceEvent(
                        event_id=self.id_factory("trace"),
                        runtime_run_id=state.runtime_run_id,
                        tenant_id=state.tenant_id,
                        sequence=trace_sequence + 1,
                        event_type=TraceEventKind.CAPABILITY_RESULT,
                        step_id=step_id,
                        payload={
                            "status": result.status.value,
                            "execution_id": result.execution_id,
                            "state_version": next_state.version,
                        },
                        occurred_at=occurred_at,
                    ),
                )
                audit_sequence = self._next_audit_sequence(
                    session, context, state.runtime_run_id
                )
                self.repository.append_audit_event(
                    session,
                    context,
                    AuditEvent(
                        audit_id=self.id_factory("audit"),
                        runtime_run_id=state.runtime_run_id,
                        tenant_id=state.tenant_id,
                        sequence=audit_sequence,
                        actor_id=self._actor_id(context),
                        operation=AuditOperation.CAPABILITY_INVOKED,
                        target_type="capability",
                        target_id=decision.target,
                        outcome=(
                            AuditOutcome.SUCCEEDED
                            if succeeded
                            else AuditOutcome.FAILED
                        ),
                        step_id=step_id,
                        metadata={"execution_id": result.execution_id},
                        occurred_at=occurred_at,
                    ),
                )
                if not succeeded:
                    self.repository.update_run_status(
                        session,
                        context,
                        state.runtime_run_id,
                        RunStatus.FAILED,
                        occurred_at,
                        result.error_code,
                    )
                    self.repository.append_trace_event(
                        session,
                        context,
                        TraceEvent(
                            event_id=self.id_factory("trace"),
                            runtime_run_id=state.runtime_run_id,
                            tenant_id=state.tenant_id,
                            sequence=trace_sequence + 3,
                            event_type=TraceEventKind.ERROR,
                            step_id=step_id,
                            payload={"termination_reason": result.error_code},
                            occurred_at=occurred_at,
                        ),
                    )
                return next_state, not succeeded
        except (TenantBoundaryError, ValueError) as exc:
            failed = self._fail_run(
                session,
                context,
                state,
                step_index=step_index,
                raw_decision=decision.model_dump(mode="json"),
                error_code=(
                    "capability_result_tenant_mismatch"
                    if isinstance(exc, TenantBoundaryError)
                    else "invalid_capability_result"
                ),
                error_message=str(exc),
            )
            latest = self.repository.get_latest_state(
                session, context, failed.runtime_run_id
            )
            assert latest is not None
            return StateSnapshot.model_validate(latest.state_json), True

    def _finish_step(
        self,
        session: Session,
        context: TenantContext,
        state: StateSnapshot,
        step_index: int,
        decision: ActionDecision,
    ) -> Run:
        occurred_at = self.clock()
        step_id = self.id_factory("step")
        pending_step = AgentStep(
            step_id=step_id,
            runtime_run_id=state.runtime_run_id,
            tenant_id=state.tenant_id,
            step_index=step_index,
            idempotency_key=decision.idempotency_key,
            input_state_version=state.version,
            decision=decision,
            status=AgentStepStatus.RUNNING,
            started_at=occurred_at,
        )
        completed_step = AgentStep(
            **{
                **pending_step.model_dump(),
                "output_state_version": state.version + 1,
                "status": AgentStepStatus.SUCCEEDED,
                "finished_at": occurred_at,
                "duration_ms": 0,
            }
        )
        final_state = StateSnapshot(
            snapshot_id=self.id_factory("state"),
            runtime_run_id=state.runtime_run_id,
            tenant_id=state.tenant_id,
            version=state.version + 1,
            goal=state.goal,
            capability_results=state.capability_results,
            status=RunStatus.COMPLETED,
            latest_step_id=step_id,
            termination_reason="finish",
            updated_at=occurred_at,
        )

        with session.begin():
            self.repository.create_agent_step(session, context, pending_step)
            self.repository.finalize_agent_step(session, context, completed_step)
            self.repository.save_state_snapshot(session, context, final_state)
            run_record = self.repository.update_run_status(
                session,
                context,
                state.runtime_run_id,
                RunStatus.COMPLETED,
                occurred_at,
                "finish",
            )
            trace_sequence = self._next_trace_sequence(
                session, context, state.runtime_run_id
            )
            self.repository.append_trace_event(
                session,
                context,
                TraceEvent(
                    event_id=self.id_factory("trace"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    sequence=trace_sequence,
                    event_type=TraceEventKind.ACTION_DECISION,
                    step_id=step_id,
                    payload={"action_kind": ActionKind.FINISH.value},
                    occurred_at=occurred_at,
                ),
            )
            self.repository.append_trace_event(
                session,
                context,
                TraceEvent(
                    event_id=self.id_factory("trace"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    sequence=trace_sequence + 1,
                    event_type=TraceEventKind.LIFECYCLE,
                    step_id=step_id,
                    payload={
                        "status": RunStatus.COMPLETED.value,
                        "state_version": final_state.version,
                    },
                    occurred_at=occurred_at,
                ),
            )
            self.repository.append_audit_event(
                session,
                context,
                AuditEvent(
                    audit_id=self.id_factory("audit"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    sequence=self._next_audit_sequence(
                        session, context, state.runtime_run_id
                    ),
                    actor_id=self._actor_id(context),
                    operation=AuditOperation.RUN_COMPLETED,
                    target_type="run",
                    target_id=state.runtime_run_id,
                    outcome=AuditOutcome.SUCCEEDED,
                    step_id=step_id,
                    occurred_at=occurred_at,
                ),
            )
            return self._run_contract(run_record)

    def _fail_run(
        self,
        session: Session,
        context: TenantContext,
        state: StateSnapshot,
        *,
        step_index: int | None,
        raw_decision: dict[str, Any],
        error_code: str,
        error_message: str,
    ) -> Run:
        occurred_at = self.clock()
        step_id = self.id_factory("step") if step_index is not None else None
        final_state = StateSnapshot(
            snapshot_id=self.id_factory("state"),
            runtime_run_id=state.runtime_run_id,
            tenant_id=state.tenant_id,
            version=state.version + 1,
            goal=state.goal,
            capability_results=state.capability_results,
            status=RunStatus.FAILED,
            latest_step_id=step_id or state.latest_step_id,
            termination_reason=error_code,
            updated_at=occurred_at,
        )

        with session.begin():
            if step_index is not None:
                raw_key = raw_decision.get("idempotency_key")
                idempotency_key = (
                    str(raw_key)
                    if isinstance(raw_key, str) and raw_key.strip()
                    else f"{state.runtime_run_id}-step-{step_index}-rejected"
                )
                assert step_id is not None
                self.repository.create_rejected_agent_step(
                    session,
                    context,
                    step_id=step_id,
                    runtime_run_id=state.runtime_run_id,
                    step_index=step_index,
                    idempotency_key=idempotency_key,
                    input_state_version=state.version,
                    raw_decision=raw_decision,
                    error_code=error_code,
                    error_message=error_message,
                    occurred_at=occurred_at,
                )
            self.repository.save_state_snapshot(session, context, final_state)
            run_record = self.repository.update_run_status(
                session,
                context,
                state.runtime_run_id,
                RunStatus.FAILED,
                occurred_at,
                error_code,
            )
            self.repository.append_trace_event(
                session,
                context,
                TraceEvent(
                    event_id=self.id_factory("trace"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    sequence=self._next_trace_sequence(
                        session, context, state.runtime_run_id
                    ),
                    event_type=TraceEventKind.ERROR,
                    step_id=step_id,
                    payload={
                        "error_code": error_code,
                        "error_message": error_message[:1000],
                    },
                    occurred_at=occurred_at,
                ),
            )
            self.repository.append_audit_event(
                session,
                context,
                AuditEvent(
                    audit_id=self.id_factory("audit"),
                    runtime_run_id=state.runtime_run_id,
                    tenant_id=state.tenant_id,
                    sequence=self._next_audit_sequence(
                        session, context, state.runtime_run_id
                    ),
                    actor_id=self._actor_id(context),
                    operation=AuditOperation.RUN_FAILED,
                    target_type="run",
                    target_id=state.runtime_run_id,
                    outcome=(
                        AuditOutcome.REJECTED
                        if step_index is not None
                        else AuditOutcome.FAILED
                    ),
                    step_id=step_id,
                    metadata={"error_code": error_code},
                    occurred_at=occurred_at,
                ),
            )
            return self._run_contract(run_record)
