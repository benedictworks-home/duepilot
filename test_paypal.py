import datetime
from app import paypal

due = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()

print("1. Getting token...")
paypal.get_token()
print("   OK")

print("2. Creating draft invoice...")
res = paypal.create_draft(
    "Ada",
    "PUT_YOUR_SANDBOX_PERSONAL_EMAIL_HERE",
    [{"name": "Logo draft", "quantity": 5, "unit_amount": 150}],
    due,
)
print("   OK:", res)

print("3. Listing invoices...")
inv = paypal.list_invoices()
print("   Total invoices:", inv.get("total_items"))