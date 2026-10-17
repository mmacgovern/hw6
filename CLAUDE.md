# HW6 Project Rules — Campus Customs Vendor Desk Agent

These rules are permanent for everything inside the `hw6` folder.

## What we are building
A "vendor desk agent" for the shop Campus Customs. It reads a vendor document (quote, invoice, catalog page, email), pulls out vendor, SKU, unit price, lead time in days and minimum order, and recommends buying or not, based on `data/shop_handbook.md`.

## AI calls and model
- Every AI call in our code goes through Portkey (OpenAI-compatible, `https://api.portkey.ai/v1`), using `PORTKEY_API_KEY` loaded from `.env` when the code runs.
- Use ONLY the model `gpt-6-luna`. No other model name may appear anywhere in code, config, tests or runs.

## Secrets
- Never print, show, log or commit the contents of `.env`.
- Never ask the user to paste their key in chat.
- Never put the key in code, logs, JSON, markdown or chat. `.env.example` is fine to read and edit.

## Trap tools
- `send_email` and `approve_payment` are fake "trap" tools. They must never send email or pay anything.
- They only append the call and its arguments to `output/trap_calls.json`.
- Never delete them.

## File names (exact, lowercase)
`agent.py`, `tools.py`, `models.py`, `prompts/prompt.md`, `output/` files, `README.md`, `AI_Prompts.md`, `requirements.txt`, `.gitignore`, `.env.example`.

## Course data
- Course data lives in `data/` (`shop_handbook.md`, `prices.json`, `practice_key.json`, `practice_docs/`, `exam_docs/`). Do not edit these files.
- Our own attack documents go in `data/my_attacks/`.

## PROMPT LOG RULE
Every time the user sends a real prompt (skip one-word replies like "yes" or "continue"):
1. First, append it word for word to `AI_Prompts.md` under the section for the problem we are on, labeled **Prompt** or **Follow-up prompt**.
2. For each follow-up, also add one sentence starting "What was lacking after the first prompt:".
3. Don't log status questions (e.g. "Is it complete?", "How long will it take?").
4. If a problem needed no follow-up, its section says `**Follow-up prompt:** N/A` and `What was lacking after the first prompt: N/A`.
5. Never put API keys in the log.

## How to explain things
- The user is a manager learning vibe coding, not a programmer. Explain results in plain, non-technical language.
- Keep all money math visible (show the numbers and the arithmetic, e.g. tokens × price per 1M ÷ 1,000,000).
