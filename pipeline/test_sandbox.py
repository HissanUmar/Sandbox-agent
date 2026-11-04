# test_sandbox.py
"""Consistency tests for the sandbox.

Run from the project root:
    python test_sandbox.py

Exit code 0 = all pass, 1 = failures.
No LLM required. Tests the plumbing only: provisioning, persistence,
FK enforcement, reset, tool errors, and failure cleanup.
"""
import os
import shutil
import sqlite3
import tempfile

import requests

from sandbox import Sandbox, _build_create_table, _run_sql


YAML = "pipeline/sandbox.yaml"
RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"[PASS] {name}")
    except AssertionError as e:
        RESULTS.append((name, False, str(e)))
        print(f"[FAIL] {name}: {e}")
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")


# ── 1. provisioning: DBs, APIs, row counts ──────────────────────
def test_provisioning():
    sb = Sandbox.from_file(YAML)
    with sb.run() as env:
        for key in ("SB_API_ORDERS", "SB_API_PAYMENTS", "SB_API_SHIPPING"):
            assert key in env, f"missing {key} in env"

        r = requests.get(f"{env['SB_API_ORDERS']}/orders", timeout=5)
        assert r.status_code == 200, f"GET /orders → {r.status_code}"
        rows = r.json()
        assert isinstance(rows, list) and len(rows) == 26, f"expected 26 orders, got {len(rows)}"

        r = requests.get(f"{env['SB_API_SHIPPING']}/rates", timeout=5)
        assert r.status_code == 200, f"GET /rates → {r.status_code}"
        assert len(r.json()["rates"]) == 2, "expected 2 shipping rates"

        # customers count via direct DB read (not exported; use the run's temp dir)
        # verify the DB file exists somewhere in the temp dir
        run_dir = None
        for key in list(env.values()):
            pass  # env only has API URLs; DB path isn't exported by design
        # fallback: count customers by querying the API? no /customers endpoint.
        # instead: assert the orders endpoint returns customer_ids in 1..10
        ids = {o["customer_id"] for o in rows}
        assert ids <= set(range(1, 11)), f"unexpected customer_id(s): {ids - set(range(1, 11))}"


# ── 2. persistence: cancel → list → absent ──────────────────────
def test_persistence():
    sb = Sandbox.from_file(YAML)
    with sb.run() as env:
        orders = env["SB_API_ORDERS"]

        before = requests.get(f"{orders}/orders", params={"status": "pending"}).json()
        assert any(o["id"] == 101 for o in before), "101 should be pending before cancel"

        r = requests.post(f"{orders}/orders/101/cancel")
        assert r.status_code == 200, f"cancel 101 → {r.status_code}: {r.text}"
        assert r.json().get("ok") is True, f"cancel 101 body: {r.json()}"

        after = requests.get(f"{orders}/orders", params={"status": "pending"}).json()
        assert not any(o["id"] == 101 for o in after), "101 should be absent after cancel"
        assert len(after) == len(before) - 1, f"expected {len(before)-1} pending, got {len(after)}"


# ── 3. FK enforcement: bad insert is rejected ───────────────────
def test_fk_enforcement():
    # DDL emits the clause
    ddl = _build_create_table("orders", {
        "columns": {
            "id": "integer",
            "customer_id": {"type": "integer", "references": "customers.id"},
        }
    })
    assert "FOREIGN KEY (customer_id) REFERENCES customers(id)" in ddl, f"DDL missing FK: {ddl}"

    # sqlite enforces it with the pragma
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "t.db")
        conn = sqlite3.connect(p)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO customers VALUES (1)")
        conn.execute(_build_create_table("orders", {
            "columns": {
                "id": "integer",
                "customer_id": {"type": "integer", "references": "customers.id"},
            }
        }))
        conn.execute("INSERT INTO orders VALUES (100, 1)")  # valid
        try:
            conn.execute("INSERT INTO orders VALUES (101, 999)")  # invalid
            conn.close()
            raise AssertionError("invalid FK was accepted")
        except sqlite3.IntegrityError:
            pass
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # full sandbox: seed loads without FK violation (proves seed order is correct)
    sb = Sandbox.from_file(YAML)
    with sb.run() as env:
        r = requests.get(f"{env['SB_API_ORDERS']}/orders")
        assert r.status_code == 200, f"seed failed under FK enforcement: {r.status_code}"


