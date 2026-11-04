# Stabilization Checklist — Remaining Items

**Status:** Items 1–3 of the original checklist are either in progress or complete. This document details the remaining items, defines the criteria for "done" for each, and outlines the required implementation changes.

---

## 1. Reference-Existence Check in `validate.py`

* **Checklist Line:** *Invalid references produce useful errors*
* **Priority:** High
* **Effort:** ~15 lines in `validate.py`, 2 test cases (under 30 minutes)
* **Dependencies:** None

### Current State
`validate()` verifies that `apis.<x>.database` names a declared database and that seed rows contain exactly the declared columns. However, it does **not** check whether `columns.<c>.references: table.column` points to an existing table and column within the same configuration. 

Consequently, typos such as `references: custmers.id` pass validation silently and fail later during `CREATE TABLE` execution with SQLite’s less informative `"no such table"` error.

### What "Done" Looks Like
Running the validation script against a broken configuration:

```bash
python pipeline/validate.py pipeline/sandbox.yaml
```

Prints a single, clear error line identifying the invalid target and listing valid options prior to creating any resources.

### Required Changes
1. **`pipeline/validate.py`:** Update `_validate_table` to accept the complete `all_tables` mapping (`name → table config`). Add a loop over `columns` to inspect dictionary-shaped column specifications:
   - Ensure any `"references"` entry follows the `"table.column"` format (contains exactly one dot).
   - Require the referenced table to exist in `all_tables`.
   - Require the referenced column to exist in `all_tables[ref_tbl]["columns"]`.
   - On failure, raise a `ConfigError` indicating the exact location (`databases.<db>.tables.<tbl>.columns.<col>.references`) and listing available tables and columns.
2. **`pipeline/validate.py`:** Update `_validate_databases` to build `all_tables` once and pass it down.
3. **`test_validate.py`:** Add two test cases expecting a `ConfigError` containing the offending name:
   - Case 1: Referenced table is incorrect.
   - Case 2: Referenced column is incorrect.

---

## 2. Foreign Key Ordering Guard in `sandbox.py`

* **Checklist Line:** *Relationships and foreign keys work*
* **Priority:** High
* **Effort:** ~30 lines in `sandbox.py`, 1 test case (~1 hour including testing)
* **Dependencies:** Item 1 (ensures malformed `references:` values fail at validation rather than during topological sorting)

### Current State
Table creation in `Sandbox.run()` iterates over `dbcfg["tables"]` in YAML declaration order. This currently works only because `customers` happens to be declared before `orders`, and `orders` before `shipments`. 

If the YAML is reordered—or if a new table referencing a later one is added— execution fails with `sqlite3.OperationalError: no such table`.

### What "Done" Looks Like
Reordering tables in `sandbox.yaml` (e.g., placing `shipments` first) still yields a working sandbox. Seed insertion succeeds because table iteration runs in dependency order rather than declaration order.

### Required Changes
1. **`sandbox.py`:** Add a helper function `_topo_sort_tables(tables: dict) -> list[str]`:
   - Build a dependency graph where each table's dependencies are extracted from any `columns.<c>.references` fields.
   - Implement Kahn's algorithm or DFS post-order traversal (~20 lines).
   - Detect cycles and raise a descriptive `ConfigError` (or `RuntimeError`) naming the cyclic loop.
2. **`sandbox.py`:** In `run()`, update the table loop:
   ```python
   # Replace:
   # for tbl, t in dbcfg["tables"].items():
   # With:
   for tbl in _topo_sort_tables(dbcfg["tables"]):
       t = dbcfg["tables"][tbl]
   ```
3. **`sandbox.py`:** Seed inserts will naturally execute in the correct sequence as they share the same sorted loop.
4. **`test_sandbox.py`:** Add a test verifying that declaring `shipments` before `orders` in YAML executes successfully.

> **Known Limitation to Document:**  
> Topological sorting orders table creation, but a seed row referencing a nonexistent parent ID (e.g., `customer_id: 999`) will still trigger `FOREIGN KEY constraint failed` upon insertion. This is expected behavior; tests should assert this failure rather than suppress it. The YAML must provide internally consistent seed data.

---

## 3. Parameter Substitution in `_resolve_body`

* **Checklist Line:** *Invalid requests are handled* (partial)
* **Priority:** Medium
* **Effort:** ~10 lines in `sandbox.py`, 1 test case (under 30 minutes)
* **Dependencies:** None

