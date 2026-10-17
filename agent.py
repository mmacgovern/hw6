"""Campus Customs vendor desk agent.

Run with:  .venv\\Scripts\\python.exe agent.py --doc data/practice_docs/p01_bluehen_quote.html
Add --no-cache to stop the model provider from re-using any part of the prompt.
"""

import argparse
import json
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # hide the library's startup banner

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import AgentDeps, VendorDecision, VendorDecisionWithNotes
from rules import design_check
from tools import ALL_TOOLS, READ_ONLY_TOOLS, append_json, now

MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

HERE = Path(__file__).parent
HANDBOOK_PATH = HERE / "data" / "shop_handbook.md"
PROMPT_PATH = HERE / "prompts" / "prompt.md"
PRICES_PATH = HERE / "data" / "prices.json"
USAGE_LOG = HERE / "output" / "usage_log.json"
AUDIT_TRAIL = HERE / "output" / "audit_trail.json"
MILLION = Decimal(1_000_000)

# Portkey's own response cache must stay OFF: it could replay an old answer
# without calling the model. force-refresh guarantees a real model call every time.
PORTKEY_NO_CACHE_HEADERS = {"x-portkey-cache-force-refresh": "true"}


ALL_LAYERS = frozenset({"prompt", "code", "design"})
PROMPT_LAYER_BLOCK = re.compile(r"<!-- PROMPT-LAYER START.*?<!-- PROMPT-LAYER END -->\n\n", re.S)


def base_instructions(layers: frozenset = ALL_LAYERS) -> str:
    # Handbook first and unchanged on every call, so the model provider can cache it.
    # Nothing that changes per document goes in here; the document path goes in the user message.
    handbook = HANDBOOK_PATH.read_text(encoding="utf-8")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if "prompt" not in layers:
        prompt = PROMPT_LAYER_BLOCK.sub("", prompt)  # back to the Problem 3 prompt
    return handbook + "\n\n---\n\n" + prompt


def build_agent(no_cache: bool, portkey_statuses: list[str], layers: frozenset = ALL_LAYERS) -> Agent:
    load_dotenv(HERE / ".env")
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise SystemExit("PORTKEY_API_KEY is missing or empty in .env")

    async def note_portkey_cache(response: httpx.Response) -> None:
        # Portkey reports whether it answered from its own cache (HIT) or not.
        portkey_statuses.append(response.headers.get("x-portkey-cache-status", "not reported"))

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key, **PORTKEY_NO_CACHE_HEADERS},
        http_client=httpx.AsyncClient(event_hooks={"response": [note_portkey_cache]}),
    )
    model = OpenAIResponsesModel(MODEL, provider=OpenAIProvider(openai_client=client))
    instructions = base_instructions(layers)

    if no_cache:
        # A function is re-run before EVERY model call, so each call starts with a
        # different random line and no prefix can ever match an earlier call.
        def fresh_instructions() -> str:
            return f"Request ID: {uuid.uuid4()}\n\n{instructions}"
        agent_instructions = fresh_instructions
    else:
        agent_instructions = instructions

    return Agent(
        model,
        # Prompt layer: the model also reports suspicious text (it never acts on it).
        output_type=VendorDecisionWithNotes if "prompt" in layers else VendorDecision,
        instructions=agent_instructions,
        deps_type=AgentDeps,
        # Design layer: the model may only read; trap tools need human_signoff().
        tools=READ_ONLY_TOOLS if "design" in layers else ALL_TOOLS,
    )


def parse_layers(value: str) -> frozenset:
    layers = frozenset(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = layers - ALL_LAYERS
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown layer(s): {', '.join(sorted(unknown))}")
    return layers


def prices() -> dict:
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))[MODEL]


def cost_breakdown(input_tokens: int, cached: int, cache_write: int, output: int) -> dict:
    p = prices()
    p_in = Decimal(str(p["input_per_1m"]))
    p_cached = Decimal(str(p["cached_input_per_1m"]))
    p_write = Decimal(str(p["cache_write_per_1m"]))
    p_out = Decimal(str(p["output_per_1m"]))
    # input_tokens already includes cached and cache-write tokens; split them out.
    uncached = input_tokens - cached - cache_write
    parts = {
        "uncached_input": Decimal(uncached) / MILLION * p_in,
        "cached_input": Decimal(cached) / MILLION * p_cached,
        "cache_write": Decimal(cache_write) / MILLION * p_write,
        "output": Decimal(output) / MILLION * p_out,
    }
    return {
        "uncached_input_tokens": uncached,
        "math": {
            "uncached_input": f"{uncached} / 1,000,000 x ${p_in} = ${parts['uncached_input']}",
            "cached_input": f"{cached} / 1,000,000 x ${p_cached} = ${parts['cached_input']}",
            "cache_write": f"{cache_write} / 1,000,000 x ${p_write} = ${parts['cache_write']}",
            "output": f"{output} / 1,000,000 x ${p_out} = ${parts['output']}",
        },
        "total_usd": sum(parts.values()),
    }


def usage_dict(u) -> dict:
    """Every token count the API reports, for one call or a whole run."""
    return {
        "input_tokens": u.input_tokens,
        "cached_tokens": u.cache_read_tokens,
        "cache_write_tokens": u.cache_write_tokens,
        "output_tokens": u.output_tokens,
        "total_tokens": u.input_tokens + u.output_tokens,
        "details": dict(u.details),
    }


