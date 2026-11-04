# Deferred: Generic Aggregate Endpoint

Status: **deferred, not abandoned**. Revisit when aggregation questions recur.

## The problem

Every new question shape (count per customer, sum per status, average per
country) requires a new endpoint and a new tool. This doesn't scale: N
questions → N endpoints → N tools. Two failure modes observed:

- `list_orders({})` returns 26 raw rows; the model tallies in context and
  miscounts (customer 5 and 10 both have 3 orders, model said 2).
- No endpoint can express `GROUP BY`, so the model compensates by reading
  everything and doing arithmetic it can't do reliably.

## The proposed fix

One endpoint per table: `GET /orders/aggregate`, with a fixed SQL template
filled from validated parameters:

    group_by: one of [customer_id, status, created_at]
    metric:   one of [count, sum, avg]
    column:   one of [total]           (required for sum/avg)
    status:   one of the five statuses (optional filter)

The handler builds the SQL from the whitelisted values (never from raw
input), so there's no injection risk and no need for a SQL gate.

## Why it's deferred

- ~40 lines of new code in `sandbox.py` (`_build_aggregate_sql`, the
  `__AGGREGATE__` sentinel branch, an `allowed:` check in `_check_params`).
- One new YAML endpoint per table.
- One new tool per table.
- Doesn't cover `HAVING`, joins, or subqueries — those need their own
  parameters or endpoints.
- Current questions don't require it often enough to justify the surface.

## What would trigger building it

- The same `GROUP BY` question appears in ≥3 different forms.
- The model starts miscounting/aggregating manually more than once per
  session (observed once so far).
- A task requires "sum by X" or "average by X" and has no endpoint.

## If/when built, the shape

- `sandbox.py`: `_build_aggregate_sql(ep, values) -> (sql, params)`.
- `sandbox.py` handler: `if _ep["sql"] == "__AGGREGATE__": ...`.
- `validate.py`: `allowed:` check in `_check_params` (values must be in the
  declared list).
- `sandbox.yaml`: one aggregate endpoint per table.
- `agent_tools.py`: `aggregate_<table>(group_by, metric, column=None, status=None)`.

## The alternative that was rejected

`run_sql`: full SQL power, but reintroduces the gate problem (semantic
validation, verbatim retry loops, wrong-question queries passing as right
answers). The aggregate endpoint is the bounded middle ground: expressive
enough for analytical questions, safe enough that no gate is needed.