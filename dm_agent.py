import os
import json
import requests
from groq import Groq
from dotenv import load_dotenv
from datetime import date

load_dotenv()

def extract_order_from_dm(dm_text, stock, active_combos):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    flavour_lines = "\n".join(
        f"- {key} = {key.replace('_slapp', '').replace('_', ' ').title()} SLAPP"
        for key in stock.keys()
    )

    system_prompt = f"""You are an order extraction assistant for SLAPP, a cookie brand in Bangalore.
Extract order details from Instagram DMs and return ONLY valid JSON, no explanation.

FLAVOURS (use these exact keys):
{flavour_lines}

CURRENT STOCK: {json.dumps(stock)}
ACTIVE COMBOS: {json.dumps(active_combos)}
TODAY: {date.today()}

Return JSON:
{{
    "name": "customer name or null",
    "phone": "phone number or null",
    "address": "full delivery address or null",
    "delivery_date": "YYYY-MM-DD or null",
    "items": {{"flavour_key": quantity}},
    "notes": "special instructions or null",
    "delivery_required": true or false,
    "missing": ["list of missing required fields"]
}}

Convert relative dates like 'tomorrow', 'next saturday' to YYYY-MM-DD based on today being {date.today()}.

For "delivery_required": default to true (Porter delivery). Set it to false ONLY if the DM clearly says the
customer will pick it up themselves, is a college friend collecting it in person, or otherwise explicitly
says no delivery is needed.

Return ONLY the JSON object."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": dm_text}
        ],
        temperature=0
    )
    
    raw = response.choices[0].message.content.strip()
    clean = raw.strip().strip('`').strip()
    if clean.startswith('json'):
        clean = clean[4:].strip()
    
    extracted = json.loads(clean)

    return extracted