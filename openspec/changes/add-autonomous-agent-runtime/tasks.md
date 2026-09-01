## 1. Runtime foundation and contracts

- [x] 1.1 Create isolated Runtime module boundaries for runs, loop, state, context, events, tools, capabilities, knowledge, and workers without changing existing business graphs; verify all new modules import successfully.
- [ ] 1.2 Add Celery and Redis configuration with separate Run and ingestion queue names; verify a local Celery worker starts and accepts one smoke task.
- [x] 1.3 Define versioned schemas for Run, ActionDecision, ActionResult, StateSnapshot, EvidenceSet, ToolResult, TraceEvent, FileVersion, and IngestionJob including mandatory `tenant_id`; verify schema tests cover valid and invalid payloads.
- [ ] 1.4 Add tenant-boundary validation shared by Run creation, file upload, ingestion, retrieval, and tool execution; verify a missing or mismatched tenant is rejected before dispatch.
- [x] 1.5 Add additive persistence for core Runtime Runs, State snapshots, action records, TraceEvents, and Checkpoints; verify isolated persistence tests pass, the Runtime migration renders successfully, and existing tables are not modified.
- [ ] 1.6 Add additive PostgreSQL persistence for files, file versions, and ingestion jobs; verify the knowledge-ingestion migration applies on a clean database without changing existing tables' behavior.

## 2. Run lifecycle and Agent Loop

- [ ] 2.1 Implement Run creation, status lookup, cancellation, user-response submission, and approval-response contracts; verify each transition is persisted with an immutable tenant identifier.
- [ ] 2.2 Implement canonical State storage and append-only TraceEvent recording; verify state snapshots can be loaded by Run id and tenant id.
- [ ] 2.3 Implement checkpoint creation and resume tokens for action boundaries; verify a worker restart resumes from the latest checkpoint without duplicating a completed action.
- [ ] 2.4 Implement Context Builder with token/character budget, State priority, selected Memory, Evidence references, and included/omitted metadata; verify over-budget context is truncated deterministically.
- [ ] 2.5 Implement the structured LLM decision adapter with action validation and bounded decision summaries; verify malformed or unsupported model decisions become rejected ActionResults instead of executing.
- [ ] 2.6 Implement the Agent Loop action dispatcher for respond, ask-user, retrieve-evidence, invoke-capability, call-tool, wait-approval, and finish; verify a mocked Run can execute multiple iterations before completion.
- [ ] 2.7 Add step, time, token, cost, repeated-action, and cancellation guards; verify each guard produces a terminal Run status and machine-readable termination reason.
- [ ] 2.8 Add the Celery Run task and progress events for queued, running, waiting, completed, failed, cancelled, and timed-out states; verify status polling observes the same state stored by the worker.
- [ ] 2.9 Add a no-side-effect demo capability for vertical-slice testing; verify a mocked goal can retrieve a result, update State, and finish through the loop.

## 3. Tool Registry and ToolExecutor

- [ ] 3.1 Implement Tool Registry metadata and input/output schema discovery with risk and permission declarations; verify Context Builder exposes only tools permitted for the Run tenant and policy.
- [ ] 3.2 Implement ToolExecutor validation, policy evaluation, timeout handling, normalized ToolResult, and execution identifiers; verify invalid and disallowed calls never reach an operating-system process.
- [ ] 3.3 Implement read-only `list_files`, `read_file`, and `grep` tools with workspace path restrictions; verify traversal outside the allowed workspace is rejected.
- [ ] 3.4 Implement sandboxed `bash` with command, environment, timeout, and resource limits; verify a timeout returns a failure result and leaves an audit event.
- [ ] 3.5 Implement `write_file` with path allowlisting, diff/size limits, and approval gating; verify no file changes occur while a Run is waiting for approval.
- [ ] 3.6 Record redacted arguments, policy decisions, approvals, outputs, errors, durations, and side-effect metadata; verify an operator can reconstruct a tool call from the Run trace.

## 4. Tenant-scoped knowledge ingestion

- [ ] 4.1 Add upload and file-metadata contracts for PDF, DOCX, and TXT with size/content validation and tenant ownership; verify unsupported formats and invalid tenant claims are rejected.
- [ ] 4.2 Persist original uploads in object storage and file/version/job metadata in PostgreSQL without binding the file to one conversation; verify another Run in the same tenant can reference a completed file version.
- [ ] 4.3 Add Celery ingestion tasks with queued, processing, completed, and failed states plus retry/idempotency keys; verify a failed job is not searchable as a complete version.
- [ ] 4.4 Define the parser/chunker provider boundary and document the later concrete strategy for PDF, DOCX, and TXT; verify provider contract tests expose chunk text, location, version, and tenant metadata.
- [ ] 4.5 Connect completed file versions to the existing knowledge indexing boundary without changing business-artifact ingestion behavior; verify indexed chunks retain document/version/location/tenant metadata.
- [ ] 4.6 Implement Knowledge Service retrieval that filters by Run tenant and returns EvidenceSet source references; verify cross-tenant retrieval is denied and same-tenant files are reusable across conversations.
- [ ] 4.7 Expose ingestion-job status and progress events to the Run/API layer; verify clients can distinguish upload acceptance, processing, failure, and searchable completion.

## 5. Capability and existing workflow integration

- [ ] 5.1 Implement Workflow/Capability Registry and Runner contracts separate from Tool Registry and ToolExecutor; verify a capability result is returned as an ActionResult without being represented as a ToolResult.
- [ ] 5.2 Wrap existing chat, FMEA, Audit, and Report entry points behind compatibility adapters without changing their graph topology or public behavior; verify existing endpoint tests remain green.
- [ ] 5.3 Add capability discovery and tenant/policy filtering to Context Builder; verify the Agent can choose a registered capability only when its contract is available to the Run.

## 6. API, events, and frontend slice

- [ ] 6.1 Expose Run create/status/cancel/respond/approve endpoints and an event stream using the Runtime schemas; verify API responses contain Run id, tenant-safe status, and termination details.
- [ ] 6.2 Expose file upload, ingestion-job status, and tenant-scoped knowledge retrieval endpoints; verify PDF/DOCX/TXT uploads report progress independently of an Agent Run.
- [ ] 6.3 Add a minimal React Run view showing status, action timeline, approval prompts, and final result; verify it can reconnect to an existing Run without losing events.
- [ ] 6.4 Add a minimal React file-upload and ingestion-status view; verify uploaded files are shown by tenant scope and are not presented as conversation-only attachments.

## 7. Verification, operations, and future data readiness

- [ ] 7.1 Add unit tests for State/Context separation, action validation, termination guards, ToolExecutor policy, Evidence references, and tenant isolation; verify the focused test suite passes.
- [ ] 7.2 Add integration tests with PostgreSQL, Redis, Celery, object storage, and Milvus service dependencies; verify a Run and an IngestionJob can complete end to end.
- [ ] 7.3 Add security regression tests for cross-tenant Run lookup, file retrieval, evidence retrieval, tool paths, bash commands, and write approvals; verify every denial is audited.
- [ ] 7.4 Run the existing chat/FMEA/Audit/Report regression suite and verify no existing endpoint or Memory V1 behavior changes.
- [ ] 7.5 Document Run, ActionDecision, ToolResult, EvidenceSet, IngestionJob, tenant boundaries, and operational commands; verify the docs match the implemented schemas.
- [ ] 7.6 Store structured decision summaries, action outcomes, evidence references, verifier results, user feedback, and model/version metadata for future evaluation datasets; verify no hidden chain-of-thought field is required.
