import os, json, time, datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Tried in order. If the first is overloaded (503), the second is used.
MODELS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]

client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY"),
    http_options={"api_version": "v1beta"},
)


def _generate(prompt, json_mode=False, rounds=2):
    """Calls Gemini. If a model is busy, tries the next one, then waits and retries."""
    config = (types.GenerateContentConfig(response_mime_type="application/json")
              if json_mode else None)
    last_error = None
    for rnd in range(rounds):
        for model in MODELS:
            try:
                return client.models.generate_content(
                    model=model, contents=prompt, config=config).text
            except Exception as e:
                last_error = e
        time.sleep(2 * (rnd + 1))  # wait 2s, then 4s, between rounds
    raise last_error


def _clean_json(text):
    """Parses JSON even if the model wrapped it in ``` fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def parse_request(message: str) -> dict:
    today = datetime.date.today().isoformat()
    prompt = f"""You are the intent parser for a freelancer payment-request assistant.
Today's date is {today}. Convert relative dates (e.g. "in 2 weeks") into YYYY-MM-DD.

Return ONLY JSON in this shape:
{{
  "intent": "create_invoice" | "question" | "other",
  "client_name": string or null,
  "client_email": string or null,
  "currency": "USD",
  "items": [{{"name": string, "quantity": number, "unit_amount": number}}],
  "due_date": "YYYY-MM-DD" or null
}}
Use "question" for anything asking about payments, who owes money, or earnings.
Never invent an email address; use null if none is given.

User message: {message}"""
    return _clean_json(_generate(prompt, json_mode=True))


def answer_question(question: str, data: dict) -> str:
    payload = json.dumps(data, default=str)[:20000]
    prompt = f"""You are a helpful assistant for a freelancer. Answer the question using
ONLY the payment data below. Be concise. If the data doesn't contain the answer, say so.

Payment data (state can be paid, awaiting_payment, or overdue):
{payload}

Question: {question}"""
    return _generate(prompt).strip()


def draft_payment_message(client_name, amount, currency, due_date, link, tone="friendly"):
    prompt = f"""Write a short, {tone} message (maximum 80 words) from a freelancer to a client
asking for payment.
Client name: {client_name}
Amount: {amount:.2f} {currency}
Due date: {due_date}
Payment link: {link}
Include the payment link exactly once. Do not add a subject line.
Do not invent the freelancer's name. End with "Thank you!"."""
    return _generate(prompt).strip()


def draft_reminder(client_name, amount, currency, due_date, days_overdue, link):
    """Reminder whose tone depends on how late the payment is."""
    if days_overdue <= 0:
        tone = "warm and friendly"
        context = f"The payment is due on {due_date} and is not overdue yet."
    elif days_overdue <= 7:
        tone = "polite but clear"
        context = f"The payment is {days_overdue} day(s) overdue (it was due on {due_date})."
    else:
        tone = "firm but professional"
        context = f"The payment is {days_overdue} days overdue (it was due on {due_date})."

    prompt = f"""Write a short {tone} payment reminder (maximum 80 words) from a freelancer
to a client.
Client name: {client_name}
Amount: {amount:.2f} {currency}
{context}
Payment link: {link}
Include the payment link exactly once. Do not add a subject line.
Do not invent the freelancer's name. End with "Thank you!"."""
    return _generate(prompt).strip()