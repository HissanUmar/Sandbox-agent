# Sandbox-Agent Roadmap

## Project Direction

**Sandbox-Agent** is a declarative environment builder for tool-using AI
agents.

A developer defines a stateful business environment through
configuration. The framework provisions databases and APIs, exposes
controlled operations to an agent, and allows the resulting state to be
inspected and reset.

The long-term goal is to let developers create reproducible environments
for agent development, testing, and evaluation without manually building
a new backend for every use case.

## Guiding Principles

1.  **Configuration-driven:** Environment-specific resources should be
    described declaratively.
2.  **Generic core:** Core provisioning should not contain
    business-specific assumptions.
3.  **Real state:** Agents should interact with actual stateful
    databases and APIs, not only mocked responses.
4.  **Controlled capabilities:** Agents should access operations through
    explicit tools and API contracts.
5.  **Reproducibility:** Environments should start from known seed data
    and support reliable reset.
6.  **Incremental development:** Add capabilities when real environments
    or tasks expose a need. Avoid speculative complexity.

------------------------------------------------------------------------

# V2 --- Environment Generalization

## Objective

Prove that the existing framework can support substantially different
business environments without changes to its core provisioning engine.

The first version established the basic pipeline:

-   Read environment configuration.
-   Provision databases and tables.
-   Seed initial data.
-   Create API endpoints.
-   Expose API operations as agent tools.
-   Let an agent perform stateful operations.

V2 should generalize this foundation rather than replace it.

## V2.1 --- Remove Business-Specific Assumptions

Separate the project into clear responsibilities:

-   **Core sandbox infrastructure:** Configuration loading, validation,
    database provisioning, API creation, lifecycle, cleanup.
-   **Environment definition:** Tables, seed data, endpoint definitions,
    parameters, and response behavior.
-   **Agent integration:** Environment-specific tools, tool
    descriptions, and agent instructions.

The core provisioning engine should not need to know whether it is
creating an e-commerce, hospital, banking, or another business
environment.

Automatic tool generation is not a requirement for this milestone.
Environment-specific tools may remain separately defined while the
architecture is being proven.

### Acceptance criteria

-   Core provisioning code contains no unnecessary business-specific
    assumptions.
-   Environment-specific tools and instructions are kept outside the
    core provisioning layer.
-   Existing e-commerce behavior continues to work.

## V2.2 --- Prove Portability With a Second Environment

Create a second, meaningfully different environment, such as hospital
management.

Possible entities:

-   Patients
-   Doctors
-   Departments
-   Appointments

Example agent task:

> Find an available doctor and schedule an appointment for a patient.

Use the existing provisioning engine. Prefer changing only:

-   The environment YAML.
-   The environment-specific agent tools.
-   Agent instructions or task definitions, where needed.

Do not modify the core provisioning engine merely to accommodate the new
business domain. If changes to the core are necessary, identify the
missing generic capability and implement it deliberately.

### Acceptance criteria

-   The second environment provisions successfully.
-   Its APIs perform real database operations.
-   Related tables and their relationships work where required.
-   An agent can complete at least one task against the environment.
-   The original e-commerce environment still works.

## V2.3 --- Improve Configuration Expressiveness

Let the second environment reveal which configuration features are
genuinely missing.

Potential improvements include:

-   Multiple related tables and foreign-key relationships.
-   More flexible parameter validation.
-   Allowed-value constraints.
-   Clearer endpoint response definitions.
-   Better handling of optional parameters and filters.
-   Consistent error responses.

Do not implement every possible feature in advance. Prioritize
capabilities required by real environment definitions.

### Deferred capability: Generic aggregate endpoint

The generic aggregate endpoint remains **deferred, not abandoned**.

The current simple endpoints may not support analytical questions such
as counts, sums, or averages grouped by a field. A bounded aggregate
endpoint could eventually support these operations through validated,
whitelisted parameters.

Do not introduce unrestricted SQL merely to solve this limitation.
Revisit aggregation when recurring tasks demonstrate the need, for
example:

-   A required task cannot be completed correctly with existing
    endpoints.
-   The same grouping question appears in multiple forms.
-   Agents repeatedly miscount or calculate aggregates from raw records.

When implemented, aggregation should use explicitly allowed grouping
fields, metrics, columns, and filters. SQL identifiers must come from
trusted configuration and validated allowlists; values must be
parameterized.

## V2.4 --- Environment-Level Evaluation

Build on the existing ground-truth task definitions.

A task should describe:

-   The instruction given to the agent.
-   The initial environment or seed state.
-   The expected final state.
-   Any relevant constraints.

Evaluation should inspect the actual database state rather than relying
only on the agent's final natural-language response.

Example:

``` yaml
task:
  name: cancel_order
  input: "Cancel order 101"
  expected_state:
    orders:
      - id: 101
        status: cancelled
```

The exact schema can be refined during implementation.

### Acceptance criteria

-   At least one task can be evaluated against actual database state.
-   A correct state passes.
-   An incorrect state fails.
-   Evaluation results are repeatable after resetting the environment.

## V2 Completion Criteria

V2 is complete when:

1.  A second business environment can be defined and provisioned.
2.  Core provisioning code does not need business-specific modifications
    for that environment.
3.  Multiple databases and APIs work as declared.
4.  Required table relationships and constraints work.
5.  An agent can perform real operations through the exposed tools.
6.  The environment can be reset to its seed state.
7.  At least one task can be evaluated against expected database state.
8.  Existing e-commerce behavior remains functional.

