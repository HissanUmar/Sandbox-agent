"""State-based grader.

Run: python grade.py tasks/shop/cancel_order.yaml
Exit 0 = pass, 1 = fail.

Task YAML:
  name:           identifier
  env:            shop | hospital
  db:             database name (shop | hospital)
  input:          task string for the agent
  mode:           at_least_one (default) | delta | exact
  expected_state:
    <table>:
      - <partial row dict>
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


def _snapshot(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur]
    finally:
        conn.close()


def _row_key(row):
    return tuple(sorted(row.items(), key=lambda kv: kv[0]))


def run_task(task):
    env_name = task["env"]
    sb = Sandbox.from_file(f"environments/{env_name}/sandbox.yaml")

    with sb.run() as env:
        runtime = importlib.import_module(f"environments.{env_name}._runtime")
        runtime.configure(env)
        tools = importlib.import_module(f"environments.{env_name}.tools").TOOLS
        prompt = open(f"environments/{env_name}/prompt.md").read()

        db_path = os.path.join(sb._run_dir, f"{task['db']}.db")

        before = {t: _snapshot(db_path, t) for t in task["expected_state"]}
        agent.main(task["input"], tools, prompt)
        after = {t: _snapshot(db_path, t) for t in task["expected_state"]}

        return before, after


def grade(task, before, after):
    mode = task.get("mode", "at_least_one")

    for table, expected_list in task["expected_state"].items():
        if mode == "at_least_one":
            rows = after[table]
            for expected in expected_list:
                matched = any(
                    all(actual.get(k) == v for k, v in expected.items())
                    for actual in rows
                )
                if not matched:
                    return False, f"no row in {table} matches {expected}; got {rows}"

        elif mode == "delta":
            before_keys = {_row_key(r) for r in before[table]}
            after_keys = {_row_key(r) for r in after[table]}
            added = [r for r in after[table] if _row_key(r) not in before_keys]
            removed = [r for r in before[table] if _row_key(r) not in after_keys]

            if len(added) != len(expected_list):
                return False, (
                    f"{table}: expected exactly {len(expected_list)} new row(s), "
                    f"got {len(added)}: {added}"
                )
            if removed:
                return False, f"{table}: unexpected rows removed: {removed}"

            unmatched = list(expected_list)
            for row in added:
                for i, exp in enumerate(unmatched):
                    if all(row.get(k) == v for k, v in exp.items()):
                        unmatched.pop(i)
                        break
                else:
                    return False, f"{table}: new row {row} matches no expected dict"
            if unmatched:
                return False, f"{table}: expected dict(s) {unmatched} not matched by any new row"

        elif mode == "exact":
            actual_set = {_row_key(r) for r in after[table]}
            expected_set = {_row_key(e) for e in expected_list}
            if actual_set != expected_set:
                return False, (
                    f"{table}: table contents differ. "
                    f"missing: {expected_set - actual_set}; "
                    f"extra: {actual_set - expected_set}"
                )

        else:
            return False, f"unknown mode {mode!r}"

    return True, "ok"


def main(path):
    task = load_task(path)
    mode = task.get("mode", "at_least_one")
    print(f"task: {task['name']} (env={task['env']}, mode={mode})")
    before, after = run_task(task)
    ok, msg = grade(task, before, after)
    print(f"[{'PASS' if ok else 'FAIL'}] {task['name']}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python grade.py tasks/<env>/<task>.yaml")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))