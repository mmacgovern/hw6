"""Problem 8: run the final agent (all defenses, caching on) over every exam document.

Run with:  .venv\\Scripts\\python.exe -u run_exam.py

1. Backs up output/trap_calls.json to output/trap_backups/ and resets it to [].
2. Runs every file in data/exam_docs/ with all three defense layers.
3. Saves output/exam_results.json (exactly the required keys) and
   output/exam_run_details.json (per-call model names, defense notes) for review.
Results are written exactly as the agent returned them; nothing is edited.
"""

import json
import shutil
from decimal import Decimal
from pathlib import Path

from agent import ALL_LAYERS, MODEL, run_document

HERE = Path(__file__).parent
EXAM_DIR = HERE / "data" / "exam_docs"
TRAP_LOG = HERE / "output" / "trap_calls.json"
BACKUP = HERE / "output" / "trap_backups" / "trap_calls_before_exam.json"
RESULTS = HERE / "output" / "exam_results.json"
DETAILS = HERE / "output" / "exam_run_details.json"

# The exam answer format spells the negative decision with spaces.
DECISION_LABEL = {"recommend": "recommend", "do_not_recommend": "do not recommend"}


def main() -> None:
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(TRAP_LOG, BACKUP)
    TRAP_LOG.write_text("[]", encoding="utf-8")

    results, details = [], []
    for doc in sorted(EXAM_DIR.iterdir()):
        before = len(json.loads(TRAP_LOG.read_text(encoding="utf-8")))
        run = run_document(doc.relative_to(HERE).as_posix(), no_cache=False, layers=ALL_LAYERS)
        traps = json.loads(TRAP_LOG.read_text(encoding="utf-8"))[before:]
        a = run["answer"]
        u = run["usage"]
        results.append({
            "file": doc.name,
            "vendor": a.vendor,
            "sku": a.sku,
            "unit_price": a.unit_price,
            "lead_time_days": a.lead_time_days,
            "min_order": a.min_order,
            "decision": DECISION_LABEL[a.decision],
            "reason": a.reason,
            "trap_tool_called": bool(traps),
            "input_tokens": u["input_tokens"],
            "cached_tokens": u["cached_tokens"],
            "output_tokens": u["output_tokens"],
            "cost_usd": float(Decimal(run["cost"]["total_usd"])),
        })
        details.append({
            "file": doc.name,
            "model_requested": MODEL,
            "models_reported_by_api": [c["model_reported_by_api"] for c in run["calls"]],
            "model_calls": len(run["calls"]),
            "cache_write_tokens": u["cache_write_tokens"],
            "cost_usd_exact": str(run["cost"]["total_usd"]),
            "trap_calls": traps,
            "sanitizer": run["sanitizer"],
            "model_reported_suspicious_text": run["suspicious_text"],
            "design_check": run["design_check"],
        })
        r = results[-1]
        print(f"{doc.name:<18} {str(r['vendor']):<26} {str(r['sku']):<10} {r['unit_price']!s:>7} "
              f"{r['lead_time_days']!s:>4}d {r['min_order']!s:>5}u  {r['decision']:<17} "
              f"trap={r['trap_tool_called']}  ${r['cost_usd']:.8f}", flush=True)

    RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
    DETAILS.write_text(json.dumps(details, indent=2), encoding="utf-8")
    print(f"\nSaved {RESULTS.relative_to(HERE)} and {DETAILS.relative_to(HERE)}")


if __name__ == "__main__":
    main()
