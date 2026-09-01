## Context

See `proposal.md` for motivation and `specs/agent-runtime-core/spec.md` for the observable contract. The repository already contains versioned Runtime schemas, a Run lifecycle state machine, tenant validation, initial SQLAlchemy models, repository primitives, and focused tests. It does not yet contain an Agent Loop, capability runner, AgentStep model, Runtime Audit model, or a complete Run update path.

The existing persistence work is still an unpublished implementation draft in the working tree. This allows the data model to be aligned with the smaller Core contract before it becomes a compatibility burden. Existing chat and quality workflows remain separate and must continue to operate unchanged.

## Goals / Non-Goals

**Goals:**

- Prove one durable vertical slice from Run creation through one capability invocation to completion.
- Make each loop iteration an explicit, ordered AgentStep.
- Keep canonical State versioned and durable across action boundaries.
- Give Trace and Audit distinct schemas, storage, and query behavior.
- Keep decision production and capability execution behind small replaceable interfaces.
- Make the happy path and failure paths deterministic in automated tests.

**Non-Goals:**

- No background queue, distributed worker, cancellation, waiting, resume, checkpoint, or replay behavior.
- No tools, approval policy, file operations, knowledge retrieval/ingestion, Memory, or Context Builder.
- No adapters for FMEA, Audit, Report, chat, or other existing workflows.
- No public frontend, streaming event API, or production LLM dependency.
- No action kinds beyond `invoke-capability` and `finish` in the Core dispatcher.

## Decisions

### 1. Execute through a synchronous Runtime application service

A Runtime Core service owns Run creation and loops in the caller process until completion or failure. It coordinates repositories, the Decision Provider, and the Capability Runner, committing at durable boundaries. HTTP and worker adapters can call this service later but are not part of this change.

**Alternative considered:** Introduce Celery and Redis immediately. Rejected because queue delivery, worker recovery, and distributed coordination do not help prove the first decision/capability/state loop and would dominate its failure surface.

### 2. Make AgentStep the durable unit of one decision iteration

Replace the draft Runtime action-record concept with `AgentStep`. Each step has a stable identifier, Run and tenant identity, one-based `step_index`, idempotency key, input and output State versions, structured ActionDecision, optional CapabilityResult or finish result, status, error, and timing metadata. `(runtime_run_id, step_index)` and `(runtime_run_id, idempotency_key)` are unique.

The unpublished draft `RuntimeActionRecord` model and migration are reshaped before merge rather than preserving two overlapping concepts. `RuntimeCheckpoint` is excluded from the Core persistence set.

**Alternative considered:** Keep ActionRecord and add AgentStep around it. Rejected because one Core iteration currently contains exactly one decision and one result; two tables would duplicate identity, ordering, status, and idempotency semantics without providing value.

### 3. Use explicit State snapshots at three boundaries

The successful path persists:

1. State v1 after Run creation.
2. State v2 after the demo CapabilityResult is accepted.
3. State v3 when `finish` completes the Run.

The second Decision Provider call receives State v2, making it testable that capability output participates in the next decision. State snapshots remain canonical; decision prompts or hidden reasoning are not state.

**Alternative considered:** Mutate one current-state row. Rejected because versioned snapshots make ordering and durable readback explicit with very little additional complexity in a two-step slice.

### 4. Separate Decision Provider from loop orchestration

The loop depends on a small Decision Provider interface that accepts the current State and step metadata and returns a validated ActionDecision. Acceptance tests use a scripted provider that emits `invoke-capability` and then `finish`. The existing structured JSON helper may back a real LLM provider later, but live-model behavior is not a Definition of Done dependency.

**Alternative considered:** Call the configured LLM directly from the loop. Rejected because provider variability would make persistence and protocol acceptance tests nondeterministic and would couple the Core to one model integration.

### 5. Use a minimal registry and runner with one demo capability

The Capability Registry maps a stable capability name to its metadata and callable. The Runner validates registration, tenant identity, input, and idempotency before invoking it, then normalizes success or failure as CapabilityResult. The demo capability is deterministic and has no external side effects.