### Current State
`_resolve_body` currently only handles static placeholders like `"{rows}"` and `"{rows[0]}"`. Parameterized error bodies like `"Order {id} does not exist"` are sent with the literal template string `{id}`. 

As a result, the agent receives `"Order {id} does not exist"` instead of `"Order 100 does not exist"`. While previously treated as a cosmetic issue, this creates functional problems when evaluating error message quality in test suites.

### What "Done" Looks Like
A request such as `POST /orders/100/cancel` returns:

```json
{
  "error": "not_found",
  "message": "Order 100 does not exist"
}
```

instead of `"Order {id} does not exist"`.

### Required Changes
1. **`sandbox.py`:** Update `_resolve_body` signature and invocation to accept parameters:  
   `_resolve_body(body_tmpl, rows, params)` where `params` is a dictionary mapping parameter names to values.
2. **`sandbox.py`:** In the string branch of `_resolve_body`, after handling `{rows}` and `{rows[0]}`, perform regex substitution using `re.sub(r"\{(\w+)\}", ...)` to replace `{name}` with `params.get(name, m.group(0))`.
3. **`sandbox.py`:** In `_build_sql_app`'s route handler, construct the parameter mapping:
   ```python
   param_map = dict(zip(_ep.get("params", {}).keys(), values))
   ```
   Pass `param_map` into every `_resolve_body` call.
4. **`test_sandbox.py`:** Add a test checking `POST /orders/999/cancel` to verify that `message == "Order 999 does not exist"`.

> **Note:** This change does not address 404/409 status code conflation (Item 8 in accepted gaps). It exclusively addresses literal parameter string substitution.

---

## 4. Second Database Configuration in YAML

* **Checklist Line:** *Multiple databases can be configured*
* **Priority:** Medium
* **Effort:** ~15 lines of YAML (under 15 minutes)
* **Dependencies:** None

### Current State
`pipeline/sandbox.yaml` currently defines only one database (`shop`). Although the creation loop in `sandbox.py` supports multiple databases, multi-database functionality remains unverified in practice.

### What "Done" Looks Like
`sandbox.yaml` defines both `shop` and `analytics`. Executing `sb.run()` initializes and seeds SQLite databases for both entries, and exports `SB_API_ANALYTICS` if an API references it. 

Existing agent tasks execute without modification (as none currently target `analytics`), while `test_provisioning.py` (Item 5) verifies both files and their row counts.

### Required Changes
1. **`pipeline/sandbox.yaml`:** Add a second database definition under `databases:`:
   ```yaml
   analytics:
     type: sqlite
     tables:
       events:
         columns: { id: integer, name: text, ts: text }
         seed:
           - { id: 1, name: "page_view", ts: "2026-10-01" }
           - { id: 2, name: "click", ts: "2026-10-02" }
   ```
2. *(Optional)* Add a simple SQL API endpoint (`type: sql`, `database: analytics`) exposing `GET /events` to make the second database reachable. 
   - *If added:* Include the corresponding tool (`list_events`) in `agent_tools.py` and verify with `validate()`.
   - *If omitted:* Leave the second database unreferenced. Validation only flags missing database references when an API attempts to point to a non-existent database.

---

## 5. Integration Suite in `test_provisioning.py`

* **Checklist Line:** *Automated tests cover configuration and provisioning*
* **Priority:** High
* **Effort:** ~40 lines in a new test file (~1 hour)
* **Dependencies:** Items 1–4

### Current State
Automated end-to-end provisioning tests are absent. Provisioning changes currently rely on manual runs of `run_agent.py` and manual inspection of output traces. While `test_validate.py` covers configuration structure, runtime creation and server initialization are untested.

### What "Done" Looks Like
Running `python test_provisioning.py` exits with code 0 and outputs affirmative status lines verifying that:
* `sb.run()` initializes without errors.
* `SB_API_ORDERS`, `SB_API_PAYMENTS`, and `SB_API_SHIPPING` are present in environment variables.
* Database files are created in the targeted run directory.
* Seed tables contain expected row counts (`customers`: 10, `orders`: 26, `charges`: 0, `shipments`: 0).
* Configured APIs respond correctly to HTTP requests (`GET /rates` -> 200, `GET /orders` -> 200).
* Temporary run directories clean up upon completion.

