"""Tiny smoke test: send one message to gpt-6-luna through Portkey.

Run with:  .venv\\Scripts\\python.exe test_portkey.py
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

load_dotenv()
api_key = os.getenv("PORTKEY_API_KEY")

# Only report whether the key exists; never print its value.
if not api_key:
    raise SystemExit("PORTKEY_API_KEY is missing or empty in .env")
print("PORTKEY_API_KEY found in .env (value hidden)")

client = OpenAI(
    api_key=api_key,
    base_url=PORTKEY_BASE_URL,
    default_headers={"x-portkey-api-key": api_key},
)

response = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Say hello in five words"}],
)

print("Model:", response.model)
print("Reply:", response.choices[0].message.content)
usage = response.usage
print("Input tokens: ", usage.prompt_tokens)
print("Output tokens:", usage.completion_tokens)
print("Total tokens: ", usage.total_tokens)
