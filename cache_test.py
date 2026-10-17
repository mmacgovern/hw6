"""Problem 4: run all 12 practice documents WITH and WITHOUT the prompt cache.

Run with:  .venv\\Scripts\\python.exe cache_test.py

Saves every model call to output/cache_test.json and prints the proof checks.
"""

import json
from decimal import Decimal
from pathlib import Path

from agent import run_document

HERE = Path(__file__).parent
DOCS = sorted((HERE / "data" / "practice_docs").iterdir())
KEY = {e["file"]: e for e in json.loads((HERE / "data" / "practice_key.json").read_text(encoding="utf-8"))}
HANDBOOK_TOKENS = json.loads((HERE / "output" / "handbook_tokens.json").read_text(encoding="utf-8"))["api_handbook_tokens"]
OUT = HERE / "output" / "cache_test.json"

# "Close to the handbook size": at least 90% of the handbook's tokens were reused.
CLOSE_ENOUGH = 0.9


def main() -> None:
    records = []
    for no_cache in (False, True):
        for doc in DOCS:
            rel = doc.relative_to(HERE).as_posix()
            run = run_document(rel, no_cache=no_cache, layers=frozenset())  # Problem 4: no defenses
            matches_key = run["answer"].decision == KEY[doc.name]["decision"]
            for call in run["calls"]:
                records.append({
                    "setup": run["setup"],
                    "document": doc.name,
                    **call,
                    "decision": run["answer"].decision,
                    "decision_matches_key": matches_key,
                })
            print(f"{run['setup']:<14} {doc.name:<30} calls {len(run['calls'])}  "
                  f"cached {[c['cached_tokens'] for c in run['calls']]}  ${run['cost']['total_usd']}")

    OUT.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nSaved {len(records)} model calls to {OUT.relative_to(HERE)}")

    # --- Proof checks ---
    without = [r for r in records if r["setup"] == "without_cache"]
    with_cache = [r for r in records if r["setup"] == "with_cache"]
    bad_without = [r for r in without if r["cached_tokens"] != 0]
    first, later = with_cache[0], with_cache[1:]
    bad_with = [r for r in later if r["cached_tokens"] < CLOSE_ENOUGH * HANDBOOK_TOKENS]
    portkey_hits = [r for r in records if r["portkey_cache_status"].upper() == "HIT"]

    print("\nPROOF CHECKS")
    print(f" Without cache: {len(without)} calls, {len(bad_without)} with cached tokens > 0 "
          f"-> {'PASS' if not bad_without else 'FAIL'}")
    print(f" With cache: first call cached {first['cached_tokens']:,} tokens "
          f"({'warm from earlier runs' if first['cached_tokens'] else 'cold, as expected'})")
    print(f" With cache: {len(later)} later calls, {len(bad_with)} below "
          f"{CLOSE_ENOUGH:.0%} of the {HANDBOOK_TOKENS:,}-token handbook -> {'PASS' if not bad_with else 'FAIL'}")
    for r in bad_with:
        print(f"   low: {r['document']} call {r['call']} cached {r['cached_tokens']:,}")
    print(f" Portkey response-cache hits: {len(portkey_hits)} -> {'PASS' if not portkey_hits else 'FAIL'}")

    for setup, rows in (("with_cache", with_cache), ("without_cache", without)):
        total = sum(Decimal(r["cost_usd"]) for r in rows)
        print(f" {setup:<14} total ${total}  per document ${total / len(DOCS)}")


if __name__ == "__main__":
    main()
