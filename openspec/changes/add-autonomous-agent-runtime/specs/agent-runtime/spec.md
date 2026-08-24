## Purpose

Provide a domain-neutral execution contract for Runs in which an Agent can repeatedly assess information sufficiency, select an appropriate action, update its state, and stop for a verifiable reason.

## ADDED Requirements

### Requirement: Run lifecycle is observable

The system SHALL create a Run with a stable identifier, tenant identifier, user goal, input references, status, timestamps, and termination reason. A Run status SHALL make it possible to distinguish queued, running, waiting for user input, waiting for approval, completed, failed, cancelled, and timed-out execution. The tenant identifier SHALL be immutable for the lifetime of the Run.

#### Scenario: Create and inspect a Run
- **WHEN** a user submits a goal
- **THEN** the system returns a Run identifier and exposes its current status, tenant boundary, and goal

#### Scenario: Run reaches a terminal state
- **WHEN** the Agent finishes, fails, is cancelled, or exceeds a configured budget
- **THEN** the system records a terminal status and a machine-readable termination reason

### Requirement: Agent selects the next action in a loop

The system SHALL allow the Agent to select its next action from the available action types, including responding, asking the user, retrieving evidence, invoking a capability, calling a tool, waiting for approval, and finishing. The system MUST NOT require a fixed business-stage sequence for every Run.

#### Scenario: Information is insufficient
- **WHEN** the Agent determines that the current State does not contain enough information to satisfy the goal
- **THEN** it selects a retrieval, tool, capability, or user-question action and continues the same Run after the action result is recorded

#### Scenario: Information is sufficient
- **WHEN** the Agent determines that the goal is satisfied and the result passes configured verification
- **THEN** it selects finish and the Run becomes completed

#### Scenario: Retrieval respects the Run tenant
- **WHEN** the Agent selects retrieve-evidence
- **THEN** the Knowledge service receives the Run tenant boundary and cannot return evidence belonging to another tenant

### Requirement: State, Context, Memory, and Evidence remain distinct

The system SHALL maintain canonical current-Run State separately from the bounded prompt Context sent to the model. Cross-Run Memory SHALL be persisted separately from State. Retrieved Knowledge evidence SHALL be represented with source references and SHALL be available to Context construction without being implicitly written to long-term Memory.

#### Scenario: Context is budgeted
- **WHEN** the current State, Memory, and Evidence exceed the model context budget
- **THEN** the system builds a bounded Context according to configured prioritization and records what was included or omitted

#### Scenario: Retrieved evidence is traceable
- **WHEN** a knowledge retrieval action returns evidence
- **THEN** the system records evidence identifiers and source references in State and makes them available to the next Context

### Requirement: Loop execution is bounded and resumable

The system SHALL enforce configured step, time, token, and cost limits. The system SHALL persist checkpoints and execution events sufficient to resume an interrupted Run or inspect its decision sequence without exposing hidden chain-of-thought as a required data field.

#### Scenario: Budget is exhausted
- **WHEN** a Run reaches any configured execution limit
- **THEN** the system stops further actions and records a bounded-budget termination reason

#### Scenario: Worker restarts during a Run
- **WHEN** a worker stops after a checkpoint has been persisted
- **THEN** another worker can resume the Run from the latest valid checkpoint without duplicating a completed side effect
