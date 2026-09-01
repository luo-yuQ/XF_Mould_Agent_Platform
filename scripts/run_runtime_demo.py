"""Run the Runtime Core happy path against the configured development PostgreSQL.

This is a development-only smoke-test entry point. It intentionally keeps all
created Runtime records so they can be inspected later in DBeaver.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DATABASE_URL  # noqa: E402
from runtime.capabilities import (  # noqa: E402
    DEMO_CAPABILITY_NAME,
    CapabilityRegistry,
    CapabilityRunner,
    register_demo_capability,
)
from runtime.loop import ScriptedDecisionProvider  # noqa: E402
from runtime.repositories import RuntimeRepository  # noqa: E402
from runtime.service import RuntimeCoreService  # noqa: E402
from runtime.tenant_context import TenantContext  # noqa: E402
from schemas.runtime import ActionDecision, ActionKind, RunStatus  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist one Runtime Core happy-path Run in development PostgreSQL."
    )
    parser.add_argument(
        "--echo-value",
        default="runtime-core-happy-path",
        help="Value passed to demo.echo (default: %(default)s).",
    )
    return parser.parse_args()


def _require_postgresql(database_url: str) -> None:
    backend = make_url(database_url).get_backend_name()
    if backend != "postgresql":
        raise RuntimeError(
            "run_runtime_demo.py requires PostgreSQL; "
            f"configured DATABASE_URL uses {backend!r}"
        )


def main() -> int:
    args = _parse_args()
    _require_postgresql(DATABASE_URL)

    unique_suffix = uuid4().hex
    runtime_run_id = f"runtime-demo-run-{unique_suffix}"
    tenant_id = f"runtime-demo-tenant-{unique_suffix}"
    principal_id = f"runtime-demo-user-{unique_suffix}"

    invoke = ActionDecision(
        action_id=f"{runtime_run_id}-action-1",
        runtime_run_id=runtime_run_id,
        tenant_id=tenant_id,
        action_kind=ActionKind.INVOKE_CAPABILITY,
        target=DEMO_CAPABILITY_NAME,
        arguments={"value": args.echo_value},
        decision_summary="Invoke the deterministic demo.echo capability.",
        expected_outcome="Persist a successful tenant-bound CapabilityResult.",
        idempotency_key=f"{runtime_run_id}-step-1",
    )
    finish = ActionDecision(
        action_id=f"{runtime_run_id}-action-2",
        runtime_run_id=runtime_run_id,
        tenant_id=tenant_id,
        action_kind=ActionKind.FINISH,
        decision_summary="Finish after observing the demo.echo result.",
        expected_outcome="Complete the Runtime Run.",
        completion_requested=True,
        idempotency_key=f"{runtime_run_id}-step-2",
    )

    provider = ScriptedDecisionProvider([invoke, finish])
    registry = CapabilityRegistry()
    register_demo_capability(registry)
    repository = RuntimeRepository()
    service = RuntimeCoreService(
        provider,
        CapabilityRunner(registry),
        repository=repository,
    )
    context = TenantContext(tenant_id=tenant_id, principal_id=principal_id)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    try:
        with Session(engine) as execution_session:
            service.execute(
                execution_session,
                context,
                "Validate the Runtime Core happy path with demo.echo",
                runtime_run_id=runtime_run_id,
            )

        # Re-open the database to prove the summary comes from durable records,
        # not objects left in the execution Session.
        with Session(engine) as readback_session:
            run = repository.get_run(
                readback_session, context, runtime_run_id
            )
            states = repository.list_state_snapshots(
                readback_session, context, runtime_run_id
            )
            steps = repository.list_agent_steps(
                readback_session, context, runtime_run_id
            )
            traces = repository.list_trace_events(
                readback_session, context, runtime_run_id
            )
            audits = repository.list_audit_events(
                readback_session, context, runtime_run_id
            )

            if run is None:
                raise RuntimeError("Runtime Run was not found during durable readback")

            state_versions = [state.version for state in states]
            action_kinds = [step.action_kind for step in steps]
            if run.status != RunStatus.COMPLETED.value:
                raise RuntimeError(f"happy path did not complete: {run.status}")
            if state_versions != [1, 2, 3]:
                raise RuntimeError(f"unexpected State versions: {state_versions}")
            if action_kinds != [
                ActionKind.INVOKE_CAPABILITY.value,
                ActionKind.FINISH.value,
            ]:
                raise RuntimeError(f"unexpected AgentStep actions: {action_kinds}")
            if steps[0].result_json is None:
                raise RuntimeError("demo.echo CapabilityResult was not persisted")
            if steps[0].result_json.get("output") != {"echo": args.echo_value}:
                raise RuntimeError("demo.echo CapabilityResult output did not match")

            print(f"runtime_run_id: {run.runtime_run_id}")
            print(f"tenant_id: {run.tenant_id}")
            print(f"final status: {run.status}")
            print(f"termination_reason: {run.termination_reason}")
            print(f"state versions: {state_versions}")
            print(f"step count: {len(steps)}")
            print(f"trace count: {len(traces)}")
            print(f"audit count: {len(audits)}")
    finally:
        engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