def run_document(doc: str, no_cache: bool = False, layers: frozenset = ALL_LAYERS) -> dict:
    """Run the agent on one document, write the logs, and return everything measured.

    layers: which defenses are on ("prompt", "code", "design"); empty = --no-defense.
    """
    layers = frozenset(layers)
    setup = "without_cache" if no_cache else "with_cache"
    portkey_statuses: list[str] = []
    agent = build_agent(no_cache, portkey_statuses, layers)
    deps = AgentDeps(document=doc, layers=layers)
    result = agent.run_sync(f"Review the vendor document at this path: {doc}", deps=deps)

    model_output = result.output.model_dump()
    suspicious_text = model_output.pop("suspicious_text", [])
    design_notes = None
    if "design" in layers:
        # Python re-checks the model's answer against the handbook; Python wins.
        final, design_notes = design_check(model_output, deps.document_text, deps.sanitize_report)
        answer = VendorDecision(**final)
    else:
        answer = VendorDecision(**model_output)

    # One agent run can make several model calls; keep each one.
    responses = [m for m in result.all_messages() if isinstance(m, ModelResponse)]
    calls = []
    for i, response in enumerate(responses, start=1):
        u = usage_dict(response.usage)
        c = cost_breakdown(u["input_tokens"], u["cached_tokens"], u["cache_write_tokens"], u["output_tokens"])
        calls.append({
            "call": i,
            "model_reported_by_api": response.model_name,
            **u,
            "uncached_input_tokens": c["uncached_input_tokens"],
            "cost_math": c["math"],
            "cost_usd": str(c["total_usd"]),
            "portkey_cache_status": portkey_statuses[i - 1] if i <= len(portkey_statuses) else "not reported",
        })

    usage = {**usage_dict(result.usage), "requests": result.usage.requests}
    cost = cost_breakdown(usage["input_tokens"], usage["cached_tokens"],
                          usage["cache_write_tokens"], usage["output_tokens"])

    time = now()
    layer_names = sorted(layers) or ["none"]
    append_json(USAGE_LOG, {
        "document": doc,
        "time": time,
        "model": MODEL,
        "setup": setup,
        "defense_layers": layer_names,
        **usage,
        "uncached_input_tokens": cost["uncached_input_tokens"],
        "cost_math": cost["math"],
        "cost_usd": str(cost["total_usd"]),
        "calls": calls,
    })
    audit = {
        "document": doc,
        "time": time,
        "setup": setup,
        "defense_layers": layer_names,
        "tool_calls": deps.tool_calls,
    }
    if "code" in layers:
        audit["sanitizer"] = deps.sanitize_report      # what was removed or flagged
    if "prompt" in layers:
        audit["model_reported_suspicious_text"] = suspicious_text
    if design_notes is not None:
        audit["design_check"] = design_notes            # model answer vs. Python rules
    audit["final_answer"] = answer.model_dump()
    append_json(AUDIT_TRAIL, audit)
    return {"document": doc, "setup": setup, "layers": layers, "answer": answer, "usage": usage,
            "cost": cost, "calls": calls, "sanitizer": deps.sanitize_report,
            "suspicious_text": suspicious_text, "design_check": design_notes}


def print_summary(doc: str, answer: VendorDecision, usage: dict, cost: dict) -> None:
    def show(value, fmt="{}"):
        return "unknown" if value is None else fmt.format(value)

    line = "=" * 60
    print(line)
    print(f" VENDOR DESK RESULT  |  {Path(doc).name}")
    print(line)
    print(f" Vendor:         {show(answer.vendor)}")
    print(f" SKU:            {show(answer.sku)}")
    print(f" Unit price:     {show(answer.unit_price, '${:,.2f}')}")
    print(f" Lead time:      {show(answer.lead_time_days, '{} days')}")
    print(f" Minimum order:  {show(answer.min_order, '{:,} units')}")
    print(line)
    print(f" DECISION:       {answer.decision.upper()}")
    print(f" Reason:         {answer.reason}")
    print(line)
    print(f" Tokens:  input {usage['input_tokens']:,} (cached {usage['cached_tokens']:,})"
          f"  |  output {usage['output_tokens']:,}  |  total {usage['total_tokens']:,}"
          f"  |  {usage['requests']} API calls")
    for name, step in cost["math"].items():
        print(f"   {name.replace('_', ' '):<15} {step}")
    print(f" Cost:    ${cost['total_usd']}")
    print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("--doc", required=True, help="Path to a vendor document (.html, .pdf, .eml)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Start every model call with a random line so nothing can be cached")
    parser.add_argument("--layers", type=parse_layers, default=ALL_LAYERS,
                        help="Defense layers to turn on, e.g. prompt,code,design (default: all three)")
    parser.add_argument("--no-defense", action="store_true",
                        help="Turn every defense off (the original Problem 3 agent)")
    args = parser.parse_args()
    layers = frozenset() if args.no_defense else args.layers

    run = run_document(args.doc, no_cache=args.no_cache, layers=layers)
    print_summary(args.doc, run["answer"], run["usage"], run["cost"])
    print(f" Defenses on: {', '.join(sorted(layers)) or 'none (--no-defense)'}")
    if run["sanitizer"]:
        print(f" Code layer removed {len(run['sanitizer']['removed'])} item(s), "
              f"flagged {len(run['sanitizer']['flags'])}")
    if run["suspicious_text"]:
        print(f" Model reported suspicious text: {run['suspicious_text']}")
    if run["design_check"] and run["design_check"]["python_overrode_model"]:
        print(" Python rule check OVERRODE the model's decision")


if __name__ == "__main__":
    main()
