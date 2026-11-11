import time
from app import paypal

o = paypal.create_order(
    "Test payment",
    [{"name": "Logo draft", "quantity": 2, "unit_amount": 150}],
    "USD",
    "http://127.0.0.1:8000/paypal/return",
    "http://127.0.0.1:8000/paypal/cancel",
    f"test-{time.time()}",
)
print("Order id:", o["id"], "| status:", o["status"])
print("Payment link:", paypal.approval_link(o))