------------------------------------------------------------------------

# V3 --- Isolation and Concurrent Environments

## Objective

Move from a useful local environment builder towards safer execution and
support for multiple independent environments.

Potential capabilities:

-   Run environments in isolated containers.
-   Separate processes and resources between environments.
-   Apply CPU, memory, storage, and execution-time limits.
-   Restrict network access.
-   Add environment-level authentication and access controls.
-   Improve startup readiness, shutdown, cleanup, and failure recovery.
-   Support multiple environments running concurrently without
    interference.

Security should be treated as a core requirement before allowing
untrusted agents or arbitrary code to execute.

### Acceptance criteria

-   One environment cannot access another environment's data or
    resources.
-   Resource limits and execution timeouts are enforced.
-   Failed startup and shutdown do not leave unmanaged resources.
-   Multiple environments can run independently.
-   Network access follows explicit policy.

V3 should introduce isolation only to the degree required by the
intended threat model. API-level restrictions and container isolation
solve different problems; containers alone do not automatically make an
environment secure.

------------------------------------------------------------------------

# V4 --- Agent Evaluation Framework

## Objective

Evolve the project from an environment builder into a framework that can
systematically test and compare agents.

Potential capabilities:

-   Reusable task suites.
-   Initial-state and expected-state definitions.
-   Automatic state-based grading.
-   Tool-call and execution traces.
-   Failure categorization.
-   Task success rates and other evaluation metrics.
-   Repeatable runs across different models or agent implementations.
-   Comparison reports.

Evaluation should distinguish between:

-   Whether the agent produced a convincing response.
-   Whether it called the correct tools.
-   Whether it actually achieved the required state.
-   Whether it respected environment constraints.

### Acceptance criteria

-   A task suite can be run repeatedly.
-   Results are based on verifiable outcomes.
-   Runs record enough information to diagnose failures.
-   Different agents or models can be compared using the same tasks and
    initial conditions.

------------------------------------------------------------------------

# V5 --- Developer Experience and Ecosystem

## Objective

Make the framework convenient for other developers to adopt and
integrate into their workflows.

Potential capabilities:

-   A clean command-line interface.
-   A documented configuration schema.
-   Reusable environment templates.
-   A Python SDK.
-   Clear setup and contribution documentation.
-   Integrations with common agent frameworks.
-   Optional MCP interfaces for exposing environment capabilities.
-   Optional local or hosted execution workflows.
-   Example projects and starter environments.

Possible user workflow:

``` text
1. Define an environment.
2. Validate its configuration.
3. Start the environment.
4. Connect an agent.
5. Run tasks.
6. Inspect traces and evaluation results.
7. Reset or stop the environment.
```

### Acceptance criteria

-   A new developer can follow the documentation to create and run an
    environment.
-   Example templates work without modifying core code.
-   Public interfaces and configuration formats are documented.
-   Integrations do not compromise the generic core.

------------------------------------------------------------------------

# Deferred and Out-of-Scope Items

These items should not distract from the current V2 objective.

  -----------------------------------------------------------------------
  Capability                          Current decision
  ----------------------------------- -----------------------------------
  Generic aggregate endpoint          Deferred until recurring need is
                                      demonstrated

  Unrestricted SQL tool               Rejected for the current bounded
                                      API approach

  Automatic tool generation           Future improvement; not required to
                                      prove V2

  Docker/container isolation          V3

  Multi-agent coordination            Not currently planned

  MCP integration                     Later, likely V5

  Multiple agent frameworks           Later, after core interfaces
                                      stabilize

  Web dashboard                       Not required for V2

  Cloud hosting                       Not required for V2
  -----------------------------------------------------------------------

A deferred feature is not necessarily rejected. Reconsider it when a
concrete use case justifies its complexity.

------------------------------------------------------------------------

# Development Rules

To keep development controlled and reduce unnecessary rework:

1.  Prefer small, focused changes.
2.  Aim to modify no more than 3--4 files in one implementation batch
    where practical.
3.  Preserve working behavior while adding new capabilities.
4.  Update requirements and this roadmap when architectural decisions
    change.
5.  Add tests for every new core capability.
6.  Prefer end-to-end verification over judging success from an LLM
    response alone.
7.  Do not generalize a feature until at least one concrete use case
    demonstrates the need.
8.  Keep the aggregate endpoint deferred unless its stated triggers
    occur.
9.  Do not claim security isolation until the relevant isolation
    controls have been implemented and tested.

------------------------------------------------------------------------

# Immediate Next Steps

Before or at the start of V2:

1.  Resolve any stale agent instructions or tool-registration
    mismatches.
2.  Ensure configuration validation is always performed before
    provisioning.
3.  Restore process environment variables after sandbox execution.
4.  Add bounded startup/readiness handling and reliable cleanup.
5.  Confirm that the existing e-commerce environment still passes its
    core tests.

Then proceed in this order:

1.  Separate core infrastructure from environment-specific definitions
    and tools.
2.  Build the hospital environment using the existing provisioning
    engine.
3.  Record any generic capability gaps exposed by that exercise.
4.  Implement only the necessary configuration improvements.
5.  Add state-based task evaluation.
6.  Verify that both environments work without regressions.

## Product Milestone

The central milestone is:

> A developer can describe a business environment in configuration,
> provision it with one command, connect an AI agent, execute real
> operations, inspect the resulting state, evaluate task success, and
> reset the environment without manually building a backend.

Achieving this reliably establishes a strong foundation for the later
isolation, evaluation, and developer-experience stages.
