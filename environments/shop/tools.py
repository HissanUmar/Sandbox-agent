"""Shop environment — agent tools.

These call the shop APIs. Every tool goes through _call() so errors carry
_status and the agent can decide whether to retry.
"""
import requests
from langchain_core.tools import tool

from ._runtime import api_url, call


@tool
def list_orders(status: str = None) -> list | dict:
    """List orders, optionally filtered by status
    (pending|paid|shipped|cancelled|refunded). Returns raw rows; for counts
    use a dedicated aggregate endpoint if one exists."""
    params = {"status": status} if status else {}
    return call(requests.get(f"{api_url('orders')}/orders", params=params))


@tool
def cancel_order(order_id: int) -> dict:
    """Cancel an order by id. Returns {ok:true} on success.
    On failure returns {error, _status}. 404 = not found, 409 = not cancellable."""
    return call(requests.post(f"{api_url('orders')}/orders/{order_id}/cancel"))


@tool
def charge_customer(customer_id: int, amount: float, currency: str = "usd") -> dict:
    """Charge a customer. Inserts a real charge row and returns it."""
    return call(requests.post(
        f"{api_url('payments')}/charge",
        json={"customer_id": customer_id, "amount": amount, "currency": currency},
    ))


@tool
def refund_charge(charge_id: str) -> dict:
    """Refund a charge by id."""
    return call(requests.post(f"{api_url('payments')}/refund",
                              json={"charge_id": charge_id}))


@tool
def get_shipping_rates() -> list | dict:
    """Get shipping rates. Returns [{carrier, price, eta_days}]."""
    r = requests.get(f"{api_url('shipping')}/rates")
    body = call(r)
    if isinstance(body, dict) and "rates" in body and "_status" not in body:
        return body["rates"]
    return body


@tool
def create_shipment(order_id: int, carrier: str) -> dict:
    """Create a shipment for an order. Inserts a real shipment row."""
    return call(requests.post(
        f"{api_url('shipping')}/shipments",
        json={"order_id": order_id, "carrier": carrier},
    ))


TOOLS = [list_orders, cancel_order, charge_customer,
         refund_charge, get_shipping_rates, create_shipment]