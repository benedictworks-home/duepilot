import sqlite3, json, datetime

DB = "duepilot.db"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pending_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool TEXT, args_json TEXT, guardrail_json TEXT,
            status TEXT DEFAULT 'pending', paypal_id TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS action_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT, event TEXT, details_json TEXT, timestamp TEXT)""")

def log(actor, event, details=None):
    with conn() as c:
        c.execute("INSERT INTO action_log(actor,event,details_json,timestamp) VALUES(?,?,?,?)",
                  (actor, event, json.dumps(details or {}), now()))

def add_pending(tool, args, guard):
    with conn() as c:
        cur = c.execute(
            "INSERT INTO pending_actions(tool,args_json,guardrail_json,created_at) VALUES(?,?,?,?)",
            (tool, json.dumps(args), json.dumps(guard), now()))
        return cur.lastrowid

def _row(r):
    return {"id": r["id"], "tool": r["tool"], "args": json.loads(r["args_json"]),
            "guardrail": json.loads(r["guardrail_json"]), "status": r["status"],
            "paypal_id": r["paypal_id"], "created_at": r["created_at"]}

def get_pending(pid):
    with conn() as c:
        r = c.execute("SELECT * FROM pending_actions WHERE id=?", (pid,)).fetchone()
    return _row(r) if r else None

def list_pending(status="pending"):
    with conn() as c:
        rows = c.execute("SELECT * FROM pending_actions WHERE status=? ORDER BY id DESC", (status,)).fetchall()
    return [_row(r) for r in rows]

def set_status(pid, status, paypal_id=None):
    with conn() as c:
        c.execute("UPDATE pending_actions SET status=?, paypal_id=? WHERE id=?", (status, paypal_id, pid))

def recent_invoices():
    """Pending + approved invoice proposals, used for duplicate detection."""
    with conn() as c:
        rows = c.execute("SELECT * FROM pending_actions WHERE status IN ('pending','approved')").fetchall()
    return [_row(r) for r in rows]

def get_log(limit=50):
    with conn() as c:
        rows = c.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"actor": r["actor"], "event": r["event"],
             "details": json.loads(r["details_json"]), "timestamp": r["timestamp"]} for r in rows]

def init_orders():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pending_id INTEGER, paypal_order_id TEXT UNIQUE, approve_url TEXT,
            client_name TEXT, client_email TEXT, amount REAL, currency TEXT,
            due_date TEXT, message TEXT, status TEXT DEFAULT 'awaiting_payment',
            created_at TEXT, paid_at TEXT)""")

def add_order(pending_id, paypal_order_id, approve_url, client_name, client_email,
              amount, currency, due_date, message):
    with conn() as c:
        c.execute("""INSERT INTO orders(pending_id,paypal_order_id,approve_url,client_name,
                     client_email,amount,currency,due_date,message,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (pending_id, paypal_order_id, approve_url, client_name, client_email,
                   amount, currency, due_date, message, now()))

def list_orders():
    with conn() as c:
        rows = c.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

def get_order_by_paypal_id(paypal_order_id):
    with conn() as c:
        r = c.execute("SELECT * FROM orders WHERE paypal_order_id=?", (paypal_order_id,)).fetchone()
    return dict(r) if r else None

def mark_paid(paypal_order_id):
    with conn() as c:
        c.execute("UPDATE orders SET status='paid', paid_at=? WHERE paypal_order_id=?",
                  (now(), paypal_order_id))