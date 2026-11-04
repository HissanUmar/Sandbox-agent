# test_fk.py
import sqlite3, tempfile, os
from sandbox import _build_create_table

# 1. the DDL contains the constraint
ddl = _build_create_table("orders", {
    "columns": {
        "id": "integer",
        "customer_id": {"type": "integer", "references": "customers.id"},
    }
})
assert "FOREIGN KEY (customer_id) REFERENCES customers(id)" in ddl, ddl
print("[PASS] DDL emits FOREIGN KEY clause")

# 2. sqlite enforces it
d = tempfile.mkdtemp()
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
    raise AssertionError("FK not enforced")
except sqlite3.IntegrityError:
    print("[PASS] invalid FK rejected at runtime")
conn.close()
import shutil; shutil.rmtree(d)