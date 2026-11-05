# V2 Architecture Assessment and Issue Register

**Repository:** `HissanUmar/Sandbox-agent`  
**Branch reviewed:** `master`  
**Review date:** 2026-11-04  
**Review type:** Static source review; tests were not executed.

---

## 1. Executive assessment

V2 has a good architectural foundation. Its central design is useful: define an environment, provision a real database and HTTP API, give the agent tools that call the API, and grade the final database state instead of trusting the agent's prose.

The separation between the generic `pipeline/` and domain-specific `environments/` is the right direction. The shop and hospital examples show that the same provisioning engine can support more than one domain without putting shop-specific tables or routes into the core.

**But V2 is not yet a fully generic, reliable environment framework.** It currently proves a narrow form of portability: two hand-authored environments can use the same SQLite/FastAPI provisioner. It does not yet prove that arbitrary business workflows can be expressed safely and correctly through the YAML model.

### Overall verdict

| Area | Assessment |
|---|---|
| Core separation | Good |
| Real database/API execution | Good foundation |
| Multi-domain portability | Partially demonstrated |
| Declarative expressiveness | Limited |
| Business-rule enforcement | Incomplete |
| State-based grading | Useful, but too weak for exact-state evaluation |
| Isolation and concurrency | Not supported |
| Test coverage | Insufficient for the V2 claims |
| V2 readiness | **Promising prototype; not complete** |

The README marks V2 complete. Based on the implementation reviewed, that status is too strong unless V2 is defined narrowly as “a first generic provisioner plus two example environments.” The broader goals—reusable multi-domain expansion, reliable state transitions, and meaningful state assertions—still have gaps.

---

## 2. What V2 gets right

### 2.1 The core abstraction is sound

The current architecture has three useful boundaries:

- `pipeline/` provisions databases, creates API services, validates configuration, and manages lifecycle.
- `environments/<domain>/` defines domain-specific schema, SQL endpoints, tools, runtime configuration, and prompts.
- `agent.py` runs the LLM/tool loop, while `grade.py` evaluates resulting state.

This is a good separation of concerns. The generic provisioner does not need to understand what an order or appointment means.

### 2.2 The agent acts through real APIs

The agent tools call FastAPI endpoints, and those endpoints execute SQL against a real SQLite database. This is materially stronger than mocked tools that return canned answers. State can persist across multiple tool calls during one run.

### 2.3 The same provisioner supports two domains

The shop and hospital configurations use the same `Sandbox` implementation. This is evidence that the core is not tightly coupled to one schema.

However, the environments still require hand-written Python tools, runtime modules, prompts, and SQL. So this demonstrates reuse of the execution engine, not fully automatic or code-free environment creation.

### 2.4 State-based grading is the right direction

Checking database state is better than judging only the agent's final text. The current grader is a useful starting point, but its assertions are currently presence-based rather than exact-state checks. See Issue 7.

---

## 3. Can a mature V2 architecture solve the problems V2 is meant to solve?

**Yes, for a defined class of stateful tool-use tasks. Not for every possible business environment without extending the design.**

A mature version of this architecture could support tasks such as:

- cancel an order only when its current status allows cancellation;
- create a charge and later refund it;
- create a shipment linked to an existing order;
- find an available doctor and schedule an appointment;
- execute multiple operations whose effects persist during a run;
- reset the environment to a known initial state;
- grade whether required database changes happened.

The design is capable of these workflows because it combines real state, controlled API operations, and a separate evaluator.

But the architecture does not make an agent correct by itself. It provides the environment in which the agent operates and the mechanism for measuring outcomes. Correctness still depends on:

1. **The environment enforcing its business rules.** The agent prompt must not be the only thing preventing invalid operations.
2. **The API model being expressive enough.** Current endpoints are mostly one SQL statement plus simple parameter binding and response mapping.
3. **The grader expressing the real task contract.** It must be able to check required changes, forbidden changes, counts, uniqueness, and relevant invariants.
4. **The runtime isolating each run.** Current module-level runtime state and process-wide environment mutation prevent safe concurrent runs.
5. **Tests proving the behaviour.** A successful demo task is not enough to prove that the framework handles invalid states, conflicts, and failure cases.

### The important boundary

V2 should aim to be a **declarative, constrained environment builder**, not a universal business-logic compiler.

