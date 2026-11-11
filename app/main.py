import os
import uuid
import datetime
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from app import paypal, ai_service, guardrails, db

# Where PayPal sends the client back after paying. Change on deploy (Render URL).
BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Path to the frontend page: <project root>/frontend/index.html
FRONTEND_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "index.html")

app = FastAPI(title="DuePilot")
db.init()
db.init_orders()


class ChatRequest(BaseModel):
    message: str


def order_view(o):
    """Adds a friendly 'state': paid / awaiting_payment / overdue."""
    state = o["status"]
    if state != "paid":
        try:
            if datetime.date.fromisoformat(o["due_date"]) < datetime.date.today():
                state = "overdue"
        except (ValueError, TypeError):
            pass
    return {**o, "state": state}


def build_summary():
    orders = [order_view(o) for o in db.list_orders()]

    def total(state):
        return round(sum(o["amount"] for o in orders if o["state"] == state), 2)

    return {
        "paid_total": total("paid"),
        "awaiting_total": total("awaiting_payment"),
        "overdue_total": total("overdue"),
        "count": len(orders),
        "orders": orders,
    }


def sync_order(paypal_order_id):
    """Asks PayPal for the order status. If the client approved it, collect the money."""
    row = db.get_order_by_paypal_id(paypal_order_id)
    if not row:
        raise HTTPException(404, "Unknown order")
    if row["status"] == "paid":
        return row
    try:
        status = paypal.get_order(paypal_order_id).get("status")
        if status == "APPROVED":
            status = paypal.capture_order(paypal_order_id).get("status")
    except Exception as e:
        db.log("system", "paypal_error", {"order": paypal_order_id, "error": str(e)})
        raise HTTPException(502, f"PayPal error: {e}")
    if status == "COMPLETED":
        db.mark_paid(paypal_order_id)
        db.log("system", "payment_received", {"order": paypal_order_id})
    return db.get_order_by_paypal_id(paypal_order_id)


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(FRONTEND_FILE)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    db.log("user", "chat", {"message": req.message})
    try:
        parsed = ai_service.parse_request(req.message)
    except Exception as e:
        db.log("system", "ai_error", {"error": str(e)})
        raise HTTPException(
            503, f"The AI service is busy or returned an unreadable answer. "
                 f"Try again in a moment. ({e})")

    if parsed.get("intent") == "create_invoice":
        args = {
            "client_name": parsed.get("client_name"),
            "client_email": parsed.get("client_email"),
            "currency": parsed.get("currency") or "USD",
            "items": parsed.get("items") or [],
            "due_date": parsed.get("due_date") or "",
        }
        guard = guardrails.check(args, db.recent_invoices())
        pid = db.add_pending("create_invoice", args, guard)
        db.log("ai", "proposed_payment_request", {"pending_id": pid, "guardrails": guard})
        return {"type": "approval_needed", "pending_id": pid,
                "proposal": args, "guardrails": guard}

    if parsed.get("intent") == "question":
        try:
            text = ai_service.answer_question(req.message, build_summary())
        except Exception as e:
            db.log("system", "ai_error", {"error": str(e)})
            raise HTTPException(
                503, f"The AI service is busy. Try again in a moment. ({e})")
        db.log("ai", "answered_question", {"question": req.message})
        return {"type": "answer", "text": text}

    return {"type": "answer",
            "text": "I can create payment requests or answer questions about who owes you."}


@app.get("/pending")
def pending():
    return db.list_pending()


@app.post("/approve/{pid}")
def approve(pid: int):
    p = db.get_pending(pid)
    if not p or p["status"] != "pending":
        raise HTTPException(404, "No pending action with that id")
    if not p["guardrail"]["ok"]:
        raise HTTPException(400, "Blocked by guardrails: " + "; ".join(p["guardrail"]["blocking"]))

    a = p["args"]
    currency = a.get("currency", "USD")
    try:
        order = paypal.create_order(
            description=f"Payment request for {a['client_name']}",
            items=a["items"],
            currency=currency,
            return_url=f"{BASE_URL}/paypal/return",
            cancel_url=f"{BASE_URL}/paypal/cancel",
            request_id=f"duepilot-{pid}-{uuid.uuid4().hex[:10]}",
        )
        link = paypal.approval_link(order)
    except Exception as e:
        db.log("system", "paypal_error", {"pending_id": pid, "error": str(e)})
        raise HTTPException(502, f"PayPal error: {e}")

    amount = p["guardrail"]["total"]
    try:
        message = ai_service.draft_payment_message(
            a["client_name"], amount, currency, a["due_date"], link)
    except Exception:
        message = f"Hi {a['client_name']}, please pay {amount:.2f} {currency} here: {link}"

    db.add_order(pid, order["id"], link, a["client_name"], a["client_email"],
                 amount, currency, a["due_date"], message)
    db.set_status(pid, "approved", order["id"])
    db.log("user", "approved_payment_request",
           {"pending_id": pid, "paypal_order_id": order["id"], "amount": amount})
    return {"status": "payment_link_created", "paypal_order_id": order["id"],
            "payment_link": link, "message_to_client": message}


@app.post("/reject/{pid}")
def reject(pid: int):
    p = db.get_pending(pid)
    if not p or p["status"] != "pending":
        raise HTTPException(404, "No pending action with that id")
    db.set_status(pid, "rejected")
    db.log("user", "rejected_payment_request", {"pending_id": pid})
    return {"status": "rejected"}


@app.get("/orders")
def orders():
    return [order_view(o) for o in db.list_orders()]


@app.post("/orders/{paypal_order_id}/refresh")
def refresh(paypal_order_id: str):
    return order_view(sync_order(paypal_order_id))


@app.post("/orders/{paypal_order_id}/reminder")
def reminder(paypal_order_id: str):
    """AI drafts a reminder whose tone depends on how overdue the payment is."""
    row = db.get_order_by_paypal_id(paypal_order_id)
    if not row:
        raise HTTPException(404, "Unknown order")
    if row["status"] == "paid":
        raise HTTPException(400, "This order is already paid")
    try:
        due = datetime.date.fromisoformat(row["due_date"])
        days = (datetime.date.today() - due).days
    except (ValueError, TypeError):
        days = 0
    try:
        text = ai_service.draft_reminder(row["client_name"], row["amount"],
                                         row["currency"], row["due_date"],
                                         days, row["approve_url"])
    except Exception as e:
        db.log("system", "ai_error", {"error": str(e)})
        raise HTTPException(503, f"The AI service is busy. Try again in a moment. ({e})")
    db.log("ai", "drafted_reminder", {"order": paypal_order_id, "days_overdue": days})
    return {"message": text, "days_overdue": days}


@app.get("/paypal/return", response_class=HTMLResponse)
def paypal_return(token: str):
    """PayPal sends the client here after they pay. 'token' is the order id."""
    o = sync_order(token)
    if o["status"] == "paid":
        return HTMLResponse("<h2>Payment received. Thank you!</h2>"
                            "<p>You can close this tab.</p>")
    return HTMLResponse("<h2>Payment is still processing.</h2>"
                        "<p>The freelancer will see the update shortly.</p>")


@app.get("/paypal/cancel", response_class=HTMLResponse)
def paypal_cancel():
    return HTMLResponse("<h2>Payment cancelled.</h2><p>No money was taken.</p>")


@app.get("/summary")
def summary():
    return build_summary()


@app.get("/log")
def action_log():
    return db.get_log()