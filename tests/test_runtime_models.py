from sqlalchemy import UniqueConstraint

from models.base import Base
from models.runtime import RuntimeAgentStep, RuntimeAuditEvent


def test_runtime_metadata_contains_exactly_five_core_tables():
    runtime_tables = {
        name for name in Base.metadata.tables if name.startswith("runtime_")
    }
    assert runtime_tables == {
        "runtime_runs",
        "runtime_state_snapshots",
        "runtime_agent_steps",
        "runtime_trace_events",
        "runtime_audit_events",
    }


def test_agent_step_has_run_order_and_idempotency_uniqueness():
    names = {
        constraint.name
        for constraint in RuntimeAgentStep.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_runtime_agent_steps_run_index" in names
    assert "uq_runtime_agent_steps_run_idempotency" in names


def test_audit_event_is_not_the_business_audit_run_table():
    assert RuntimeAuditEvent.__tablename__ == "runtime_audit_events"
    assert RuntimeAuditEvent.__tablename__ != "audit_runs"
