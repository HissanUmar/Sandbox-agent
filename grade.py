# grade.py
"""Minimal state-based grader.

Run: python grade.py tasks/shop/cancel_order.yaml
Exit 0 = pass, 1 = fail.
"""
import importlib
import os
import sqlite3
import sys

import yaml
from dotenv import load_dotenv
load_dotenv()

from pipeline.sandbox import Sandbox
import agent


def load_task(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _select(db_path, table, where):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"SELECT * FROM {table} WHERE {where}")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur]
    finally:
        conn.close()


def run_task(task):
    env_name = task["env"]
    sb = Sandbox.from_file(f"environments/{env_name}/sandbox.yaml")

    with sb.run() as env:
        runtime = importlib.import_module(f"environments.{env_name}._runtime")
        runtime.configure(env)
        tools = importlib.import_module(f"environments.{env_name}.tools").TOOLS
        prompt = open(f"environments/{env_name}/prompt.md").read()

        agent.main(task["input"], tools, prompt)
        db_path = os.path.join(sb._run_dir, f"{task['db']}.db")

        results = {}
        for table, expected_rows in task["expected_state"].items():
            # find rows matching each expected dict's keys
            for expected in expected_rows:
                where = " AND ".join(f"{k} = ?" for k in expected)
                params = list(expected.values())
                conn = sqlite3.connect(db_path)
                try:
                    cur = conn.execute(f"SELECT * FROM {table} WHERE {where}", params)
                    cols = [d[0] for d in cur.description]
                    results.setdefault(table, []).extend(
                        dict(zip(cols, r)) for r in cur
                    )
                finally:
                    conn.close()
        return results


def grade(task, actual_rows):
    # actual_rows is a list of dicts, one per table in expected_state
    # grouped by table: {"orders": [...], "appointments": [...]}
    if not actual_rows:
        return False, "no rows returned from DB"

    for table, expected_list in task["expected_state"].items():
        rows = actual_rows.get(table, [])
        if not rows:
            return False, f"no rows in table {table}"
        for expected in expected_list:
            matched = any(
                all(actual.get(k) == v for k, v in expected.items())
                for actual in rows
            )
            if not matched:
                return False, f"no row in {table} matches {expected}; got {rows}"
    return True, "ok"


def main(path):
    task = load_task(path)
    print(f"task: {task['name']} (env={task['env']})")
    actual = run_task(task)
    ok, msg = grade(task, actual)
    print(f"[{'PASS' if ok else 'FAIL'}] {task['name']}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python grade.py tasks/<env>/<task>.yaml")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))