YAML plus parameterized SQL can cover many CRUD and workflow tasks. More complex rules—overlapping appointments, inventory reservation, multi-step transactions, conditional workflows, or cross-resource invariants—need stronger primitives or domain-specific API code. That is not a failure of the architecture. It is a boundary that should be explicit.

A good mature design can preserve a generic core while allowing an environment to provide custom validation or transaction logic where declarative SQL is not enough.

---

## 4. Issues found in the current V2 implementation

Severity guide:

- **Critical:** breaks a central architecture contract or can make a run use the wrong instructions/state.
- **High:** can produce incorrect business state or misleading grading.
- **Medium:** limits portability, reliability, or test confidence.
- **Low:** documentation or maintainability issue.

### Issue 1 — The environment-specific system prompt is ignored

**Severity:** Critical  
**Files:** `agent.py`, `run_agent.py`, `grade.py`

`run_agent.py` loads `environments/<env>/prompt.md` and passes it to `agent.main(..., system_prompt)`. `grade.py` does the same.

But `agent.main()` builds the messages with the module-level `SYSTEM` constant:

```python
messages = [SystemMessage(content=SYSTEM), HumanMessage(content=task)]
```

The `system_prompt` argument is never used.

The hardcoded `SYSTEM` text describes a shop operations assistant, a shop database, `run_sql`, orders, customers, payments, and shipping. The hospital prompt therefore has no effect. In fact, the loaded shop prompt also has no effect.

**Impact:** The agent is not actually configured by the selected environment. This breaks a central part of the intended separation between generic agent logic and domain-specific instructions.

**Required fix:** Build the system message from the `system_prompt` argument. Remove the obsolete shop-specific global prompt, or keep only a genuinely domain-neutral base prompt and combine it deliberately with the environment prompt.

**Acceptance test:** Run the same generic agent loop with shop and hospital prompts and assert that the exact supplied prompt is used.

---

### Issue 2 — Zero-row updates cannot distinguish “not found” from “conflict”

**Severity:** High  
**Files:** `pipeline/sandbox.py`, both environment YAML files

For a SQL endpoint that does not use `RETURNING`, the handler selects an outcome like this:

```python
if affected == 0:
    key = "on_not_found" if "on_not_found" in _ep else "on_conflict"
```

A zero-row update can mean either:

- the target record does not exist; or
- the record exists, but its current state does not allow the operation.

If an endpoint declares both `on_not_found` and `on_conflict`, the current code always selects `on_not_found`. The conflict response is therefore unreachable for those cases.

The shop cancellation endpoint and hospital cancellation endpoint both declare these two outcomes.

**Impact:** An already-cancelled or otherwise non-cancellable record can be reported as missing. The API contract promises a distinction that the implementation cannot make.

**Required fix:** Add an explicit way to distinguish the cases. Options include a declarative precondition/existence query, a supported multi-statement transaction, or a custom handler hook. Do not infer “not found” from `rowcount == 0` alone.

**Acceptance test:** Verify all three cases for cancellation: existing cancellable record succeeds; missing record returns 404; existing non-cancellable record returns 409.

---

### Issue 3 — Hospital appointment creation does not enforce doctor availability

**Severity:** High  
**File:** `environments/hospital/sandbox.yaml`

`GET /doctors` filters out doctors who already have an appointment at the requested time. But `POST /appointments` inserts an appointment without checking that the doctor is still available.

The agent is expected to call the availability tool first. That is not enough to enforce the rule: another operation could reserve the slot after the lookup, or the agent could call the insert endpoint directly.

**Impact:** The database can contain two scheduled appointments for the same doctor at the same time. The environment can therefore accept a state that its own availability API says should be unavailable.

**Required fix:** Enforce the invariant at the write boundary, not only in the read endpoint or prompt. Prefer a database constraint where the rule can be represented, or a transaction/custom endpoint that checks availability and inserts atomically. Consider cancelled appointments when defining the invariant.

**Acceptance test:** Attempt two bookings for the same doctor and time. The first should succeed; the second should be rejected with a meaningful conflict response. Also verify that a cancelled appointment no longer blocks the slot.

---

### Issue 4 — Hospital tool says availability is optional, but the API requires it

**Severity:** Medium  
**Files:** `environments/hospital/tools.py`, `environments/hospital/sandbox.yaml`

The Python tool declares:

```python
def list_doctors(available_at: str = None):
```

Its docstring says availability filtering is optional. But the YAML endpoint declares `available_at` with `required: true`.