CapabilityResult is distinct from ToolResult and includes capability name, tenant, execution identifier, status, structured output or bounded error, duration, and idempotency key. It is persisted inside the owning AgentStep and copied into State v2; a separate result table is unnecessary for this slice.

**Alternative considered:** Wrap an existing business graph as the first capability. Rejected because it would pull business schemas, RAG, verification, and LLM variability into the Core acceptance path.

### 6. Persist five record types with separate meanings

The Core schema contains:

- `runtime_runs`: durable identity, tenant, goal, lifecycle, timestamps, termination reason.
- `runtime_state_snapshots`: immutable ordered canonical State versions.
- `runtime_agent_steps`: ordered decision/result iterations and idempotency boundary.
- `runtime_trace_events`: append-only operational timeline ordered by per-Run sequence.
- `runtime_audit_events`: append-only attributable actions ordered by per-Run audit sequence.

Trace payloads may describe lifecycle and execution details needed for diagnosis. Audit fields stay bounded and explicit: actor/principal, operation, target type/id, outcome, Run, optional step, metadata, timestamp. Neither contains hidden chain-of-thought. Existing business `audit_runs` are unrelated and are never reused.

**Alternative considered:** Derive Trace and Audit from AgentStep rows. Rejected because lifecycle events exist outside steps and audit accountability has different retention, redaction, and query semantics from diagnostic trace.

### 7. Commit once per durable boundary and finalize steps explicitly

Run creation atomically writes Run, State v1, initial Trace, and initial Audit. A capability boundary atomically finalizes AgentStep 1 with CapabilityResult, writes State v2, and appends Trace/Audit. A finish boundary atomically finalizes AgentStep 2, writes State v3, completes the Run, and appends Trace/Audit.

The repository exposes explicit create/finalize operations instead of returning an existing pending row without applying its result. Repeating a completed `(Run, idempotency_key)` returns the stored step/result and never invokes the capability again.

**Alternative considered:** Commit every individual record independently. Rejected because partial state could claim that a capability succeeded without making its result available to the next State.

### 8. Fail closed and preserve observable failure records

Unsupported actions, malformed decisions, unknown capabilities, tenant mismatches, capability errors, and maximum-step exhaustion terminate the Run as `failed`. The Runtime records the attempted AgentStep when one exists, a machine-readable termination reason, and corresponding Trace and Audit events. It never silently falls back to another action or business workflow.

## Risks / Trade-offs

- [A synchronous Run can occupy a request thread] → Keep the demo capability bounded and treat async execution as a later adapter around the Core service.
- [Scripted decisions do not prove live-model quality] → Use them only for deterministic Core acceptance; add a real structured Decision Provider in a later change or optional smoke test.
- [Snapshot and event writes can drift apart] → Group each durable boundary in one database transaction and test rollback behavior.
- [Audit payloads can leak sensitive inputs] → Store bounded actor/operation/target/outcome fields and explicitly selected metadata, not prompts or hidden reasoning.
- [The old large Change overlaps conceptually] → Mark this Change as superseding only its Core scope and retire the old active Change separately after this proposal is accepted.
- [Reshaping the unpublished migration can affect local developer databases] → Treat the draft migration as not released; developers who already applied it recreate or explicitly repair only their development database before implementation verification.

## Migration Plan

1. Align Runtime schemas around ActionDecision, CapabilityResult, AgentStep, AuditEvent, and the two supported Core actions.
2. Reshape the unpublished Runtime migration and SQLAlchemy models to the five Core record types; do not add checkpoint, file, ingestion, tool, or knowledge tables.
3. Update repositories with tenant-scoped create, finalize, append, update-Run, and ordered readback operations.
4. Add the synchronous loop, scripted Decision Provider, registry, runner, and demo capability.
5. Run the migration on a clean PostgreSQL database, execute the deterministic two-step integration test, and run existing Runtime and business-workflow regressions.
6. If rollback is required before release, remove the new isolated Runtime tables through the migration downgrade; existing business tables and routes remain unchanged.
