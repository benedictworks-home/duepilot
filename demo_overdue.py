import sqlite3, datetime

d = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
c = sqlite3.connect("duepilot.db")
c.execute("""UPDATE orders SET due_date=?
             WHERE id=(SELECT id FROM orders WHERE status!='paid' ORDER BY id DESC LIMIT 1)""", (d,))
c.commit()
print("Latest unpaid order is now due", d)