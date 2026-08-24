## Context

The repository already has a FastAPI entry point, React UI, PostgreSQL models, Redis, Milvus-backed knowledge retrieval, MinIO in the local service topology, and several LangGraph-style business graphs. The existing graphs are useful capabilities, but their fixed topology is not an adequate Runtime contract. Existing Memory V1 and the current FMEA/Audit/Report/RAG flows must remain compatible while the new harness is introduced. The first upload slice is limited to PDF, DOCX, and TXT, and all Runs and knowledge records are tenant-scoped.

See `proposal.md` for the motivation and the capability contracts for externally observable behavior.

## Goals / Non-Goals

**Goals:**

- Make a Run the unit of execution and observation.
- Let the Agent choose among evidence retrieval, atomic tools, registered capabilities, user questions, approval waits, and completion on every loop iteration.
- Keep State, bounded Context, Memory, and Knowledge Evidence as separate data concepts.
- Provide a policy boundary around ToolExecutor and a separate runner for workflows.
- Process uploaded knowledge asynchronously and preserve source/version/scope metadata.
- Capture enough structured trace data for evaluation and future training-data preparation.

**Non-Goals:**

- Do not rewrite the existing FMEA, Audit, Report, or chat graphs in this change.
- Do not make cold-stamping or after-sales behavior part of the Runtime contract.
- Do not implement SFT, RL, hidden chain-of-thought storage, or autonomous deployment actions.
- Do not treat RAG as a Tool, or make a fixed workflow sequence mandatory.
- Do not alter Memory V1 semantics or existing business-artifact Milvus ingestion behavior.

## Decisions

### 1. Separate Run execution from file ingestion

Use `Run` for an Agent task and `IngestionJob` for asynchronous document processing. A file belongs to a tenant-level knowledge scope and may be referenced by many Runs in that tenant; it is not bound to the conversation that uploaded it. Parsing a large file must not occupy the Run worker.

**Alternative considered:** Model ingestion as a special Agent tool call. Rejected because upload and indexing are user/data-plane operations with different retries, permissions, and progress semantics.

### 2. Use a small action protocol instead of a fixed graph

The loop emits a structured decision with an action kind, target, validated arguments, concise decision summary, expected outcome, and completion flag. The Runtime dispatches the action to Knowledge Service, ToolExecutor, Workflow Runner, user interaction, or termination. The loop then writes the result into State and asks the model for the next decision.

The decision summary is observable and bounded; hidden chain-of-thought is neither required nor persisted.

**Alternative considered:** Keep a supervisor graph with a larger set of predefined branches. Rejected because it preserves the current workflow-first behavior and prevents the model from choosing an open-ended sequence.

### 3. Make State canonical and Context derived

State is the source of truth for the current Run: goal, constraints, messages, actions, tool/workflow outputs, Evidence references, artifacts, status, budgets, and termination reason. Context Builder creates a budgeted model input from State plus selected Memory and Evidence and records selection metadata. Memory is persisted separately and only receives explicitly selected durable facts.

**Alternative considered:** Store the complete prompt as the primary state. Rejected because prompts are lossy, expensive to replay, and mix current facts with presentation choices.

### 4. Separate Tool Registry, ToolExecutor, and Workflow Runner

Tool Registry provides metadata and schemas. ToolExecutor validates and executes atomic operations such as `grep`, `bash`, and `write_file` within Policy/Sandbox controls. Workflow Registry and Workflow Runner expose existing multi-step capabilities without labeling them as tools. Both return structured action results to the same loop, but they have different contracts and risk models.

**Alternative considered:** Wrap every workflow as a Tool. Rejected because it hides business capability boundaries and makes permission, tracing, and future capability discovery ambiguous.

### 5. Reuse the existing knowledge ingestion boundary

The new upload flow will call the existing document parsing/chunking/indexing boundary where possible, adding only the file/job/scope contract needed by the Runtime. Original files belong in object storage; PostgreSQL owns file/version/job metadata; Milvus remains the retrieval index for knowledge chunks. Business-artifact ingestion and existing RAG query behavior are not changed.