### Required Changes
1. **`test_provisioning.py` (New File):** Create standard testing routine at project root:
   ```python
   import os
   import sqlite3
   import requests
   from sandbox import Sandbox

   EXPECTED = {
       "customers": 10, 
       "orders": 26, 
       "charges": 0, 
       "shipments": 0,
   }

   def test_provisioning():
       sb = Sandbox.from_file("pipeline/sandbox.yaml")
       with sb.run() as env:
           # 1. Verify API handle environment variables
           for key in ("SB_API_ORDERS", "SB_API_PAYMENTS", "SB_API_SHIPPING"):
               assert key in env, f"Missing key in env: {key}"

           # 2. Verify API availability
           assert requests.get(f"{env['SB_API_ORDERS']}/orders").status_code == 200
           assert requests.get(f"{env['SB_API_SHIPPING']}/rates").status_code == 200

           # 3. Verify record counts via API responses
           orders = requests.get(f"{env['SB_API_ORDERS']}/orders").json()
           assert len(orders) == 26, f"Expected 26 orders, got {len(orders)}"

       print("[PASS] All provisioning tests passed successfully.")

   if __name__ == "__main__":
       test_provisioning()
   ```
2. **Database Access Decision:** To verify database rows directly on disk instead of via API queries, `sandbox.py` must expose internal database file paths. To preserve the boundaries preventing the agent from directly inspecting DB files, introduce a `SANDBOX_TEST=1` environment variable flag. When set, `run()` exports `SB_DB_<NAME>` variables for test access.

---

## 6. Concurrent Environment Isolation

* **Checklist Line:** *Two environments can run without interfering*
* **Priority:** Deferred
* **Effort:** ~30 lines across 3 files (~4 hours)
* **Dependencies:** None (Recommended to execute last due to wide scope across tools)

### Current State
`Sandbox.run()` modifies process-level state via `os.environ.update(env)`. If two `sb.run()` contexts execute concurrently within a single process, their handles overwrite each other. 

While this presents a design issue, it does not currently block workflows since parallel sandbox executions are not actively used.

### What "Done" Looks Like
Two concurrent `sb.run()` blocks can exist within the same process simultaneously without environment variable leakage or handle collision.

### Required Changes
1. **`sandbox.py`:** Retain `env` yielding in `Sandbox.run()`, but remove the global `os.environ.update(env)` call.
2. **`agent_tools.py`:** Replace direct `os.environ["SB_API_ORDERS"]` lookups with a module-level context dictionary (`_ENV`) populated via a `configure(env)` call:
   ```python
   _ENV = {}

   def configure(env):
       _ENV.update(env)

   def _api(name):
       return _ENV.get(f"SB_API_{name.upper()}", os.environ.get(f"SB_API_{name.upper()}"))
   ```
3. **`agent.py`:** Maintain signature for `main(task)` while using updated tool execution paths.
4. **`run_agent.py`:** Explicitly inject handles into tool modules:
   ```python
   with sb.run() as env:
       agent_tools.configure(env)
       import agent
       agent.main(TASK)
   ```
5. **Backward Compatibility:** Ensure `_ENV` falls back to `os.environ` if unconfigured, preserving backwards compatibility during migration.

> **Recommendation:** Mark as `[~] deferred`. Address this refactor when parallel workflow execution becomes a functional requirement.

---

## Executive Summary & Plan

### Summary Matrix

| # | Item | Files Touched | Effort | Priority |
|---|---|---|---|---|
| 1 | Reference-existence check | `validate.py`, `test_validate.py` | 30 min | High |
| 2 | FK ordering guard | `sandbox.py`, `test_sandbox.py` | 1 hr | High |
| 3 | `_resolve_body` params | `sandbox.py`, `test_sandbox.py` | 30 min | Medium |
| 4 | Second DB in YAML | `sandbox.yaml` | 15 min | Medium |
| 5 | Provisioning test suite | `test_provisioning.py`, `sandbox.py` (optional) | 1 hr | High |
| 6 | Environment isolation | `sandbox.py`, `agent_tools.py`, `run_agent.py` | 4 hr | Deferred |

### Target Checklist State After Implementation

Upon completing Items 1, 2, 4, and 5:

- [x] YAML schema validation works
- [x] Invalid references produce useful errors
- [x] Multiple databases can be configured
- [x] Relationships and foreign keys work
- [x] Automated tests cover configuration and provisioning
- [~] Two environments can run without interfering *(Deferred)*

### Next Steps & Additional Verification
Remaining manual checklist items (CRUD operations, persistence, agent integrations) are currently validated manually in working environments. 

To complete test coverage without needing immediate environment isolation refactoring, add an end-to-end test suite (`test_e2e.py`, ~15 lines) that executes `cancel_order(101)`, queries `list_orders('pending')`, and asserts that order `101` is removed.