# test_validate_issue12.py
"""Tests for Issue 12 validation additions:
  - ? inside string literals / comments not counted
  - unknown table rejected
  - unknown column rejected
  - precheck SQL validated
"""
import yaml
from pipeline.validate import validate, ConfigError


def expect_error(cfg, needle):
    try:
        validate(cfg)
    except ConfigError as e:
        assert needle in str(e), f"expected {needle!r} in: {e}"
        print(f"[PASS] rejected: {needle!r}")
        return
    raise AssertionError(f"expected ConfigError containing {needle!r}, got none")


def expect_ok(cfg, label):
    validate(cfg)
    print(f"[PASS] accepted: {label}")


def base_db():
    return {
        "shop": {
            "type": "sqlite",
            "tables": {
                "orders": {
                    "columns": {"id": "integer", "status": "text", "total": "real"},
                    "seed": [],
                },
            },
        }
    }


# ── 12a: ? inside string literals is not a placeholder ─────────────
expect_ok(
    {
        "databases": base_db(),
        "apis": {
            "orders": {
                "type": "sql",
                "database": "shop",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/x",
                        "params": {"id": {"type": "integer", "source": "query"}},
                        "sql": "SELECT '?' AS lit, id FROM orders WHERE id = ?",
                        "on_success": {"status": 200, "body": "{rows}"},
                    },
                ],
            },
        },
    },
    "? inside string literal counts as one placeholder",
)

# ── 12a: ? inside a comment is not a placeholder ───────────────────
expect_ok(
    {
        "databases": base_db(),
        "apis": {
            "orders": {
                "type": "sql",
                "database": "shop",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/x",
                        "params": {"id": {"type": "integer", "source": "query"}},
                        "sql": "-- which id?\nSELECT id FROM orders WHERE id = ?",
                        "on_success": {"status": 200, "body": "{rows}"},
                    },
                ],
            },
        },
    },
    "? inside SQL comment ignored",
)

# ── 12b: unknown table rejected ─────────────────────────────────────
expect_error(
    {
        "databases": base_db(),
        "apis": {
            "orders": {
                "type": "sql",
                "database": "shop",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/x",
                        "sql": "SELECT id FROM ordrs",
                        "on_success": {"status": 200, "body": "{rows}"},
                    },
                ],
            },
        },
    },
    "unknown table 'ordrs'",
)

# ── 12b: unknown column rejected ────────────────────────────────────
expect_error(
    {
        "databases": base_db(),
        "apis": {
            "orders": {
                "type": "sql",
                "database": "shop",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/x",
                        "sql": "SELECT id, statuss FROM orders",
                        "on_success": {"status": 200, "body": "{rows}"},
                    },
                ],
            },
        },
    },
    "unknown column 'statuss'",
)

# ── 12c: precheck SQL with a syntax error is rejected ──────────────
expect_error(
    {
        "databases": base_db(),
        "apis": {
            "orders": {
                "type": "sql",
                "database": "shop",
                "endpoints": [
                    {
                        "method": "POST",
                        "path": "/x",
                        "params": {"id": {"type": "integer", "source": "path"}},
                        "require_exists": "SELEC status FROM orders WHERE id = ?",
                        "sql": "UPDATE orders SET status = 'cancelled' WHERE id = ?",
                        "on_success": {"status": 200, "body": {"ok": True}},
                    },
                ],
            },
        },
    },
    "require_exists",
)

# ── baseline: the real YAMLs still validate ──────────────────────────
with open("environments/shop/sandbox.yaml") as f:
    expect_ok(yaml.safe_load(f), "environments/shop/sandbox.yaml")

with open("environments/hospital/sandbox.yaml") as f:
    expect_ok(yaml.safe_load(f), "environments/hospital/sandbox.yaml")

print("\nall Issue 12 validation tests passed")