## Why

The current project is primarily a collection of predefined workflows and does not yet demonstrate a genuine autonomous Agent Runtime. We need a domain-neutral, Run-driven harness in which the model can determine whether the current information is sufficient, choose knowledge retrieval, tools, capabilities, a user question, or completion, and repeat that loop under explicit safety and budget controls.

This is the right foundation before cleaning up the frontend or rewriting existing domain workflows. It also creates a stable execution trace that can support later evaluation, SFT, or RL data preparation without training anything now.

## What Changes

- Add a Run lifecycle and asynchronous execution model backed by FastAPI, Celery, Redis, and workers.
- Add an autonomous Agent Loop driven by decisions and termination conditions rather than a fixed business sequence.
- Define canonical State, bounded Context construction, cross-run Memory, checkpoints, events, and replay metadata.
- Add separate registries and runners for atomic tools and multi-step workflows.
- Add a policy-aware `ToolExecutor` for `read_file`, `list_files`, `grep`, `bash`, and `write_file`, including validation, approval, sandboxing, timeout, and normalized results.
- Add user file upload for PDF, DOCX, and TXT plus asynchronous knowledge ingestion: object storage, parsing, chunking, embedding, Milvus indexing, metadata, and retrieval evidence.
- Enforce tenant isolation: every Run and knowledge record carries a tenant boundary; Runs can use files shared inside their own tenant but never files from another tenant.
- Treat RAG as a Knowledge/Evidence subsystem, not as a Tool or a fixed workflow stage.
- Keep existing FMEA, Audit, Report, and chat behavior available; expose them as optional capabilities instead of making them the Runtime's mandatory path.
- Remove the product-level dependency on cold-stamping or after-sales scenarios; those may become future capability packs.

## Capabilities

### New Capabilities

- `agent-runtime`: Run lifecycle, Agent Loop, State, Context, Memory, termination, checkpoints, events, and replay contracts.
- `tool-execution`: Tool metadata, policy checks, approval, sandboxed execution, and normalized `ToolResult` handling.
- `knowledge-ingestion`: Tenant-scoped PDF/DOCX/TXT upload, asynchronous ingestion jobs, document metadata/versioning, chunk indexing, retrieval, and evidence references.

### Modified Capabilities

None. Existing business workflows remain compatible and are not rewritten by this change.

## Impact

- FastAPI gains Run, event, file, ingestion-job, and knowledge-retrieval contracts.
- Celery uses Redis for separate Run and ingestion queues, progress, locks, and hot execution state.
- PostgreSQL stores tenant-aware Run metadata, State/trace metadata, file and ingestion metadata, permissions, and job status.
- MinIO (or the existing object-storage service) stores original uploaded files; Milvus stores chunk embeddings and retrieval indexes.
- The React frontend will eventually need Run status/trace and file-upload views, but frontend cleanup is out of scope for this planning change.
- Existing FMEA/Audit/Report graphs should be wrapped behind a capability registry in a later implementation step, without changing their current contracts.
