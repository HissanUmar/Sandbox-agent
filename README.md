# Sandbox Agent

> **A declarative environment builder for tool-using AI agents.**

Describe a business environment in YAML — tables, seed data, API endpoints — and the framework provisions real databases and real HTTP services, hands the agent a set of tools that talk to those services, and grades the agent on the resulting database state rather than on its prose.

**No mocks. No hardcoded responses.** The agent never touches the database; it calls HTTP APIs, and the APIs read and write real state.

---

## Table of Contents

- [Overview](#overview)
- [Project Architecture](#project-architecture)
- [Getting Started](#getting-started)
  - [Installation & Setup](#installation--setup)
- [How the Sandbox Works](#how-the-sandbox-works)
  - [Lifecycle](#lifecycle)
  - [Endpoint Specification](#endpoint-specification)
  - [Configuration Validation](#configuration-validation)
- [Defining an Environment](#defining-an-environment)
- [Execution & Grading](#execution--grading)
  - [Running the Agent](#running-the-agent)
  - [State-Based Grading](#state-based-grading)
  - [Running the Test Suite](#running-the-test-suite)
- [Included Domains](#included-domains)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Design Principles](#design-principles)

---

## Overview

Most agent harnesses test against fixtures: a fake tool returns a canned string, and the agent's output is compared to an expected text string. That works for toy tasks but fails for stateful workflows because the agent never has to reason about **consequences**.

Sandbox Agent takes the opposite approach. Each run provisions:
- **SQLite databases**, created and seeded fresh from YAML declarations.
- **FastAPI services** whose endpoints execute declared SQL statements against those databases (e.g., `POST /orders/101/cancel` executes `UPDATE orders SET status='cancelled' WHERE id = ?`).
- **LangChain tools** that talk to those services over HTTP. The agent sees only `SB_API_*` handles and never receives direct `SB_DB_*` connection access.

When the run finishes, everything is torn down. Every run starts from the same deterministic seed, writes persist for the run duration, and no state survives outside `sb.run()`.

---

## Project Architecture

```text
Sandbox-agent/
├── run_agent.py          # Entry point: --env shop|hospital, task string
├── agent.py              # Generic ReAct loop; takes tools + prompt
├── grade.py              # State-based grader for a given task file
├── test_sandbox.py       # Core stack integration tests
├── requirements.txt
├── .env
│
├── pipeline/             # Generic execution engine (no domain logic)
│   ├── __init__.py       # Exports Sandbox, validate, ConfigError
│   ├── sandbox.py        # Provisioner: YAML -> DBs + APIs + lifecycle
│   ├── validate.py       # Pure configuration validator
│   └── test_sandbox.py   # Core unit tests (run via python -m pipeline.test_sandbox)
│
├── environments/         # Business domain definitions
│   ├── shop/
│   │   ├── sandbox.yaml  # Schema, seed data, endpoints
│   │   ├── tools.py      # Agent tool definitions
│   │   ├── _runtime.py   # Runtime helpers (configure, api_url, call)
│   │   └── prompt.md     # Domain-specific system prompt
│   └── hospital/
│       ├── sandbox.yaml
│       ├── tools.py
│       ├── _runtime.py
│       └── prompt.md
│
├── tasks/                # Ground-truth task assertions
│   ├── shop/
│   │   └── cancel_order.yaml
│   └── hospital/
│       └── schedule_appointment.yaml
│
└── docs/                 # Design documentation & checklists
    ├── aggregate_endpoint.md
    ├── stabilization_checklist.md
    └── v2_acceptance_checks.md
```

> **Architecture Boundary:** `pipeline/` manages SQLite, HTTP, and SQL, and is agnostic to the LLM. `agent.py` handles the LLM and the ReAct reasoning loop without knowing tool implementations. `run_agent.py` ties both layers together.

---

## Getting Started

### Installation & Setup

1. **Set up a Python virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables (`.env`):**
   ```env
   OLLAMA_BASE_URL=https://<your-tunnel>.trycloudflare.com
   OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
   OLLAMA_API_KEY=ollama
   ```
   *Note: Update `.env` whenever your Cloudflare tunnel endpoint changes.*

---

## How the Sandbox Works

### Lifecycle

Inside the `with sb.run():` block, `sandbox.py` parses `environments/<name>/sandbox.yaml` and performs the following:

1. **Directory Isolation:** Creates a run-specific temporary directory (`self._run_dir`).
2. **Database Provisioning:** Reads `databases:`, creates SQLite database files, runs `CREATE TABLE` commands, and inserts seed data. Enforces relational integrity (`PRAGMA foreign_keys = ON`).
3. **Service Provisioning:** Reads `apis:`, launches FastAPI instances on random free ports, and maps endpoints to SQL statements binding parameters positionally (`?`).
4. **Handle Export:** Exports `SB_API_*` endpoints into environment variables while hiding database connection paths.
5. **Teardown:** On exit, stops servers, releases sockets, and purges temporary directories regardless of run success or failure.

### Endpoint Specification

Endpoints are declared declaratively in `sandbox.yaml`:

```yaml
- method: POST
  path: /orders/{id}/cancel
  params:
    id: { type: integer, required: true, min: 1, source: path }
  sql: "UPDATE orders SET status = 'cancelled' WHERE id = ? AND status IN ('pending','paid')"
  on_success:   { status: 200, body: { ok: true } }
  on_not_found: { status: 404, body: { error: "not_found", message: "Order {id} does not exist" } }
  on_conflict:  { status: 409, body: { error: "invalid_state", message: "Order {id} is not cancellable" } }
  on_invalid:   { status: 400, body: { error: "invalid_input" } }
```

- **`params`**: Parameter requirements (`type`, `source`, `required`, `min`) validated prior to SQL execution.
- **`sql`**: SQL statement with parameter placeholders (`?`).
- **Outcomes**: Mapped response shapes (`on_success`, `on_not_found`, `on_conflict`, `on_invalid`) selected by database state and execution results.

### Configuration Validation

Run strict schema and placeholder checking using `pipeline/validate.py`:

```bash
python pipeline/validate.py environments/shop/sandbox.yaml
```

Validation checks for structural integrity, placeholder counts matching parameter definitions, seed column consistency, and endpoint-to-database references.

---

## Defining an Environment

An environment is defined by four core files in `environments/<domain_name>/`:

1. **`sandbox.yaml`**: Environment schema, seed records, foreign keys, API routes, SQL queries, and response shapes.
2. **`tools.py`**: LangChain tool wrappers decorated with `@tool` that interface with endpoint URLs via runtime helpers.
3. **`_runtime.py`**: Per-environment helper module (`configure`, `api_url`, `call`).
4. **`prompt.md`**: Domain context and system instructions for the LLM agent.

---

## Execution & Grading

### Running the Agent

To launch an agent on a natural language task:

```bash
python run_agent.py "Cancel order 101, then list pending orders." --env shop
```

### State-Based Grading

Rather than parsing agent responses, task success is verified directly against the database state after execution:

```bash
python grade.py tasks/shop/cancel_order.yaml
```

**Task Spec Example (`tasks/shop/cancel_order.yaml`):**
```yaml
name: cancel_order_101
env: shop
db: shop
input: "Cancel order 101."
expected_state:
  orders:
    - id: 101
      status: cancelled
```

### Running the Test Suite

```bash
# Core pipeline integration tests
python -m pipeline.test_sandbox

# Shop domain verification
python grade.py tasks/shop/cancel_order.yaml

# Hospital domain verification
python grade.py tasks/hospital/schedule_appointment.yaml
```

---

## Included Domains

### Shop Domain (`environments/shop/`)
- **Tables**: `customers`, `orders`, `charges`, `shipments`.
- **Tools**: `list_orders`, `cancel_order`, `charge_customer`, `refund_charge`, `get_shipping_rates`, `create_shipment`.

### Hospital Domain (`environments/hospital/`)
- **Tables**: `departments`, `doctors`, `patients`, `appointments`.
- **Tools**: `list_doctors`, `schedule_appointment`, `cancel_appointment`.

---

## Known Limitations

- **No Arbitrary SQL**: Agent capabilities are limited to explicitly declared endpoints.
- **Positional Bindings**: Dual use of a single parameter requires declaring multiple `?` placeholders and bindings.
- **Dormant `on_conflict`**: Write operations cannot distinguish zero-row updates without dedicated precheck endpoints.
- **Environment Isolation**: Subprocess environment variables (`SB_API_*`) restrict execution to a single concurrent sandbox per process.
- **Host Process Scope**: Sandboxes run directly on host processes without container isolation.

---

## Roadmap

- [x] **V2**: Core abstraction for arbitrary multi-domain expansion and database-state assertions.
- [ ] **V3**: Containerization, process resource limits, non-polluting configuration pass-through, and concurrent environment execution.
- [ ] **V4**: Automated benchmark evaluation suites across multiple model architectures.
- [ ] **V5**: Developer tools (CLI, OpenAPI/JSON-Schema export, MCP server interface).

---

## Design Principles

1. **Configuration-driven**: Domain specifics are declared in code-free YAML configurations.
2. **Generic Core**: `pipeline/` contains zero business domain assumptions.
3. **Real State**: Real state transitions against real SQLite databases over HTTP endpoints.
4. **Controlled Capabilities**: Agents act strictly through structured endpoints rather than raw database queries.
5. **Reproducibility**: Runs start deterministically from identical seed states.
6. **State Over Prose**: Evaluation measures actual system state changes rather than LLM text output.