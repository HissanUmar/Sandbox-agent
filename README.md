# Local Agent Sandbox

A local sandbox for testing AI agents against **real databases** and **real HTTP APIs** — no mocks, no hardcoded responses. 

The agent sees only the API surface; the database lives behind it.

---

## What this is

An agent's environment is provisioned from a single YAML file at run time:

- **Databases** — SQLite files, created and seeded fresh on every run.
- **APIs** — FastAPI services that execute declared SQL against those databases.
- **Tools** — LangChain tools that call the APIs over HTTP.

Every run starts from the same seed, writes persist for the duration of the run, and everything is torn down on exit. The agent never holds a database connection — it calls `POST /orders/101/cancel` and the API does the rest.

---

## Structure

```text
.
├── run_agent.py          # Entry point
├── agent.py              # LLM + ReAct loop + system prompt
├── agent_tools.py        # Tools the agent can call
├── sandbox.py            # Provisioner: YAML → DB + APIs
├── pipeline/
│   └── sandbox.yaml      # The world: tables, seeds, endpoints
├── requirements.txt
└── .env
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration (`.env`)

```bash
OLLAMA_BASE_URL=https://<your-tunnel>.trycloudflare.com
OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
OLLAMA_API_KEY=ollama
```

> **Note:** The LLM endpoint is an Ollama instance exposed through a Cloudflare tunnel (see `Colab_Ollama.ipynb`). The tunnel URL changes on every restart.

---

## Run

```bash
python run_agent.py "Cancel order 101, then list pending orders"
```

### Expected trace:

```text
sandbox up: {'SB_API_ORDERS': 'http://127.0.0.1:...', 'SB_API_PAYMENTS': '...', 'SB_API_SHIPPING': '...'}
[tool] cancel_order({'order_id': 101}) -> {'ok': True}
[tool] list_orders({'status': 'pending'}) -> [ ...5 rows, 101 absent... ]
=== FINAL === Order 101 cancelled. Pending orders: ...
```

The absence of 101 in the second call is the point: the write persisted to the real database, and the read saw it.

---

## How the sandbox works

`sandbox.py` reads `pipeline/sandbox.yaml` and, inside `with sb.run()`:

1. Creates a temp directory for the run.
2. For each `databases:` entry — creates a SQLite file, runs `CREATE TABLE` from `columns:`, inserts `seed:` rows.
3. For each `apis:` entry with `type: sql` — starts a FastAPI server on a random port. Each endpoint's `sql:` is executed against the database named in `database:`.
4. Exports `SB_API_*` handles into the environment. `SB_DB_*` is never exported — the agent has no database handle.
5. On exit — shuts down the servers and deletes the temp directory.

---

## Endpoint format

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

- **`params`** — Validated before SQL runs. `source` is path, query, or body.
- **`sql`** — One statement. `?` placeholders bind in declaration order.
- **`on_success` / `on_not_found` / `on_conflict` / `on_invalid`** — Chosen by affected rows and validation outcome.
- **`body: "{rows}"`** returns the row list; **`"{rows[0]}"`** returns the first row.

---

## What the agent can do

| Tool | Endpoint | Effect |
| :--- | :--- | :--- |
| `list_orders(status)` | `GET /orders` | Reads `orders` |
| `cancel_order(id)` | `POST /orders/{id}/cancel` | Writes `orders.status` |
| `charge_customer(id, amount, currency)` | `POST /payments/charge` | Inserts into `charges` |
| `refund_charge(charge_id)` | `POST /payments/refund` | Writes `charges.status` |
| `get_shipping_rates()` | `GET /shipping/rates` | Static rates |
| `create_shipment(order_id, carrier)` | `POST /shipping/shipments` | Inserts into `shipments` |

---

## Known limitations

- **No `run_sql`:** The agent can only answer questions the endpoints support. Adding a question means adding an endpoint.
- **Error bodies keep literal placeholders:** `"Order {id} does not exist"` is sent as-is; `{id}` is not substituted. (Cosmetic)
- **404 and 409 are not distinguished for write endpoints:** A shipped order and a missing order both return 404. (Accepted)
- **Positional `?` binding:** Declared params and SQL placeholders must be in the same order. Multi-param endpoints with repeated placeholders will break with a "bindings" error.
- **No baseline diff:** You can inspect final state, but not "what changed from the seed."

---

## Testing

Grade the agent's answers against known ground truth. Current seed supports, among others:

| Task | Expected |
| :--- | :--- |
| **List cancelled orders** | `102, 111, 121` |
| **Total value of shipped orders** | `537.09` |
| **Customers per country** | `US=4, UK=2, DE=FR=JP=RU=1` |
| **Orders from UK customers** | `102, 103, 112, 113, 123, 124` |
| **Cancel 101 then list pending** | `5 rows (101 absent)` |

Save traces to `runs/` and diff against them after any change to `sandbox.yaml` or `sandbox.py`.

---

## Architecture

Two pipelines, one boundary:

- **Plumbing** — `sandbox.yaml`, `sandbox.py`, `agent_tools.py`. Knows about SQLite, HTTP, and SQL. Does not know the LLM exists.
- **Agentic** — `agent.py`. Knows about the LLM, the ReAct loop, and the prompt. Imports `TOOLS` from the plumbing; does not know how they are implemented.

`run_agent.py` is the only file that imports both. It is also the only file that changes when the delivery surface changes (script → CLI → HTTP broker).

The agent is constrained by the API contract, not by a gate. There is no SQL validator because the agent does not write SQL. Every action is a declared endpoint; every failure is a status code.