Calling `list_doctors()` without a time therefore reaches the API without the required query parameter and returns a 400 response.

**Impact:** The tool schema and API contract disagree. The agent may reasonably call the tool with no argument based on its signature and description, but the API rejects it.

**Required fix:** Decide whether the time is optional. If optional, make the YAML parameter optional and make the SQL handle a missing value correctly. If required, remove the Python default and make the tool description clear.

**Acceptance test:** Test both the no-argument call and the time-filtered call according to the chosen contract.

---

### Issue 5 — Response templates do not substitute request parameters

**Severity:** Medium  
**File:** `pipeline/sandbox.py`

The SQL response resolver handles `{rows}` and `{rows[0]}`. It recursively resolves dictionaries and lists, but it does not substitute request parameters.

For example, the shop cancellation YAML contains:

```yaml
message: "Order {id} does not exist"
```

The SQL handler passes only query result rows into `_resolve_body()`. The `{id}` placeholder is not replaced, so the literal placeholder can reach the caller.

There is a `_substitute()` helper for the legacy mock API path, but it is not used for SQL endpoint outcomes.

**Impact:** Declared error messages can be misleading or contain unresolved placeholders.

**Required fix:** Define one documented response-template model that supports only explicitly allowed values (for example, request parameters and result rows), and use it consistently. Avoid unrestricted string evaluation.

**Acceptance test:** Trigger a missing-order response and assert that the actual order ID appears in the returned message.

---

### Issue 6 — Process-wide and module-wide state is not safe for concurrent runs

**Severity:** Medium  
**Files:** `pipeline/sandbox.py`, `environments/shop/_runtime.py`, `environments/hospital/_runtime.py`

`Sandbox.run()` calls `os.environ.update(env)` and does not restore the previous environment after the run. This leaves `SB_API_*` values in the process after teardown.

The environment runtime modules also store API URLs in a module-level `_ENV` dictionary. `configure()` clears and replaces that dictionary. Two simultaneous runs using the same environment can overwrite each other's URLs.

**Impact:** Sequential runs can leave stale configuration behind, and concurrent runs can send tool calls to the wrong sandbox. This conflicts with the idea that each run has its own isolated state.

**Required fix:** Pass a per-run runtime/context object to tools instead of using process-global state. At minimum, stop mutating `os.environ` and make the runtime instance-specific. Treat concurrency as unsupported until this is fixed and tested.

**Acceptance test:** Run two instances of the same environment concurrently, mutate both databases differently, and prove that each tool only reaches its own API/database.

---

### Issue 7 — The grader checks expected rows exist, not that the expected state is exact

**Severity:** High  
**File:** `grade.py`

The grader selects rows matching each expected dictionary and checks whether at least one row matches each expected item.

This supports positive assertions such as “there is an appointment for patient 3 at this time.” It does not prove that:

- there is only one such appointment;
- no duplicate appointment was created;
- forbidden rows or changes are absent;
- a table has the exact expected contents;
- a count or aggregate is correct;
- an invariant across multiple rows holds.

For example, if the task expects one appointment but the agent creates two duplicate appointments, the current expected-row check can still pass.

**Impact:** A task can receive PASS while the database contains extra or invalid state. This weakens the main promise of state-based grading.

**Required fix:** Extend task assertions to support exact or partial modes explicitly, including at least row count, expected absence, uniqueness, and table/row predicates. Keep partial matching available when that is genuinely what a task needs.

**Acceptance test:** Add a task where the expected row exists alongside an unwanted duplicate. The grader must fail in exact/unique mode.

---

### Issue 8 — Environment selection is not fully plug-in driven

**Severity:** Medium  
**Files:** `run_agent.py`, `grade.py`

The CLI restricts `--env` to `shop` and `hospital` using a hardcoded `choices` list. The runner also assumes a fixed folder and module layout for every environment.

The generic provisioner is reusable, but adding an environment still requires editing the runner's choices and following its import/file conventions.

**Impact:** The core is more reusable than the application entry point. This is not a blocker for two examples, but it weakens the claim of arbitrary domain expansion.

**Required fix:** Discover valid environment packages/configurations from a known environments directory or a small registry. Validate that the required files exist and produce a clear error for an unknown environment.

**Acceptance test:** Add a third minimal environment without changing `run_agent.py` and run it through the same entry point.

---

### Issue 9 — The declarative schema supports only a small set of database constraints

