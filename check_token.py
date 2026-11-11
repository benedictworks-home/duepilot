import os, requests
from dotenv import load_dotenv
load_dotenv()

cid = os.getenv("PAYPAL_CLIENT_ID") or ""
r = requests.post(
    "https://api-m.sandbox.paypal.com/v1/oauth2/token",
    auth=(cid, os.getenv("PAYPAL_SECRET")),
    data={"grant_type": "client_credentials"},
)
d = r.json()
print("Status:", r.status_code)
print("Client ID starts with:", cid[:6])
print("Scopes:")
for s in d.get("scope", "").split():
    print("  ", s)