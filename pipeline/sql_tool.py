# pipeline/sql_tool.py
"""Safe SQL execution against the sandbox database.

The gate does exactly three structural checks — SELECT-only, schema-existence,
function-existence — and nothing about English. Semantic correctness is the
model's job; the gate only guarantees the query is safe to run.
"""
import os
import re
import sqlite3

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.qualify import qualify
from sqlglot.schema import MappingSchema
from langchain_core.tools import tool


SQLITE_FUNCS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL", "GROUP_CONCAT",
    "ABS", "ROUND", "LENGTH", "LOWER", "UPPER", "SUBSTR", "REPLACE",
    "TRIM", "LTRIM", "RTRIM", "COALESCE", "IFNULL", "NULLIF",
    "CAST", "TYPEOF", "DATE", "TIME", "DATETIME", "JULIANDAY",
    "STRFTIME", "IIF",
}

# sqlglot knows these from other dialects but sqlite will not run them.
DIALECT_MISMATCH = {
    "STRING_AGG": "Use GROUP_CONCAT(column) instead of STRING_AGG(column, sep).",
    "CONCAT":     "Use the || operator or GROUP_CONCAT for concatenation.",
    "NOW":        "Use DATE('now') for the current date.",
    "CURRENT_TIMESTAMP": "Use DATE('now') for the current date.",
}


def _db():
    return sqlite3.connect(os.environ["SB_DB_SHOP"].replace("sqlite:///", ""))


def _schema() -> MappingSchema:
    conn = _db()
    tables = {}
    for (tbl,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        tables[tbl] = {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info({tbl})")}
    conn.close()
    return MappingSchema(tables, dialect="sqlite")


def _reject(cls, problem, suggestion, query):
    return {"rejected": True, "class": cls, "failed_sql": query,
            "problem": problem, "suggestion": suggestion}


def gate(query: str, schema: MappingSchema) -> dict | None:
    """Return None if the query is safe to execute, else a rejection dict.

    Three checks, all structural:
      1. parse + SELECT-only
      2. every table and column exists
      3. every function is available in sqlite
    """
    # raw-text dialect check (sqlglot normalizes these away before the AST)
    for bad, hint in DIALECT_MISMATCH.items():
        if re.search(rf"\b{bad}\s*\(", query, re.IGNORECASE):
            return _reject("function", f"{bad} is not valid sqlite.", hint, query)

    # 1. parse + SELECT-only
    try:
        ast = sqlglot.parse_one(query, dialect="sqlite")
    except ParseError as e:
        return _reject("syntax", f"SQL could not be parsed: {e}",
                       "Fix the syntax and retry.", query)
    if not isinstance(ast, exp.Select):
        return _reject("not_select", f"Root is {type(ast).__name__}, not SELECT.",
                       "Only SELECT statements are allowed.", query)

    # 2. schema: tables and columns
    for table in ast.find_all(exp.Table):
        if table.name and table.name not in schema.mapping:
            return _reject(
                "schema",
                f"Table '{table.name}' does not exist. "
                f"Available: {', '.join(sorted(schema.mapping))}.",
                "Use one of the existing tables.", query,
            )
    try:
        qualify(ast, dialect="sqlite", schema=schema, quote_identifiers=False)
    except Exception as e:
        return _reject("schema", f"Schema error: {e}",
                       "Check table and column names. If you renamed a column, "
                       "use the exact name.", query)

    # 3. functions
    unknown = {
        (node.name or "").upper()
        for node in ast.find_all(exp.Anonymous)
        if (node.name or "").upper() not in SQLITE_FUNCS
    }
    if unknown:
        return _reject(
            "function",
            f"Unknown function(s): {', '.join(sorted(unknown))}.",
            "Rewrite without these functions, or use a sqlite equivalent.",
            query,
        )

    return None


_FAILED = set()


def reset_retry_guard():
    _FAILED.clear()


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


@tool
def run_sql(query: str) -> list | dict:
    """Execute a read-only SQL query against the shop database.

    Tables:
      customers(id, name, email, country)
      orders(id, customer_id, status, total, created_at)
    status: pending | paid | shipped | cancelled | refunded.
    created_at: ISO date string, e.g. '2026-10-21'.

    Only SELECT is allowed. If rejected, the dict contains {class, problem,
    suggestion, failed_sql}. Fix the specific thing named and retry.
    Never resubmit identical SQL.
    """
    norm = _norm(query)
    if norm in _FAILED:
        return _reject("repeated", "This exact SQL already failed.",
                       "Write a different query.", query)

    rejection = gate(query, _schema())
    if rejection:
        _FAILED.add(norm)
        return rejection

    conn = _db()
    try:
        cur = conn.execute(query)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur]
    except Exception as e:
        _FAILED.add(norm)
        return _reject("execution", f"Execution failed: {e}",
                       "Fix the query and retry.", query)
    finally:
        conn.close()