**Severity:** Medium  
**Files:** `pipeline/sandbox.py`, `pipeline/validate.py`

`_build_create_table()` currently handles column type, primary key, and foreign-key references. The YAML model does not currently express common constraints such as `NOT NULL`, `UNIQUE`, `CHECK`, or defaults.

The validator also does not fully validate schema declarations or confirm that referenced columns exist.

**Impact:** Many business invariants cannot be represented directly in the database schema. They must be encoded in endpoint SQL or custom code, and invalid configurations may fail only during provisioning or execution.

**Required fix:** Extend the schema model deliberately, with validation and tests for each supported constraint. Do not add arbitrary SQL fragments as an unvalidated shortcut.

**Acceptance test:** Add valid and invalid configurations for each supported constraint and verify both provisioning-time validation and runtime enforcement.

---

### Issue 10 — Test coverage does not verify the hospital environment or the main failure paths

**Severity:** High  
**File:** `pipeline/test_sandbox.py`

The current pipeline test suite defaults to `environments/shop/sandbox.yaml`. Its six tests cover shop provisioning, cancellation persistence, foreign keys, reset consistency, tool error propagation, and partial-failure cleanup.

It does not provide equivalent hospital integration tests. It also does not test several important contracts identified above, including prompt selection, conflict-vs-not-found behaviour, duplicate appointment prevention, or exact-state grading.

The README also references `docs/v2_acceptance_checks.md` and `docs/stabilization_checklist.md`, but those paths could not be fetched from the reviewed `master` branch. The README's project tree also lists a root `test_sandbox.py`, which could not be fetched.

**Impact:** The current tests are not enough to support the claim that V2 works across domains or that the key environment invariants are enforced.

**Required fix:** Add LLM-free integration tests for both environments and focused tests for the agent prompt wiring and grader. Reconcile README references with files that actually exist.

**Acceptance test:** A clean test run should exercise both shop and hospital and include success, invalid input, missing record, conflict, duplicate operation, reset, and cleanup cases.

---

### Issue 11 — Server startup and shutdown are not robustly bounded

**Severity:** Medium  
**File:** `pipeline/sandbox.py`

The server startup loop waits until `server.started` becomes true but has no timeout or explicit startup-failure check. Shutdown sets `should_exit`, sleeps for a fixed short interval, and then removes the run directory without joining the server threads.

The free-port helper also releases the selected port before Uvicorn binds it, leaving a small port-allocation race.

**Impact:** A startup failure can hang the run. During teardown, a server thread may still be active while its database files are being removed. The free-port race can cause intermittent bind failures.

**Required fix:** Use bounded startup with an error path, retain and join server threads during shutdown, and use a safer socket lifecycle where practical.

**Acceptance test:** Simulate startup failure and slow shutdown. The sandbox should fail within a bounded time and leave no active server or run directory.

---

### Issue 12 — SQL endpoint configuration is not validated deeply enough

**Severity:** Medium  
**File:** `pipeline/validate.py`

The validator checks broad structure, parameter types/sources, and the count of `?` placeholders. It does not verify that:

- SQL refers to valid tables and columns;
- declared outcome objects contain valid status/body fields;
- response placeholders are valid;
- the SQL parameter count is correct when `?` appears inside a quoted string or SQL comment;
- the configured schema can actually be provisioned and used by the endpoint.

The placeholder count is a simple `sql.count("?")`, not a SQL-aware check.

**Impact:** Some configuration errors are found only when a request executes. A question mark inside a literal or comment can also make the placeholder count incorrect.

**Required fix:** Strengthen static validation where possible, and add a configuration smoke test that provisions the database and exercises every declared endpoint with valid sample parameters. Clearly separate checks that can be done statically from checks that require SQLite.

**Acceptance test:** Invalid table/column references and malformed outcomes should be rejected before an agent task starts; valid endpoints should pass a smoke test.

---

### Issue 13 — The environment definition is not fully code-free

**Severity:** Low / architectural limitation  
**Files:** `environments/*/sandbox.yaml`, `environments/*/tools.py`, `environments/*/_runtime.py`

The README describes domain definitions as declarative YAML, but a usable environment also needs hand-written Python tool wrappers and runtime modules. SQL itself is also executable logic embedded in YAML.

**Impact:** V2 reduces the amount of framework code needed for a new domain, but it does not let a user define every environment using YAML alone.

