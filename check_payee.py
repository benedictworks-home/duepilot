import time
from app import paypal

o = paypal.create_order(
    "diagnostic",
    [{"name": "test", "quantity": 1, "unit_amount": 10}],
    "USD",
    "http://127.0.0.1:8000/paypal/return",
    "http://127.0.0.1:8000/paypal/cancel",
    f"diag-{time.time()}",
)
full = paypal.get_order(o["id"])
print("payee:", full["purchase_units"][0].get("payee"))
print("status:", full.get("status"))