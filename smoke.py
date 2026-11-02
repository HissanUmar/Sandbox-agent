from sandbox import Sandbox
import requests, os, sqlite3

sb = Sandbox.from_file("sandbox.yaml")
with sb.run() as env:
    print("env:", env)

    # DB check
    db = sqlite3.connect(os.environ["SB_DB_SHOP"].replace("sqlite:///", ""))
    print("pending:", db.execute("SELECT id, total FROM orders WHERE status='pending'").fetchall())

    # API check
    print("rates:", requests.get(f"{os.environ['SB_API_SHIPPING']}/rates").json())
    print("charge:", requests.post(
        f"{os.environ['SB_API_PAYMENTS']}/charge",
        json={"customer_id": 1, "amount": 7.5, "currency": "usd"},
    ).json())