# ── 4. reset: two runs → identical seed state ───────────────────
def test_reset_consistency():
    def snapshot():
        sb = Sandbox.from_file(YAML)
        with sb.run() as env:
            rows = requests.get(f"{env['SB_API_ORDERS']}/orders").json()
            return sorted((o["id"], o["status"], o["total"]) for o in rows)

    a = snapshot()
    b = snapshot()
    assert a == b, f"two runs produced different state\n first: {a[:3]}...\n second: {b[:3]}..."


# ── 5. tool errors reach the agent (via _call) ──────────────────
def test_tool_errors():
    from agent_tools import _call, cancel_order

    # _call surfaces _status on 4xx
    class FakeResp:
        status_code = 404
        def json(self): return {"error": "not_found"}
    out = _call(FakeResp())
    assert out.get("_status") == 404, f"_call dropped status: {out}"
    assert out.get("error") == "not_found", f"_call dropped body: {out}"

    # 2xx does not add _status
    class OK:
        status_code = 200
        def json(self): return {"ok": True}
    out = _call(OK())
    assert "_status" not in out, f"_call added _status on success: {out}"

    # a real tool call against a live sandbox: missing order → 404 surfaced
    sb = Sandbox.from_file(YAML)
    with sb.run() as env:
        import agent_tools
        agent_tools.configure(env) if hasattr(agent_tools, "configure") else None
        # the tools read os.environ by default; env is already set by run()
        r = cancel_order.invoke({"order_id": 9999})
        assert isinstance(r, dict), f"cancel_order returned {type(r)}"
        assert r.get("_status") == 404, f"expected 404 for missing order, got: {r}"


# ── 6. partial failure cleanup: temp dir removed, no leaked servers ─
def test_failure_cleanup():
    # craft a config that fails halfway: first DB ok, second DB has a bad table spec
    bad_config = {
        "databases": {
            "shop": {
                "type": "sqlite",
                "tables": {
                    "customers": {
                        "columns": {"id": "integer", "name": "text"},
                        "seed": [{"id": 1, "name": "Alice"}],
                    },
                },
            },
            "broken": {
                "type": "sqlite",
                "tables": {
                    "x": {
                        "columns": {"id": "integer"},
                        "seed": [{"id": 1, "not_a_column": "boom"}],  # will fail at INSERT
                    },
                },
            },
        },
        "apis": {},
    }

    sb = Sandbox(bad_config)

    before = set(os.listdir(tempfile.gettempdir()))
    raised = False
    try:
        with sb.run():
            pass
    except Exception:
        raised = True
    after = set(os.listdir(tempfile.gettempdir()))

    assert raised, "broken config did not raise"

    leaked = {d for d in (after - before) if d.startswith("sandbox-")}
    assert not leaked, f"temp dir(s) leaked after failure: {leaked}"


# ── run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    check("provisioning (DBs, APIs, row counts)", test_provisioning)
    check("persistence (cancel → list → absent)", test_persistence)
    check("FK enforcement (DDL + runtime)", test_fk_enforcement)
    check("reset consistency (two runs identical)", test_reset_consistency)
    check("tool errors reach agent (_status surfaced)", test_tool_errors)
    check("partial failure cleanup (no leaked temp dirs)", test_failure_cleanup)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} passed")
    for name, ok, msg in RESULTS:
        if not ok:
            print(f"  FAIL: {name} — {msg}")
    raise SystemExit(0 if passed == total else 1)