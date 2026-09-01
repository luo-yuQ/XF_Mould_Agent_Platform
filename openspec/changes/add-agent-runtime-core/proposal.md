## Why

The existing `add-autonomous-agent-runtime` change combines the Agent Loop with distributed workers, tool execution, knowledge ingestion, business adapters, and frontend work, making the first verifiable Runtime milestone too large. We need a smaller vertical slice that proves the core execution protocol and its durable records before adding those surrounding systems.

## What Changes

- Add a synchronous, single-process Runtime Core that executes exactly the minimal loop needed for one capability invocation followed by completion.
- Add an ordered `AgentStep` model in which step 1 persists an `invoke-capability` decision and its `CapabilityResult`, while step 2 persists a `finish` decision.
- Add a deterministic, no-side-effect demo capability behind a minimal capability registry and runner.
- Persist five distinct Runtime record types: Run, versioned State snapshots, AgentStep, append-only Trace events, and append-only Audit events.
- Add tenant validation, structured decision validation, unknown-capability handling, idempotent step execution, and a maximum-step guard for this minimal loop.
- Reuse and narrow the existing Runtime schemas, lifecycle state machine, tenant boundary, persistence groundwork, and structured-output helper where they fit the smaller contract.
- Supersede the Runtime Core portion of `add-autonomous-agent-runtime`; that larger change is not completed or archived by this proposal, and its remaining features must be handled separately.
- Explicitly exclude Celery, Redis, distributed workers, resume/checkpoints/replay, ToolExecutor, knowledge ingestion and retrieval, existing business capability adapters, frontend work, user/approval waits, and the other autonomous action kinds.

## Capabilities

### New Capabilities

- `agent-runtime-core`: Synchronous two-step Agent execution, demo capability invocation, completion, and separate persistence of Run, State, AgentStep, Trace, and Audit records.

### Modified Capabilities

None.

## Impact

- Affects the isolated `runtime/` package, Runtime schemas and persistence models, additive database migration(s), model exports, and focused Runtime tests.
- Introduces a minimal Runtime application-service boundary and demo capability without changing existing chat, FMEA, Audit, Report, RAG, Memory V1, or Milvus behavior.
- Does not require Redis, Celery, MinIO, Milvus, a frontend, or a live LLM for deterministic acceptance testing.
