# agent_tools.py
import os
import sqlite3
import requests
from langchain_core.tools import tool


def _db():
    return sqlite3.connect(os.environ["SB_DB_SHOP"].replace("sqlite:///", ""))


# ─────────────────────────────────────────────────────────────
# Database tools
# ─────────────────────────────────────────────────────────────

@tool
def query_orders(
    status: str = None,
    customer_id: int = None,
    min_total: float = None,
    created_after: str = None,
) -> list[dict]:
    """Query orders. All filters are optional and combined with AND.
    Returns id, customer_id, status, total, created_at for each matching order.

    - status: one of pending, paid, shipped, cancelled, refunded
    - customer_id: only orders for this customer
    - min_total: only orders with total >= this value
    - created_after: ISO date string, e.g. "2026-10-01"
    """
    clauses, params = [], []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if customer_id is not None:
        clauses.append("customer_id = ?")
        params.append(customer_id)
    if min_total is not None:
        clauses.append("total >= ?")
        params.append(min_total)
    if created_after is not None:
        clauses.append("created_at > ?")
        params.append(created_after)

    sql = "SELECT id, customer_id, status, total, created_at FROM orders"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    conn = _db()
    cur = conn.execute(sql, params)
    rows = [
        {
            "id": r[0],
            "customer_id": r[1],
            "status": r[2],
            "total": r[3],
            "created_at": r[4],
        }
        for r in cur
    ]
    conn.close()
    return rows


@tool
def list_customers(country: str = None) -> list[dict]:
    """List customers, optionally filtered by country.
    Returns id, name, email, country for each customer.
    email may be null.

    - country: ISO country code like "US", "UK", "DE", "FR", "JP", "RU"
    """
    sql = "SELECT id, name, email, country FROM customers"
    params = []
    if country is not None:
        sql += " WHERE country = ?"
        params.append(country)

    conn = _db()
    cur = conn.execute(sql, params)
    rows = [
        {"id": r[0], "name": r[1], "email": r[2], "country": r[3]}
        for r in cur
    ]
    conn.close()
    return rows


@tool
def get_customer(customer_id: int) -> dict:
    """Fetch a single customer by id.
    Returns id, name, email, country. email may be null.
    Returns an empty dict if no such customer exists."""
    conn = _db()
    cur = conn.execute(
        "SELECT id, name, email, country FROM customers WHERE id = ?",
        (customer_id,),
    )
    r = cur.fetchone()
    conn.close()
    if not r:
        return {}
    return {"id": r[0], "name": r[1], "email": r[2], "country": r[3]}


# ─────────────────────────────────────────────────────────────
# API tools
# ─────────────────────────────────────────────────────────────

@tool
def charge_customer(customer_id: int, amount: float, currency: str = "usd") -> dict:
    """Charge a customer via the payments API. Returns the charge object
    with id, customer_id, amount, status."""
    r = requests.post(
        f"{os.environ['SB_API_PAYMENTS']}/charge",
        json={"customer_id": customer_id, "amount": amount, "currency": currency},
        timeout=10,
    )
    return r.json()


@tool
def get_shipping_rates() -> list[dict]:
    """Get available shipping rates from the shipping API.
    Returns a list of {carrier, price, eta_days}."""
    r = requests.get(f"{os.environ['SB_API_SHIPPING']}/rates", timeout=10)
    return r.json()["rates"]


@tool
def create_shipment(order_id: int, carrier: str) -> dict:
    """Create a shipment for an order via the shipping API.
    Returns tracking_id, order_id, carrier, status."""
    r = requests.post(
        f"{os.environ['SB_API_SHIPPING']}/shipments",
        json={"order_id": order_id, "carrier": carrier},
        timeout=10,
    )
    return r.json()


TOOLS = [
    query_orders,
    list_customers,
    get_customer,
    charge_customer,
    get_shipping_rates,
    create_shipment,
]