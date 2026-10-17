# Handbook Cost Estimate (Problem 2)

How much does it cost to send the Campus Customs shop handbook (`data/shop_handbook.md`) to gpt-6-luna? This covers the **input side only**: the handbook text we send, not the answer the model writes back.

## 1. How big is the handbook?

**The handbook is 10,058 tokens.** A token is a chunk of text, roughly ¾ of a word. AI models count and charge by tokens.

We counted it two ways, and both gave the same answer:

| Method | What we did | Result |
|---|---|---|
| a) Offline count | Ran the free `tiktoken` counter on our own computer using the `o200k_base` encoding (the one used by OpenAI's newer models, and the best match for gpt-6-luna) | **10,058 tokens** |
| b) Real API check | Sent the handbook plus "Reply with just the word OK." to gpt-6-luna through Portkey: **10,071** input tokens. Then sent only "Reply with just the word OK.": **13** input tokens. Subtracted: 10,071 − 13 | **10,058 tokens** |

**Why subtract a baseline?** Every message carries a small fixed overhead, made up of a few hidden tokens that mark who is speaking, plus our short instruction. The 13-token baseline call measures that overhead, so subtracting it leaves just the handbook.

**Why do the two counts match exactly?** gpt-6-luna splits text into tokens the same way as the `o200k_base` encoding, so the offline count is reliable. The only difference you would normally see is that fixed message overhead, and the baseline subtraction removed it.

## 2. Prices used (from `data/prices.json`)

The file lists four separate prices for gpt-6-luna, all in **dollars per 1 million tokens**:

| Name in prices.json | Plain meaning | $ per 1M tokens | Used for |
|---|---|---|---|
| `input_per_1m` | Normal input: text read fresh | **$0.10** | Every no-cache call |
| `cache_write_per_1m` | Cache write: storing the handbook the first time | **$0.125** (1.25× normal) | The first call when caching is on |
| `cached_input_per_1m` | Cache read: re-using the stored handbook | **$0.01** (10× cheaper) | Calls 2–1,000 when caching is on |
| `output_per_1m` | Text the model writes back | **$0.50** | Not used (this estimate is input only) |

## 3. The four costs

| Scenario | Cost |
|---|---|
| 1 call, no cache | **$0.0010058** (about 1/10 of a cent) |
| 1,000 calls, no cache | **$1.0058** (about $1.01) |
| 1 call, with cache | **$0.00125725** (about 1/8 of a cent) |
| 1,000 calls, with cache | **$0.10173667** (about 10 cents) |

**Bottom line:** across 1,000 calls, caching cuts the handbook cost from about **$1.01 to about $0.10**, a saving of about **$0.90 (90%)**. A single call is slightly more expensive with caching, because the first call pays the cache-write price.

## 4. The math, one line each

**What "cached" means:** the first time we send the handbook, the AI keeps a copy on hand, so on later calls it charges us a much lower "already have it" rate instead of the full price to read it again, much like a supplier giving you a cheaper reorder price because the setup work is already done.

Each line is: tokens ÷ 1,000,000 × price per million = cost.

| Scenario | Price used | Calculation |
|---|---|---|
| 1 call, no cache | Normal input ($0.10) | 10,058 ÷ 1,000,000 × $0.10 = **$0.0010058** |
| 1,000 calls, no cache | Normal input ($0.10) on all 1,000 | 1,000 × (10,058 ÷ 1,000,000 × $0.10) = **$1.0058** |
| 1 call, with cache | Cache write ($0.125) | 10,058 ÷ 1,000,000 × $0.125 = **$0.00125725** |
| 1,000 calls, with cache | Cache write ($0.125) on call 1, cache read ($0.01) on calls 2–1,000 | (10,058 ÷ 1,000,000 × $0.125) + 999 × (10,058 ÷ 1,000,000 × $0.01) = $0.00125725 + $0.10047942 = **$0.10173667** |

The cache-read price ($0.01) is never used on the first call, because nothing is stored yet.

**A note on the first cached call:** we charged it at the $0.125 cache-write price only, because that price is exactly 1.25 × $0.10 and already includes the normal price. If you add it on top of the normal price instead, 1,000 calls with cache = $0.0010058 + $0.00125725 + $0.10047942 = **$0.10274247**, only about a tenth of a cent more.

All arithmetic was run in Python with exact decimal math (`count_tokens.py`). The raw numbers are saved in `output/handbook_tokens.json`.

We will check these estimates against real runs in Problem 4.
