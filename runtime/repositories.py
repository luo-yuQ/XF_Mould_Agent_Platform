"""Tenant-scoped persistence operations for the synchronous Runtime Core."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from models.runtime import (
    RuntimeAgentStep,
    RuntimeAuditEvent,
    RuntimeRun,
    RuntimeStateSnapshot,
    RuntimeTraceEvent,
)
from runtime.state_machine import RunStateMachine
from runtime.tenant_context import TenantContext, ensure_same_tenant, require_tenant_context
from schemas.runtime import (
    AgentStep,
    AgentStepStatus,
    AuditEvent,
    Run,
    RunStatus,
    StateSnapshot,
    TraceEvent,
)


class RuntimeRecordNotFound(LookupError):
    """Raised when a tenant-scoped Runtime record does not exist."""


class RuntimePersistenceError(ValueError):
    """Raised when a Runtime write violates ordering or immutability."""


_TERMINAL_STEP_STATUSES = {
    AgentStepStatus.SUCCEEDED,
    AgentStepStatus.REJECTED,
    AgentStepStatus.FAILED,
}


class RuntimeRepository:
    """Repository surface shared by the Core application service and tests."""

    @staticmethod
    def _owned_run(
        session: Session, context: TenantContext, runtime_run_id: str
    ) -> RuntimeRun:
        context = require_tenant_context(context)
        record = session.scalar(
            select(RuntimeRun).where(
                RuntimeRun.runtime_run_id == runtime_run_id,
                RuntimeRun.tenant_id == context.tenant_id,
            )
        )
        if record is None:
            raise RuntimeRecordNotFound("Runtime Run was not found")
        return record

    def create_run(self, session: Session, context: TenantContext, run: Run) -> RuntimeRun:
        ensure_same_tenant(context, run.tenant_id)
        if session.scalar(
            select(RuntimeRun).where(RuntimeRun.runtime_run_id == run.runtime_run_id)
        ) is not None:
            raise RuntimePersistenceError("runtime_run_id already exists")
        record = RuntimeRun(
            runtime_run_id=run.runtime_run_id,
            tenant_id=run.tenant_id,
            goal=run.goal,
            status=run.status.value,
            termination_reason=run.termination_reason,
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
        session.add(record)
        session.flush()
        return record

    def get_run(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> RuntimeRun | None:
        context = require_tenant_context(context)
        return session.scalar(
            select(RuntimeRun).where(
                RuntimeRun.runtime_run_id == runtime_run_id,
                RuntimeRun.tenant_id == context.tenant_id,
            )
        )

    def update_run_status(
        self,
        session: Session,
        context: TenantContext,
        runtime_run_id: str,
        status: RunStatus,
        occurred_at: datetime,
        termination_reason: str | None = None,
    ) -> RuntimeRun:
        record = self._owned_run(session, context, runtime_run_id)
        target = RunStateMachine.transition(record.status, status)
        record.status = target.value
        record.updated_at = occurred_at
        if target is RunStatus.RUNNING and record.started_at is None:
            record.started_at = occurred_at
        if target in {RunStatus.COMPLETED, RunStatus.FAILED}:
            record.finished_at = occurred_at
            record.termination_reason = termination_reason
        session.flush()
        return record

    def save_state_snapshot(
        self, session: Session, context: TenantContext, snapshot: StateSnapshot
    ) -> RuntimeStateSnapshot:
        ensure_same_tenant(context, snapshot.tenant_id)
        self._owned_run(session, context, snapshot.runtime_run_id)
        existing = session.scalar(
            select(RuntimeStateSnapshot).where(
                RuntimeStateSnapshot.runtime_run_id == snapshot.runtime_run_id,
                RuntimeStateSnapshot.version == snapshot.version,
            )
        )
        if existing is not None:
            raise RuntimePersistenceError("State version already exists")
        record = RuntimeStateSnapshot(
            snapshot_id=snapshot.snapshot_id,
            runtime_run_id=snapshot.runtime_run_id,
            tenant_id=snapshot.tenant_id,
            version=snapshot.version,
            status=snapshot.status.value,
            state_json=snapshot.model_dump(mode="json"),
            termination_reason=snapshot.termination_reason,
            created_at=snapshot.updated_at,
        )
        session.add(record)
        session.flush()
        return record

    def get_latest_state(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> RuntimeStateSnapshot | None:
        self._owned_run(session, context, runtime_run_id)
        return session.scalar(
            select(RuntimeStateSnapshot)
            .where(
                RuntimeStateSnapshot.runtime_run_id == runtime_run_id,
                RuntimeStateSnapshot.tenant_id == context.tenant_id,
            )
            .order_by(desc(RuntimeStateSnapshot.version))
            .limit(1)
        )

    def list_state_snapshots(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> list[RuntimeStateSnapshot]:
        self._owned_run(session, context, runtime_run_id)
        return list(
            session.scalars(
                select(RuntimeStateSnapshot)
                .where(
                    RuntimeStateSnapshot.runtime_run_id == runtime_run_id,
                    RuntimeStateSnapshot.tenant_id == context.tenant_id,
                )
                .order_by(RuntimeStateSnapshot.version)
            )
        )

    def create_agent_step(
        self, session: Session, context: TenantContext, step: AgentStep
    ) -> RuntimeAgentStep:
        ensure_same_tenant(context, step.tenant_id)
        self._owned_run(session, context, step.runtime_run_id)
        existing = self.get_agent_step_by_idempotency(
            session, context, step.runtime_run_id, step.idempotency_key
        )
        if existing is not None:
            return existing
        if session.scalar(
            select(RuntimeAgentStep).where(
                RuntimeAgentStep.runtime_run_id == step.runtime_run_id,
                RuntimeAgentStep.step_index == step.step_index,
            )
        ) is not None:
            raise RuntimePersistenceError("AgentStep index already exists")
        record = RuntimeAgentStep(
            step_id=step.step_id,
            runtime_run_id=step.runtime_run_id,
            tenant_id=step.tenant_id,
            step_index=step.step_index,
            idempotency_key=step.idempotency_key,
            input_state_version=step.input_state_version,
            output_state_version=step.output_state_version,
            action_kind=step.decision.action_kind.value,
            target=step.decision.target,
            decision_json=step.decision.model_dump(mode="json"),
            result_json=(
                step.capability_result.model_dump(mode="json")
                if step.capability_result is not None
                else None
            ),
            status=step.status.value,
            error_code=step.error_code,
            error_message=step.error_message,
            started_at=step.started_at,
            finished_at=step.finished_at,
            duration_ms=step.duration_ms,
        )
        session.add(record)
        session.flush()
        return record

    def finalize_agent_step(
        self, session: Session, context: TenantContext, step: AgentStep
    ) -> RuntimeAgentStep:
        ensure_same_tenant(context, step.tenant_id)
        if step.status not in _TERMINAL_STEP_STATUSES:
            raise RuntimePersistenceError("finalized AgentStep must be terminal")
        record = self.get_agent_step_by_idempotency(
            session, context, step.runtime_run_id, step.idempotency_key
        )
        if record is None:
            raise RuntimeRecordNotFound("AgentStep was not found")
        if record.step_id != step.step_id or record.step_index != step.step_index:
            raise RuntimePersistenceError("AgentStep identity does not match idempotency record")
        incoming_result = (
            step.capability_result.model_dump(mode="json")
            if step.capability_result is not None
            else None
        )
        if record.status in {item.value for item in _TERMINAL_STEP_STATUSES}:
            if record.status != step.status.value or record.result_json != incoming_result:
                raise RuntimePersistenceError("completed AgentStep is immutable")
            return record
        record.output_state_version = step.output_state_version
        record.result_json = incoming_result
        record.status = step.status.value
        record.error_code = step.error_code
        record.error_message = step.error_message
        record.started_at = step.started_at or record.started_at
        record.finished_at = step.finished_at
        record.duration_ms = step.duration_ms
        session.flush()
        return record

    def create_rejected_agent_step(
        self,
        session: Session,
        context: TenantContext,
        *,
        step_id: str,
        runtime_run_id: str,
        step_index: int,
        idempotency_key: str,
        input_state_version: int,
        raw_decision: dict[str, Any],
        error_code: str,
        error_message: str,
        occurred_at: datetime,
    ) -> RuntimeAgentStep:
        """Persist an attempted step whose raw decision failed schema validation."""

        context = require_tenant_context(context)
        self._owned_run(session, context, runtime_run_id)
        existing = self.get_agent_step_by_idempotency(
            session, context, runtime_run_id, idempotency_key
        )
        if existing is not None:
            return existing
        action_kind = str(raw_decision.get("action_kind", "invalid"))[:64]
        target = str(raw_decision.get("target", ""))[:1000]
        record = RuntimeAgentStep(
            step_id=step_id,
            runtime_run_id=runtime_run_id,
            tenant_id=context.tenant_id,
            step_index=step_index,
            idempotency_key=idempotency_key,
            input_state_version=input_state_version,
            action_kind=action_kind,
            target=target,
            decision_json=raw_decision,
            status=AgentStepStatus.REJECTED.value,
            error_code=error_code,
            error_message=error_message[:1000],
            started_at=occurred_at,
            finished_at=occurred_at,
            duration_ms=0,
        )
        session.add(record)
        session.flush()
        return record

    def get_agent_step_by_idempotency(
        self,
        session: Session,
        context: TenantContext,
        runtime_run_id: str,
        idempotency_key: str,
    ) -> RuntimeAgentStep | None:
        self._owned_run(session, context, runtime_run_id)
        return session.scalar(
            select(RuntimeAgentStep).where(
                RuntimeAgentStep.runtime_run_id == runtime_run_id,
                RuntimeAgentStep.tenant_id == context.tenant_id,
                RuntimeAgentStep.idempotency_key == idempotency_key,
            )
        )

    def list_agent_steps(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> list[RuntimeAgentStep]:
        self._owned_run(session, context, runtime_run_id)
        return list(
            session.scalars(
                select(RuntimeAgentStep)
                .where(
                    RuntimeAgentStep.runtime_run_id == runtime_run_id,
                    RuntimeAgentStep.tenant_id == context.tenant_id,
                )
                .order_by(RuntimeAgentStep.step_index)
            )
        )

    def append_trace_event(
        self, session: Session, context: TenantContext, event: TraceEvent
    ) -> RuntimeTraceEvent:
        ensure_same_tenant(context, event.tenant_id)
        self._owned_run(session, context, event.runtime_run_id)
        if session.scalar(
            select(RuntimeTraceEvent).where(
                RuntimeTraceEvent.runtime_run_id == event.runtime_run_id,
                RuntimeTraceEvent.sequence == event.sequence,
            )
        ) is not None:
            raise RuntimePersistenceError("Trace sequence already exists")
        record = RuntimeTraceEvent(
            event_id=event.event_id,
            runtime_run_id=event.runtime_run_id,
            tenant_id=event.tenant_id,
            sequence=event.sequence,
            event_type=event.event_type.value,
            step_id=event.step_id,
            payload_json=event.payload,
            occurred_at=event.occurred_at,
        )
        session.add(record)
        session.flush()
        return record

    def list_trace_events(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> list[RuntimeTraceEvent]:
        self._owned_run(session, context, runtime_run_id)
        return list(
            session.scalars(
                select(RuntimeTraceEvent)
                .where(
                    RuntimeTraceEvent.runtime_run_id == runtime_run_id,
                    RuntimeTraceEvent.tenant_id == context.tenant_id,
                )
                .order_by(RuntimeTraceEvent.sequence)
            )
        )

    def append_audit_event(
        self, session: Session, context: TenantContext, event: AuditEvent
    ) -> RuntimeAuditEvent:
        ensure_same_tenant(context, event.tenant_id)
        self._owned_run(session, context, event.runtime_run_id)
        if session.scalar(
            select(RuntimeAuditEvent).where(
                RuntimeAuditEvent.runtime_run_id == event.runtime_run_id,
                RuntimeAuditEvent.sequence == event.sequence,
            )
        ) is not None:
            raise RuntimePersistenceError("Audit sequence already exists")
        record = RuntimeAuditEvent(
            audit_id=event.audit_id,
            runtime_run_id=event.runtime_run_id,
            tenant_id=event.tenant_id,
            sequence=event.sequence,
            actor_id=event.actor_id,
            operation=event.operation.value,
            target_type=event.target_type,
            target_id=event.target_id,
            outcome=event.outcome.value,
            step_id=event.step_id,
            metadata_json=event.metadata,
            occurred_at=event.occurred_at,
        )
        session.add(record)
        session.flush()
        return record

    def list_audit_events(
        self, session: Session, context: TenantContext, runtime_run_id: str
    ) -> list[RuntimeAuditEvent]:
        self._owned_run(session, context, runtime_run_id)
        return list(
            session.scalars(
                select(RuntimeAuditEvent)
                .where(
                    RuntimeAuditEvent.runtime_run_id == runtime_run_id,
                    RuntimeAuditEvent.tenant_id == context.tenant_id,
                )
                .order_by(RuntimeAuditEvent.sequence)
            )
        )