**Alternative considered:** Put uploaded file contents directly into Run State. Rejected because it breaks context budgets, prevents reuse across Runs, and loses document/version provenance.

### 6. Use Celery with separate queue lanes and idempotent checkpoints

Celery uses Redis as the broker/result backend, with separate queue lanes for Run work and ingestion work. Every action receives an execution identifier and an idempotency/checkpoint boundary. Side-effecting tools require a policy decision before execution and are not replayed after a completed side effect without an explicit idempotency check.

**Alternative considered:** ARQ or one synchronous FastAPI request for the whole loop and ingestion. ARQ is also a Python Redis queue with stronger asyncio alignment, but Celery is selected for its mature task routing, retry, monitoring, and ecosystem. A synchronous request is rejected because model/tool calls and document processing can exceed request limits and cannot recover cleanly from worker restarts.

### 7. Introduce adapters around existing capabilities

Existing FMEA, Audit, Report, and chat graphs are registered as capabilities behind a compatibility adapter. Their current entry points and artifact contracts remain unchanged. The adapter translates a capability invocation into a structured action result and preserves existing references and verification behavior.

**Alternative considered:** Change each graph to understand the new Runtime State immediately. Rejected because it expands the change surface and risks breaking the already-working workflows.

### 8. Map persistence to the existing service topology

- PostgreSQL: tenant-aware Run metadata, action/trace metadata, file/version/job metadata, permission scope, and terminal results.
- Redis: Celery broker/result backend, locks, progress notifications, and hot checkpoint coordination.
- MinIO/object storage: original uploaded files and generated non-database artifacts.
- Milvus: knowledge chunk index used by the existing retrieval boundary.

The exact table names and queue library remain implementation details, but the API and event contracts must remain stable.

## Risks / Trade-offs

- [Autonomous loop can run too long or spend too much] → Enforce step/time/token/cost budgets, detect repeated actions, and expose a stop endpoint.
- [Bash and write tools can damage data] → Default-deny policy, workspace path allowlist, sandbox, timeout, approval gates, and complete side-effect tracing.
- [Context selection can omit important facts] → Keep canonical State, record included/omitted context items, and make Evidence references compact and source-linked.
- [Uploaded files can be malicious or malformed] → Validate PDF/DOCX/TXT type, size, and content, isolate parsing workers, retain failed job status, and never expose an incomplete version as searchable.
- [A tenant boundary can be bypassed] → Require tenant identifiers at every Run, file, ingestion-job, and retrieval boundary; test cross-tenant denial explicitly.
- [RAG evidence can be low quality] → Preserve source/version/chunk metadata, return an explicit empty result, and require the Agent to communicate uncertainty when evidence is insufficient.
- [Adapters can hide incompatibilities in old graphs] → Start with read-only capability registration and contract tests; do not modify old graph topology in the first implementation slice.
- [Trace data may contain sensitive content] → Store structured decision summaries and references by default, apply redaction to tool arguments/output, and avoid persisting hidden chain-of-thought.

## Migration Plan

1. Add the Runtime contracts and tenant-aware persistence/event types without changing existing routes.
2. Add a minimal Run API, queue lane, worker, loop, checkpoint, and trace path using a no-side-effect demo capability.
3. Add Tool Registry, ToolExecutor, and policy/approval controls; enable read-only tools before `bash` and `write_file`.
4. Add the PDF/DOCX/TXT upload and IngestionJob path by reusing the existing knowledge ingestion boundary, then expose tenant-scoped retrieval Evidence to the loop.
5. Register existing graphs through compatibility adapters and verify their current endpoints still pass their existing tests.
6. Add frontend Run/trace/upload views after the backend contracts stabilize.

Rollback is by disabling the new Run and ingestion routes/worker consumers. Existing chat and business workflow routes remain the fallback and are not migrated in place.

## Open Questions

- Which parser and chunking strategy should be used for PDF, DOCX, and TXT? This is deliberately deferred until the ingestion contract and worker boundary are implemented.
