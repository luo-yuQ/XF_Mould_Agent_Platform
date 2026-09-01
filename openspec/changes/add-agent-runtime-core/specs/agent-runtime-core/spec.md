## Purpose

Provide the smallest durable Agent Runtime contract that proves an ordered decision loop can invoke one registered capability, incorporate its result into canonical State, finish on the next step, and preserve independently queryable execution records.

## ADDED Requirements

### Requirement: Runtime executes the minimal two-step loop

The system SHALL execute a Run synchronously in one process. For the successful Runtime Core path, the first AgentStep SHALL select `invoke-capability`, the selected capability SHALL return a structured CapabilityResult, the Runtime SHALL update State with that result, the second AgentStep SHALL select `finish`, and the Run SHALL become `completed`.

#### Scenario: Demo capability completes a Run
- **WHEN** a valid tenant starts a Run whose decision sequence selects the registered demo capability and then selects `finish`
- **THEN** the Runtime executes exactly two ordered AgentSteps and returns a completed Run containing the demo capability outcome

#### Scenario: Second decision observes the capability result
- **WHEN** the first AgentStep successfully returns a CapabilityResult
- **THEN** the Runtime persists an updated State before requesting the second ActionDecision, and the second decision input includes that result

### Requirement: Runtime accepts only the Core action protocol

The Runtime Core SHALL validate every ActionDecision and SHALL dispatch only `invoke-capability` and `finish`. It MUST NOT execute an unsupported action or an unregistered capability.

#### Scenario: Unsupported action is rejected
- **WHEN** a decision selects an action other than `invoke-capability` or `finish`
- **THEN** the Runtime records the rejected step, terminates the Run as `failed`, and does not dispatch the action

#### Scenario: Unknown capability is rejected
- **WHEN** a decision selects `invoke-capability` with a capability name that is not registered for the Run
- **THEN** the Runtime records a failed CapabilityResult or equivalent structured failure, terminates the Run as `failed`, and does not invoke unrelated code

### Requirement: Capability invocation is structured and idempotent

The Runtime SHALL invoke capabilities through a registry and runner boundary. Each invocation SHALL use validated arguments and an idempotency key, and SHALL produce a structured CapabilityResult containing the capability identity, outcome status, output or error, and execution metadata.

#### Scenario: Registered demo capability succeeds
- **WHEN** the first AgentStep invokes the registered no-side-effect demo capability with valid arguments
- **THEN** the runner returns a successful CapabilityResult that is attached to the AgentStep and incorporated into the next State version

#### Scenario: Invocation is retried with the same idempotency key
- **WHEN** the Runtime receives the same Run, step, and idempotency key after the capability result has already been persisted
- **THEN** it reuses the persisted result and does not execute the capability a second time

### Requirement: Five Runtime record types are persisted separately

The system SHALL persist Run, versioned State, AgentStep, TraceEvent, and AuditEvent as five distinct Runtime record types. AgentStep SHALL preserve its step index, ActionDecision, input State version, output State version, result, status, and timing. TraceEvent and AuditEvent SHALL remain separate append-only records with stable ordering inside a Run.

#### Scenario: Successful Run is reloaded from durable records
- **WHEN** the successful two-step Run is reloaded using a new database session
- **THEN** the system can retrieve one completed Run, three ordered State versions, two ordered AgentSteps, ordered TraceEvents, and ordered AuditEvents without reconstructing them from process memory

#### Scenario: State versions reflect each durable boundary
- **WHEN** the minimal loop completes successfully
- **THEN** State version 1 represents Run creation, version 2 contains the CapabilityResult, and version 3 represents terminal completion

### Requirement: Trace and Audit serve distinct observable purposes

TraceEvent SHALL describe the ordered operational execution sequence for diagnosis. AuditEvent SHALL describe attributable Runtime operations using bounded fields for actor, operation, target, outcome, Run, optional AgentStep, and timestamp. Neither record type SHALL require or persist hidden chain-of-thought.

#### Scenario: Capability execution is traceable and auditable
- **WHEN** the Runtime invokes the demo capability
- **THEN** Trace records the execution sequence while Audit separately records who invoked which capability and whether it succeeded

#### Scenario: Run completion is audited
- **WHEN** the `finish` decision completes the Run
- **THEN** the Runtime appends a completion TraceEvent and a distinct successful AuditEvent associated with the Run

### Requirement: Runtime records are tenant isolated

Every Run, State, AgentStep, TraceEvent, AuditEvent, ActionDecision, and CapabilityResult SHALL carry or inherit one immutable tenant boundary. The Runtime SHALL reject a missing or mismatched tenant before reading a protected record or dispatching a capability.

#### Scenario: Cross-tenant Run access is denied
- **WHEN** a caller from another tenant requests a Run or any of its persisted records
- **THEN** the Runtime returns no protected data and does not dispatch an action

#### Scenario: Capability result tenant does not match the Run
- **WHEN** a capability returns a result whose tenant identity differs from the owning Run
- **THEN** the Runtime rejects the result, records the failure within the owning tenant boundary, and does not update State with the mismatched data

### Requirement: Loop execution is bounded

The Runtime Core SHALL enforce a configured positive maximum AgentStep count. Reaching the limit before a valid `finish` decision SHALL terminate the Run as `failed` with a machine-readable termination reason and observable Trace and Audit records.

#### Scenario: Maximum step count is reached
- **WHEN** valid decisions continue without selecting `finish` until the configured maximum is reached
- **THEN** the Runtime stops without executing another step and persists the Run failure, termination reason, TraceEvent, and AuditEvent