**Required decision:** Either describe V2 accurately as “YAML-configured database/API provisioning with Python tool adapters,” or design a generic tool-generation mechanism. Do not claim full code-free environment authoring unless it is actually supported.

---

## 5. Known design limitations versus implementation defects

These should not be mixed together.

### Implementation defects to fix

1. Environment prompt ignored by the agent.
2. Conflict and not-found outcomes are not distinguished.
3. Hospital appointment write does not enforce availability.
4. Hospital tool/API optionality mismatch.
5. Request placeholders are not resolved in SQL response bodies.
6. Global runtime/environment state can leak or collide.
7. Grader can pass despite extra/duplicate state.
8. Tests do not cover hospital and critical failure paths.
9. Server lifecycle has no bounded startup/join.
10. Configuration validation is incomplete.

### Current design limits to address deliberately

1. The YAML endpoint model is mostly one SQL statement with simple positional parameters.
2. The schema model supports only a small subset of database constraints.
3. Tool wrappers and runtime files are still hand-written per environment.
4. Exact-state and invariant grading are not yet part of the task language.
5. Concurrent execution and strong process/container isolation are not supported.
6. More complex business workflows may need custom transactional endpoint logic.

These design limits are not necessarily bugs. They define what the current V2 model can and cannot express.

---

## 6. Recommended order of work

Do not start V3 isolation/container work before the V2 correctness contracts are reliable. Fix in small batches.

### Batch 1 — Make environment execution correct

Files:
- `agent.py`
- `pipeline/sandbox.py`
- `environments/hospital/sandbox.yaml`
- `environments/hospital/tools.py`

Work:
- Use the supplied environment prompt.
- Distinguish missing records from invalid-state conflicts.
- Enforce doctor availability during appointment creation.
- Make the hospital tool/API contract consistent.
- Resolve request parameters in response templates.

### Batch 2 — Make grading trustworthy

Files:
- `grade.py`
- task YAML files
- new or updated grader tests

Work:
- Add explicit partial versus exact assertions.
- Support absence and uniqueness/count checks.
- Add a duplicate-appointment grading test.

### Batch 3 — Prove portability and lifecycle

Files:
- `pipeline/test_sandbox.py`
- `pipeline/sandbox.py`
- `pipeline/validate.py`
- README/docs as needed

Work:
- Add hospital integration tests.
- Test configuration validation and endpoint smoke tests.
- Bound server startup and join server threads during teardown.
- Remove process-global runtime coupling before claiming concurrent-run support.
- Correct README claims and missing documentation references.

Keep each batch small. Run the LLM-free tests after every batch. Run the LLM grading tasks only after the environment and grader tests pass.

---

## 7. V2 completion criteria

V2 should be considered complete when all of the following are demonstrated:

- [ ] A new domain can be added without modifying generic pipeline code.
- [ ] The same runner can load a new environment without editing a hardcoded environment list.
- [ ] Environment-specific prompts are actually passed to the agent.
- [ ] Multiple databases and APIs can be provisioned from one environment configuration.
- [ ] Supported schema constraints are validated and enforced.
- [ ] Invalid state transitions are rejected by the environment, not merely discouraged by prompts.
- [ ] Missing-record and conflict outcomes are distinguishable.
- [ ] State persists across tool calls and resets deterministically between runs.
- [ ] The grader can check both required and forbidden state, including uniqueness/count where needed.
- [ ] Shop and hospital have LLM-free integration coverage.
- [ ] Server startup, failure cleanup, and teardown are bounded and tested.
- [ ] Documentation describes actual capabilities and limitations.

**Concurrency and container/process isolation can remain V3 goals**, but V2 must clearly state that concurrent runs are unsupported until the global runtime state is removed.

---

## 8. Final conclusion

The V2 architecture is worth continuing. Its strongest decision is the separation of a generic environment provisioner from domain-specific definitions and agent tools. Real APIs backed by real database state, combined with state-based grading, are a credible foundation for evaluating agents on operational tasks.

The current implementation is still a prototype, not yet a dependable general-purpose framework. The most important gaps are not a reason to discard the architecture. They are missing correctness guarantees around prompt wiring, business invariants, outcome semantics, grading strength, and test coverage.

**Recommendation:** Keep the architecture. Tighten the V2 contracts and prove them with tests before moving to V3. A mature version can solve the class of stateful tool-use problems V2 targets, provided it remains explicit about the limits of declarative SQL and gives environments a safe way to enforce complex business rules.
