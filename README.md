# Campus Customs Vendor Desk Agent (HW6)

An AI agent that reads a vendor document (quote, invoice, catalog page or email), pulls out the vendor, SKU, unit price, lead time and minimum order, and recommends buying or not based on `data/shop_handbook.md`. It uses only the model `gpt-6-luna`, through Portkey. Three defense layers (code, design, prompt) protect it from hidden instructions in vendor documents, and it can never send email or approve payment on its own.

**Results:** open `output/hw6_report.html` in any browser (no internet needed).

**Model:** every AI call requests exactly `gpt-6-luna` (see `MODEL` in `agent.py`), and no other model name is used anywhere in the code. In the logs (`output/exam_run_details.json`, `output/usage_log.json`) and the report you will also see `gpt-6-luna-global`. That is not a second model: it is the name the API sends back for the global deployment that serves gpt-6-luna, recorded exactly as the API reported it.

## How to run

1. **Install the requirements** (once, from this folder):
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Add your key:** copy `.env.example` to `.env`, then replace the placeholder with your own `PORTKEY_API_KEY`. `.env` is listed in `.gitignore`, so it is never committed.
3. **Run the agent on one document:**
   ```
   python agent.py --doc data/practice_docs/p01_bluehen_quote.html
   ```
   It prints the extracted facts, the decision, a one-sentence reason, the tokens used and the cost (with the math).
4. **Options:**
   - `--no-defense`: turn off all defenses (the original, undefended agent).
   - `--no-cache`: start every model call with a random line, so the prompt cache can't be reused.
   - `--layers prompt,code,design`: choose which defense layers to use (all three are on by default).
5. **Rerun the tests** (each one calls the model and takes several minutes):
   ```
   python count_tokens.py       # Problem 2: handbook token count and cost estimate
   python cache_test.py         # Problem 4: 12 practice documents with and without cache
   python attack_test.py        # Problem 5: 12 practice documents with no defenses
   python defense_test.py       # Problem 6: 12 practice documents under 4 defense setups
   python red_team_test.py      # Problem 7: our attack files, no defense vs. full defense
   python run_exam.py           # Problem 8: the 10 exam documents with all defenses
   python build_report.py       # Problem 9: rebuild output/hw6_report.html (no model calls)
   python make_red_team_pdf.py  # Problem 7: rebuild the a2 PDF attack file (no model calls)
   python -m pytest             # human sign-off tests (no model calls; uses a temporary trap log)
   ```
   `output/p3_demo_runs.txt` shows the terminal output of `python agent.py` on p01 and p08.
6. **Check the logs** in `output/`: `usage_log.json` (tokens and cost), `audit_trail.json` (tool calls, what the defenses removed or flagged, and the final answers) and `trap_calls.json` (any attempt to use the fake `send_email` / `approve_payment` tools).

## Files

| File | What it is |
|---|---|
| `agent.py` | Entry point: runs the agent on one document |
| `tools.py` | `read_document`, plus the trap tools `send_email` / `approve_payment` (they only log; nothing is sent or paid) |
| `models.py` | The structured answer the agent must return |
| `prompts/prompt.md` | The agent's instructions and buying rules |
| `sanitize.py`, `rules.py` | Code and design defense layers |
| `AI_prompts.md` | Every prompt used to build this project, by problem |
| `output/` | All results and reports |
