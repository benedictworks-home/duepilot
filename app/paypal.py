import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")

# Holds the access token so we don't ask PayPal for a new one every call
_token = {"value": None, "expires_at": 0}


class PayPalError(Exception):
    """Raised when PayPal returns an error. Message includes PayPal's explanation."""


def _check(response):
    if not response.ok:
        raise PayPalError(f"{response.status_code}: {response.text[:600]}")
    return response


def get_token():
    # Reuse the token if it's still valid
    if _token["value"] and time.time() < _token["expires_at"] - 60:
        return _token["value"]

    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_SECRET")
    if not client_id or not secret:
        raise PayPalError("PAYPAL_CLIENT_ID or PAYPAL_SECRET is missing from your .env file")

    r = requests.post(
        f"{BASE}/v1/oauth2/token",
        auth=(client_id, secret),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    _check(r)
    data = r.json()
    _token["value"] = data["access_token"]
    _token["expires_at"] = time.time() + data.get("expires_in", 300)
    return _token["value"]


def _headers():
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }


def next_invoice_number():
    r = requests.post(
        f"{BASE}/v2/invoicing/generate-next-invoice-number",
        headers=_headers(),
        timeout=30,
    )
    _check(r)
    return r.json()["invoice_number"]


def create_draft(client_name, client_email, items, due_date, currency="USD"):
    """
    items: [{"name": str, "quantity": number, "unit_amount": number}]
    due_date: "YYYY-MM-DD"
    Returns PayPal's response, which contains an 'href' ending in the invoice id.
    """
    body = {
        "detail": {
            "invoice_number": next_invoice_number(),
            "currency_code": currency,
            "payment_term": {"due_date": due_date},
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": client_name},
                    "email_address": client_email,
                }
            }
        ],
        "items": [
            {
                "name": i["name"],
                "quantity": str(i["quantity"]),
                "unit_amount": {
                    "currency_code": currency,
                    "value": f'{float(i["unit_amount"]):.2f}',
                },
            }
            for i in items
        ],
    }
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices", headers=_headers(), json=body, timeout=30
    )
    _check(r)
    return r.json()


def send_invoice(invoice_id):
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}/send",
        headers=_headers(),
        json={"send_to_recipient": True},
        timeout=30,
    )
    _check(r)
    return r.json() if r.text else {"status": "sent"}


def get_invoice(invoice_id):
    r = requests.get(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}", headers=_headers(), timeout=30
    )
    _check(r)
    return r.json()


def list_invoices(page=1, page_size=20):
    r = requests.get(
        f"{BASE}/v2/invoicing/invoices",
        headers=_headers(),
        params={"page": page, "page_size": page_size, "total_required": "true"},
        timeout=30,
    )
    _check(r)
    return r.json()


def send_reminder(invoice_id, subject, note):
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}/remind",
        headers=_headers(),
        json={"subject": subject, "note": note, "send_to_invoicer": False},
        timeout=30,
    )
    _check(r)
    return r.json() if r.text else {"status": "reminder_sent"}

    # ---------- Orders API (payment links) ----------
from decimal import Decimal, ROUND_HALF_UP


def _money(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def create_order(description, items, currency, return_url, cancel_url, request_id):
    """
    Creates a PayPal order and returns PayPal's response.
    items: [{"name": str, "quantity": number, "unit_amount": number}]
    """
    line_items = []
    total = Decimal("0.00")
    for i in items:
        qty = float(i["quantity"])
        if not qty.is_integer() or qty <= 0:
            raise PayPalError(f"Quantity must be a whole number, got {i['quantity']}")
        unit = _money(i["unit_amount"])
        total += unit * int(qty)
        line_items.append({
            "name": str(i["name"])[:127],
            "quantity": str(int(qty)),
            "unit_amount": {"currency_code": currency, "value": str(unit)},
        })

    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": request_id,
            "description": description[:127],
            "amount": {
                "currency_code": currency,
                "value": str(total),
                "breakdown": {"item_total": {"currency_code": currency, "value": str(total)}},
            },
            "items": line_items,
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "DuePilot",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            }
        },
    }
    headers = _headers()
    headers["PayPal-Request-Id"] = request_id  # prevents accidental duplicate orders
    r = requests.post(f"{BASE}/v2/checkout/orders", headers=headers, json=body, timeout=30)
    _check(r)
    return r.json()


def approval_link(order):
    """The URL the client opens to pay."""
    for link in order.get("links", []):
        if link.get("rel") in ("payer-action", "approve"):
            return link["href"]
    raise PayPalError("PayPal did not return a payment link")


def get_order(order_id):
    r = requests.get(f"{BASE}/v2/checkout/orders/{order_id}", headers=_headers(), timeout=30)
    _check(r)
    return r.json()


def capture_order(order_id):
    """Collects the money after the client has approved the payment."""
    r = requests.post(
        f"{BASE}/v2/checkout/orders/{order_id}/capture",
        headers=_headers(), json={}, timeout=30,
    )
    _check(r)
    return r.json()