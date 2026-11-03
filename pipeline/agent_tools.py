import os, requests
from langchain_core.tools import tool

def _api(name):
    return os.environ[f"SB_API_{name.upper()}"]


def _call(resp):
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        body = {**body, "_status": resp.status_code}
    return body


@tool
def list_orders(status: str = None) -> list[dict]:
    """List orders, optionally filtered by status (pending|paid|shipped|cancelled|refunded)."""
    r = requests.get(f"{_api('orders')}/orders", params={"status": status} if status else {})
    return _call(r)

@tool
def cancel_order(order_id: int) -> dict:
    """Cancel an order by id. Returns {ok:true} or an error dict."""
    r = requests.post(f"{_api('orders')}/orders/{order_id}/cancel")
    return _call(r)

@tool
def charge_customer(customer_id: int, amount: float, currency: str = "usd") -> dict:
    """Charge a customer. Inserts a real charge row and returns it."""
    r = requests.post(f"{_api('payments')}/charge",
                      json={"customer_id": customer_id, "amount": amount, "currency": currency})
    return _call(r)

@tool
def refund_charge(charge_id: str) -> dict:
    """Refund a charge by id."""
    r = requests.post(f"{_api('payments')}/refund", json={"charge_id": charge_id})
    return _call(r)

@tool
def get_shipping_rates() -> list[dict]:
    """Get shipping rates."""
    r = requests.get(f"{_api('shipping')}/rates")
    return _call(r)

@tool
def create_shipment(order_id: int, carrier: str) -> dict:
    """Create a shipment for an order. Inserts a real shipment row."""
    r = requests.post(f"{_api('shipping')}/shipments",
                      json={"order_id": order_id, "carrier": carrier})
    return _call(r)

TOOLS = [list_orders, cancel_order, charge_customer, refund_charge,
         get_shipping_rates, create_shipment]