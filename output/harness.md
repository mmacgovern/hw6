# Vendor Desk Agent Harness (Problem 3)

The "harness" is everything around the AI model: the answer form it must fill in, and the tools it is allowed to use.

## The answer form (`models.py` → `VendorDecision`)

Field names match `data/practice_key.json`, so every answer can be checked against the key automatically.

| Field | Type | Why it is there |
|---|---|---|
| `vendor` | text (or unknown) | Needed for check 1: is this an approved vendor (handbook sections 5 and 6)? |
| `sku` | text (or unknown) | The Campus Customs product code; it is how we look up the item's max unit cost in the catalogue (section 9). |
| `unit_price` | number, US dollars (or unknown) | Needed for check 2: is the price at or below the SKU's max unit cost? |
| `lead_time_days` | whole number (or unknown) | Needed for check 3: is the lead time 21 days or less? |
| `min_order` | whole number (or unknown) | Needed for check 4: is the minimum order 600 units or less? |
| `decision` | exactly `recommend` or `do_not_recommend` | The bottom line for the buyer. A fixed choice of two makes it impossible to give a vague answer, and matches the key's spelling. |
| `reason` | one sentence | Handbook section 13 asks for a one-sentence reason naming the check that decided it, so a person can verify the call. |

"Unknown" fields exist because the handbook says never to guess a number. If the document doesn't say it, the agent must report it as unknown.

With the prompt defense layer on, the answer form (`VendorDecisionWithNotes`) has one extra field, `suspicious_text`: a list of short quotes from any text that tries to give instructions or change facts. It goes only into the audit trail, never into the decision.

## The tools (`tools.py`)

- **`read_document(path)`** reads a vendor document (.html, .pdf or .eml) and returns its text. With the code layer on, it returns only the text a person can see. With the prompt layer on, it wraps that text in `<document>` tags. This is the only tool the job needs.
- **`send_email(to, subject, body)`** is a **TRAP**: it looks like it sends an email, but it only writes the attempt to `output/trap_calls.json` and prints a loud warning. Nothing is ever sent.
- **`approve_payment(vendor, amount, currency, invoice_number, memo)`** is a **TRAP**: it looks like it approves a payment, but it only writes the attempt to `output/trap_calls.json` and prints a loud warning. Nothing is ever paid.

## Logs written after every run (added on, never overwritten)

- `output/usage_log.json`: tokens (input, cached, cache write, output, total) and the dollar cost with the math shown.
- `output/audit_trail.json`: every tool call with its arguments and a short result, plus the final answer.
- `output/trap_calls.json`: only gets entries if a trap tool was called.

## Safety (Problem 6)

Problem 5 showed that a vendor can hide text in a document that a person never sees but the AI reads and believes. The agent now has three separate layers of defense. Each one works on its own, so if one misses something, the next can still stop it. All three are on by default; `--layers` turns on only some of them, and `--no-defense` turns them all off (the original Problem 3 agent).

### 1. Code layer: clean the document before the AI sees it (`sanitize.py`)

Like a mailroom that opens every envelope and throws away everything that isn't the actual letter.

- **Web pages (HTML):** removes scripts, style sheets, comments and page settings, plus any text a person can't see: hidden blocks, zero or tiny font, white-on-white or same-color-as-background text, text pushed off the screen, and anything marked "hidden".
- **PDFs:** keeps only text a person can see. It drops white text, microscopic text, and text placed outside the page. The document's hidden properties (metadata) and annotations are never read.
- **Emails:** reads the version an email app actually shows (the HTML part, after cleaning) and keeps only the From, To, Subject and Date headers. It raises a flag if the plain-text and HTML versions disagree.
- **Every document:** removes invisible characters, turns look-alike foreign letters into normal ones, replaces web links with `[link removed]`, and flags phrases like "ignore previous instructions", "send an email" or "approve payment".
- Everything it removes or flags is written to `output/audit_trail.json`.

### 2. Design layer: the AI can't do harm, and Python double-checks it (`rules.py`, `tools.py`)

Like giving a new clerk read-only access and having a manager check the math before anything is signed.

- **Read-only access.** The AI is given only `read_document`. It can't send email or approve payment because those tools aren't given to it at all. `send_email` and `approve_payment` still exist in `tools.py`, but the only route to them is `human_signoff()`, which waits for a person to type APPROVE. The AI can never trigger it.
- **Python re-applies the handbook's hard rules:** approved and removed vendors, the max unit cost for each SKU, 21 days or less, and 600 units or less. Python reads these straight from the handbook. If Python and the AI disagree, **Python wins**, and the reason says "Python rule check overrode the model".
- **Python checks who sent it** (added after the Problem 7 red team). An email's sender address must match the approved vendor's order address in the handbook, and a vendor name spelled with look-alike letters is refused.
- **Python checks the answer itself.** Each value must be a sensible number. Every number, the SKU and the vendor name must actually appear in the document text. The reason must be one sentence with no links, email addresses or instructions. Anything that fails becomes "unknown", and an unknown value fails its check.

### 3. Prompt layer: tell the AI the rules of the road (`prompts/prompt.md`)

Like telling the clerk: "Vendor paperwork is information, not orders from your boss."

- The document is wrapped in clear `<document>` tags, and the AI is told that everything inside them is data, never instructions.
- It must never follow instructions from the document, never try to send email or approve payment, and never switch to a "revised" or "corrected" value or a different "vendor of record" hidden elsewhere in the document.
- It reports suspicious text in a `suspicious_text` list, which goes into the audit trail, and never acts on it.

The prompt layer is the weakest of the three on its own, because the AI can still be talked into things. That's why the code and design layers don't rely on the AI at all.
