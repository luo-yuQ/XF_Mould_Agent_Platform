## Purpose

Provide a controlled execution boundary for atomic tools so that an Agent can use local inspection and modification capabilities without bypassing validation, authorization, safety, or observability requirements.

## ADDED Requirements

### Requirement: Tools expose executable contracts

The system SHALL register each tool with a stable name, description, input schema, output schema, risk level, and permission requirements. The registered contract SHALL be available to the Agent when selecting an action.

#### Scenario: Agent receives available tools
- **WHEN** a Run builds its decision Context
- **THEN** the Context includes only tools allowed for that Run and their input contracts

### Requirement: ToolExecutor validates and executes calls

The ToolExecutor SHALL validate tool-call arguments, enforce the registered permission and policy checks, execute the selected tool within configured resource limits, and return a normalized result containing success or failure, structured output, error information, duration, and an execution identifier.

#### Scenario: Valid low-risk call
- **WHEN** the Agent calls an allowed read-only tool with valid arguments
- **THEN** the ToolExecutor executes it and records a normalized successful result in the Run trace

#### Scenario: Invalid or disallowed call
- **WHEN** a tool call fails schema validation or violates Run policy
- **THEN** the ToolExecutor does not execute it and returns a structured rejection result

### Requirement: High-risk tools require controlled execution

The system SHALL classify shell execution and file writes as high-risk by default. The ToolExecutor MUST apply sandbox, path, command, timeout, and approval controls before executing a high-risk call.

#### Scenario: Write requires approval
- **WHEN** the Agent requests a write operation in a scope requiring approval
- **THEN** the Run enters waiting-for-approval and no file is changed until approval is granted

#### Scenario: Bash exceeds its limit
- **WHEN** a bash call exceeds its timeout or resource limit
- **THEN** the ToolExecutor terminates the call, records partial output where available, and returns a timeout or resource-limit failure

### Requirement: Tool side effects are auditable

The system SHALL record the selected tool, validated arguments or a redacted representation, policy decision, approval decision, result, and side-effect metadata in the Run trace.

#### Scenario: Tool call is replayed for inspection
- **WHEN** an operator inspects a completed Run
- **THEN** the operator can identify what tool was called, why it was permitted, what result it produced, and whether it changed files
