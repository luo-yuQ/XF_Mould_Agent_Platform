## Purpose

Allow users to upload knowledge files asynchronously and make their versioned, permission-scoped content available to Agent Runs as traceable retrieval evidence rather than as an opaque prompt or tool result.

## ADDED Requirements

### Requirement: User can create a file ingestion job

The system SHALL accept an uploaded PDF, DOCX, or TXT file with tenant metadata and an access scope, persist the original file, create an ingestion-job identifier, and expose processing status and errors independently from any Agent Run. The file and its ingestion job SHALL carry an immutable tenant identifier.

#### Scenario: Upload is accepted
- **WHEN** a user uploads a supported file within configured size and security limits
- **THEN** the system stores the original, returns a file and ingestion-job identifier, and marks the job as queued or processing

#### Scenario: Supported formats are explicit
- **WHEN** a user uploads a PDF, DOCX, or TXT file within configured limits
- **THEN** the system accepts it for ingestion without requiring the file to be tied to the current conversation

#### Scenario: Upload is rejected
- **WHEN** a file type, size, content, or access scope violates policy
- **THEN** the system rejects the upload without indexing it and returns a structured reason

### Requirement: Ingestion produces versioned searchable content

The system SHALL parse accepted files, preserve document and version metadata, split content into retrievable chunks, index the chunks, and expose a terminal ingestion status. Each indexed chunk SHALL retain enough metadata to identify its document, version, location, and access scope.

#### Scenario: Ingestion completes
- **WHEN** parsing, chunking, and indexing succeed
- **THEN** the ingestion job becomes completed and the file version can be searched within its permitted scope

#### Scenario: Ingestion fails
- **WHEN** parsing or indexing fails
- **THEN** the job becomes failed with an actionable error and no incomplete version is presented as searchable

### Requirement: Retrieval returns evidence, not an opaque text blob

The Knowledge service SHALL accept a query and permitted knowledge scope and return an EvidenceSet containing selected chunks, source references, document/version identifiers, and retrieval metadata. Retrieval SHALL be a distinct Agent action and SHALL NOT be modeled as an atomic Tool call.

#### Scenario: Agent retrieves permitted evidence
- **WHEN** the Agent selects retrieve-evidence for a query
- **THEN** the system returns only evidence within the Run's permitted scope and records source references for the next Context

#### Scenario: No evidence is found
- **WHEN** retrieval returns no permitted matching evidence
- **THEN** the system returns an explicit empty result so the Agent can ask the user, use another action, or finish with an uncertainty statement

### Requirement: Knowledge access is isolated by scope and version

The system SHALL enforce tenant isolation and file/knowledge-scope permissions for both ingestion and retrieval. A Run SHALL be allowed to retrieve files shared within its own tenant by default, regardless of which conversation uploaded them. A Run SHALL never retrieve a file belonging to another tenant. A newer file version SHALL NOT silently overwrite the metadata or traceability of an older version.

#### Scenario: User searches another scope
- **WHEN** a Run requests evidence from a scope the user is not allowed to access
- **THEN** the Knowledge service denies the request and records the authorization failure

#### Scenario: Cross-tenant retrieval is denied
- **WHEN** a Run attempts to retrieve evidence whose tenant identifier differs from the Run tenant identifier
- **THEN** the Knowledge service returns an authorization failure and no cross-tenant content is exposed

#### Scenario: Same-tenant file is reusable
- **WHEN** a Run requests evidence from a completed file version shared within the Run's tenant
- **THEN** the Knowledge service may return that evidence even when the file was uploaded by another conversation
