# DuePilot

**Chat to get paid.** DuePilot is an AI agent that turns a plain-English message into a
PayPal payment request, checks it with safety guardrails, waits for human approval,
writes the message to the client, and tracks whether you've been paid.

Built for the *Build What's Next with PayPal and AI* hackathon.

**Live demo:** <https://duepilot-nir9.onrender.com/> (PayPal **sandbox**, test money only)

## What it does

1. **Chat to payment request:** "Invoice Ada (ada@example.com) for 5 logo drafts at $150 each, due in 2 weeks" becomes a structured request.
2. **Guardrails:** every request is checked before anything touches money (valid email, amounts and quantities, a safety cap, future due date, supported currency, duplicate detection).
3. **Human approval:** the agent only proposes. Nothing is created in PayPal until you click Approve.
4. **PayPal payment link:** on approval, DuePilot creates a PayPal order and a checkout link.
5. **AI client message:** the agent drafts the message you send with the link.
6. **Payment tracking:** when the client pays, DuePilot captures the payment through PayPal and marks it paid.
7. **Smart reminders:** for unpaid requests, the AI drafts a reminder whose tone depends on how overdue it is (friendly, polite, firm).
8. **Ask your money:** "Who owes me money?" is answered from your real payment data.
9. **Action log:** every step (user, AI, system) is recorded and shown in the UI.

## Tools used

| Tool | How it is used |
|---|---|
| **PayPal Orders API v2 (sandbox)** | Creates payment orders and checkout links, reads order status, captures payments after the buyer approves |
| **Google Gemini (`gemini-2.5-flash`, fallback `gemini-2.5-flash-lite`)** | (1) Parses messy text into structured JSON, (2) writes client payment messages, (3) writes tone-adaptive reminders, (4) answers questions about payment data |
| FastAPI, SQLite | Backend API and storage (payment requests, orders, action log) |
| Plain HTML/CSS/JS | Single-page frontend |

## Architecture

```
Browser (chat, approval cards, orders table, action log)
        |  REST/JSON
FastAPI backend
  /chat ---> Gemini parses intent --> Guardrails --> pending approval (SQLite)
  /approve -> PayPal Orders API: create order --> checkout link --> Gemini drafts message
  /paypal/return <- client redirected here after paying --> capture order --> mark paid
  /summary, /orders, /log, /orders/{id}/reminder
        |                     |                    |
   Gemini API         PayPal Sandbox          SQLite
```

## Run it locally

Requirements: Python 3.10+, a PayPal developer account (free sandbox), a Google AI API key.

```bash
git clone <this repo>
cd duepilot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your keys
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

`.env` values:

```
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_SECRET=your_sandbox_secret
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
GOOGLE_API_KEY=your_google_ai_key
APP_BASE_URL=http://127.0.0.1:8000
```

Get the PayPal values from developer.paypal.com > Apps & Credentials (Sandbox) > Create App.

## Try it (sandbox)

1. Type a payment request in the chat and approve it.
2. Open the generated payment link in a private window.
3. Log in with your sandbox **Personal** account (developer.paypal.com > Testing tools >
   Sandbox accounts > View/edit account) and pay.
4. You are redirected back and the request shows as **Paid**.

## Design notes

- **Safe by design:** the AI proposes, guardrails evaluate, a human approves. Blocked
  requests cannot be approved.
- **Resilient AI calls:** automatic retry and a fallback model when Gemini is busy.
- **Limitations:** sandbox only; SQLite storage resets on free hosting; reminders are
  drafted for you to send rather than sent automatically.

## License

MIT