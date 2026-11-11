import os, json, datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# 1. Fixed the model name so it matches what worked in your test
MODEL = "gemini-2.5-flash"

# 2. The v1beta fix is correctly here
client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY"),
    http_options={"api_version": "v1beta"}
)

def parse_request(message: str) -> dict:
    today = datetime.date.today().isoformat()
    prompt = f"""You are the intent parser for a freelancer invoicing assistant.
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
Use "question" for anything asking about invoices, who owes money, or earnings.
Never invent an email address; use null if none is given.

User message: {message}"""
    
    # 3. Updated to use types.GenerateContentConfig for safety
    resp = client.models.generate_content(
        model=MODEL, 
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(resp.text)

def answer_question(question: str, invoice_data: dict) -> str:
    data = json.dumps(invoice_data)[:20000]
    prompt = f"""You are a helpful assistant for a freelancer. Answer the question using
ONLY the PayPal invoice data below. Be concise. If the data doesn't contain the answer, say so.

Invoice data:
{data}

Question: {question}"""
    
    resp = client.models.generate_content(
        model=MODEL, 
        contents=prompt
    )
    return resp.text

def draft_payment_message(client_name, amount, currency, due_date, link, tone="friendly"):
    prompt = f"""Write a short, {tone} message (maximum 80 words) from a freelancer to a client
asking for payment.
Client name: {client_name}
Amount: {amount:.2f} {currency}
Due date: {due_date}
Payment link: {link}
Include the payment link exactly once. Do not add a subject line.
Do not invent the freelancer's name. End with "Thank you!"."""
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text.strip()