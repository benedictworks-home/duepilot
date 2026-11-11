import re, datetime

MAX_AMOUNT = 5000  # change as you like

def check(args, history):
    blocking, warnings = [], []
    items = args.get("items") or []
    email = (args.get("client_email") or "").strip()

    if not args.get("client_name"):
        blocking.append("Missing client name")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        blocking.append("Missing or invalid client email")
    if not items:
        blocking.append("No line items")

    total = 0.0
    for i in items:
        try:
            q, p = float(i["quantity"]), float(i["unit_amount"])
            if q <= 0 or p <= 0:
                blocking.append(f"Invalid quantity/price for '{i.get('name')}'")
            total += q * p
        except (KeyError, TypeError, ValueError):
            blocking.append("A line item has a bad quantity or price")

    if total > MAX_AMOUNT:
        blocking.append(f"Total {total:.2f} exceeds the safety cap of {MAX_AMOUNT}")
    elif total > MAX_AMOUNT * 0.6:
        warnings.append(f"Large invoice: {total:.2f}")

    try:
        due = datetime.date.fromisoformat(args.get("due_date", ""))
        if due <= datetime.date.today():
            blocking.append("Due date must be in the future")
    except ValueError:
        blocking.append("Due date is not a valid date")

    if args.get("currency", "USD") not in ("USD", "EUR", "GBP", "CAD", "AUD"):
        blocking.append("Unsupported currency")

    # duplicate check: same client + same total in the last 7 days
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    for h in history:
        a = h["args"]
        try:
            h_total = sum(float(x["quantity"]) * float(x["unit_amount"]) for x in a.get("items", []))
            created = datetime.datetime.fromisoformat(h["created_at"])
        except Exception:
            continue
        same_client = (a.get("client_email") or "").lower() == email.lower() or \
                      (a.get("client_name") or "").lower() == (args.get("client_name") or "").lower()
        if same_client and abs(h_total - total) < 0.01 and created > cutoff:
            warnings.append("Possible duplicate: same client and amount in the last 7 days")
            break

    confidence = "high" if not blocking and not warnings else ("medium" if not blocking else "low")
    return {"ok": not blocking, "blocking": blocking, "warnings": warnings,
            "total": round(total, 2), "confidence": confidence}