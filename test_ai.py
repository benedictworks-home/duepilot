import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Load the environment variables from your .env file
load_dotenv()

# 2. Initialize the client using your new Google key
from google.genai.types import HttpOptions

client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY"),
    http_options={'api_version': 'v1beta'}
)

# 3. Define the schema for your invoice
invoice_schema = {
    "type": "object",
    "properties": {
        "client_name": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "number"}
                },
                "required": ["description", "quantity", "unit_price"]
            }
        },
        "due_date": {"type": "string"}
    },
    "required": ["client_name", "items", "due_date"]
}

# 4. Make the API call
print("Sending request to Gemini...")
response = client.models.generate_content(
    model='gemini-2.5-flash', 
    contents='Client Ada wants 5 logo drafts, $150 each, due in 2 weeks',
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_json_schema=invoice_schema
    )
)

# 5. Print the result
print("\n--- GEMINI RESPONSE ---")
print(response.text)