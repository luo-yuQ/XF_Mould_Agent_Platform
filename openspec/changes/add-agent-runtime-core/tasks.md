## 1. Core contracts and persistence model

- [x] 1.1 Narrow the Runtime Core dispatcher contract to `invoke-capability` and `finish`, add `CapabilityResult`, `AgentStep`, and `AuditEvent` schemas, and verify schema tests reject malformed, unsupported, or cross-tenant payloads.
- [x] 1.2 Reshape the unpublished Runtime SQLAlchemy draft into exactly the five Core record types (`runtime_runs`, `runtime_state_snapshots`, `runtime_agent_steps`, `runtime_trace_events`, and `runtime_audit_events`), remove draft ActionRecord/Checkpoint exports from the Core model, and verify metadata contains the expected tables and uniqueness constraints.
- [x] 1.3 Align the Runtime migration with the five Core tables and verify upgrade and downgrade render successfully without changing existing business tables.
- [x] 1.4 Implement tenant-scoped repository operations for Run lifecycle updates, immutable State snapshots, AgentStep create/finalize and idempotent lookup, ordered Trace append/read, and ordered Audit append/read; verify focused persistence tests cover a new database session and cross-tenant denial.

## 2. Decision and capability boundaries

- [x] 2.1 Define a replaceable Decision Provider boundary plus a scripted test provider that emits `invoke-capability` and then `finish`, and verify the second call receives State containing the first CapabilityResult.
- [x] 2.2 Implement the minimal Capability Registry and Runner with registration lookup, argument and tenant validation, normalized CapabilityResult, error normalization, and completed-result idempotency; verify unknown capabilities fail closed and duplicate keys do not execute twice.
- [x] 2.3 Add one deterministic no-side-effect demo capability and verify valid input returns a tenant-bound structured result without calling existing business graphs, RAG, tools, or external services.

## 3. Synchronous Runtime loop

- [x] 3.1 Implement atomic Run initialization that persists a queued Run, State v1, initial TraceEvent, and initial AuditEvent before execution; verify partial initialization rolls back as one transaction.
- [x] 3.2 Implement AgentStep 1 dispatch for `invoke-capability`, including Run transition to running, step creation/finalization, demo capability execution, CapabilityResult persistence, State v2 creation, and Trace/Audit appends; verify every record shares the Run tenant and stable identifiers.
- [x] 3.3 Implement AgentStep 2 dispatch for `finish`, including step creation/finalization, State v3 creation, Run completion timestamps and termination reason, and terminal Trace/Audit appends; verify the final Run and State are both completed.
- [x] 3.4 Implement fail-closed handling for malformed or unsupported decisions, unknown capabilities, mismatched result tenants, capability failures, and positive `max_steps` exhaustion; verify each path terminates the Run once with a machine-readable reason and observable Step/Trace/Audit records.

## 4. Vertical-slice verification

- [x] 4.1 Add a deterministic end-to-end test for `Run created -> AgentStep 1 invoke-capability -> Demo Capability -> CapabilityResult -> State update -> AgentStep 2 finish -> Run completed`, and verify readback in a new database session returns one Run, State versions 1/2/3, two ordered AgentSteps, ordered TraceEvents, and separate ordered AuditEvents.
- [x] 4.2 Add integration coverage proving a repeated completed step/idempotency key reuses its persisted CapabilityResult and invokes the demo capability only once.
- [x] 4.3 Apply the Runtime migration to a clean PostgreSQL database and verify the focused Runtime contract, persistence, failure-path, and vertical-slice test suites pass without Redis, Celery, MinIO, Milvus, or a live LLM.
- [x] 4.4 Run the existing chat, FMEA, Audit, Report, RAG, Memory, and business-workflow regression suites relevant to touched imports and models, and verify this isolated Core introduces no endpoint or persistence regressions.
