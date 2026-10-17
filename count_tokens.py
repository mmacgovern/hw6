"""Problem 2: count the handbook's tokens two ways and price it.

Run with:  .venv\\Scripts\\python.exe count_tokens.py

a) Offline with tiktoken (o200k_base encoding).
b) Real check: send the handbook to gpt-6-luna through Portkey and read the
   input token count the API reports, minus a tiny baseline call.
Then work out the handbook's input cost with exact decimal math.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
ENCODING = "o200k_base"

HERE = Path(__file__).parent
HANDBOOK_PATH = HERE / "data" / "shop_handbook.md"
PRICES_PATH = HERE / "data" / "prices.json"
RESULTS_PATH = HERE / "output" / "handbook_tokens.json"

# The same short instruction goes in both calls, so subtracting cancels it out.
INSTRUCTION = "Reply with just the word OK."
MILLION = Decimal(1_000_000)


def count_offline(text: str) -> int:
    return len(tiktoken.get_encoding(ENCODING).encode(text))


def api_input_tokens(client: OpenAI, content: str) -> int:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": content}],
    )
    return response.usage.prompt_tokens


def main() -> None:
    handbook = HANDBOOK_PATH.read_text(encoding="utf-8")
    prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))[MODEL]

    # a) Offline count
    offline = count_offline(handbook)
    print(f"a) tiktoken ({ENCODING}): {offline:,} tokens")

    # b) Real count from the API
    load_dotenv(HERE / ".env")
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise SystemExit("PORTKEY_API_KEY is missing or empty in .env")
    client = OpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
    )
    with_handbook = api_input_tokens(client, handbook + "\n\n" + INSTRUCTION)
    baseline = api_input_tokens(client, INSTRUCTION)
    handbook_api = with_handbook - baseline
    print(f"b) API, handbook + instruction: {with_handbook:,} input tokens")
    print(f"   API, instruction only:       {baseline:,} input tokens")
    print(f"   Handbook alone (difference): {handbook_api:,} tokens")
    print(f"   Gap vs tiktoken: {handbook_api - offline:+,} tokens")

    # Costs, input side only, using the API-measured count
    n = Decimal(handbook_api)
    normal = Decimal(str(prices["input_per_1m"]))
    cached = Decimal(str(prices["cached_input_per_1m"]))
    write = Decimal(str(prices["cache_write_per_1m"]))

    one_no_cache = n / MILLION * normal
    thousand_no_cache = one_no_cache * 1000
    # First call writes the cache, billed at the cache-write rate
    # ($0.125, i.e. 1.25x the normal $0.10, so it already includes normal input).
    one_with_cache = n / MILLION * write
    cached_call = n / MILLION * cached
    thousand_with_cache = one_with_cache + cached_call * 999

    costs = {
        "1 call, no cache": one_no_cache,
        "1,000 calls, no cache": thousand_no_cache,
        "1 call, with cache (cache write)": one_with_cache,
        "1 later call, cached": cached_call,
        "1,000 calls, with cache": thousand_with_cache,
    }
    print("\nHandbook input cost:")
    for label, value in costs.items():
        print(f"   {label:<34} ${value}")

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "model": MODEL,
                "encoding": ENCODING,
                "tiktoken_tokens": offline,
                "api_with_handbook": with_handbook,
                "api_baseline": baseline,
                "api_handbook_tokens": handbook_api,
                "prices_per_1m": {"input": str(normal), "cached_input": str(cached),
                                  "cache_write": str(write)},
                "costs_usd": {k: str(v) for k, v in costs.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved numbers to {RESULTS_PATH.relative_to(HERE)}")


if __name__ == "__main__":
    main()
