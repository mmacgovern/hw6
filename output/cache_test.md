# With and Without Cached Tokens (Problem 4)

We ran the vendor desk agent on all 12 practice documents twice:

- **With cache:** every call starts with the same handbook and instructions, and the document comes after, so the model provider can reuse ("cache") the handbook part.
- **Without cache:** we ran `agent.py --no-cache`, which puts a random line ("Request ID: ...") at the very start of every call, before the handbook, so nothing can ever be reused.

Each document took **2 model calls**: one where the agent asks to read the document, and one where it gives its answer. That makes **48 calls** in total, and every one is saved in `output/cache_test.json`. All costs use `data/prices.json` (per 1 million tokens): normal input $0.10, cache write $0.125, cached input (cache read) $0.01, output $0.50.

## Did each setup really work? (proof from the API's own token counts)

| Check | Result |
|---|---|
| Without cache: every call shows 0 cached tokens | **PASS**: all 24 calls show 0 |
| With cache: calls after the first reuse close to the handbook's 10,058 tokens | **PASS**: all 23 later calls reused 10,944 to 11,321 tokens |
| With cache: the first call | It was **already cached** (10,966 tokens), because we had run the same handbook a few minutes earlier while testing. On a truly fresh start it would show 0. That is expected. |
| Portkey's own response cache is off | **PASS**: every call was sent with `x-portkey-cache-force-refresh: true`, and Portkey reported `REFRESH` (a real model call) on all 48 calls, with 0 replayed answers |

Both checks passed on the first full run, so nothing needed fixing. One thing we checked on purpose: the random line in no-cache mode is regenerated before **every** call, not just once per document. Otherwise the agent's second call could reuse its first call. The 0s on the second calls confirm it worked.

## 1. Cost results

| Setup | Total, 12 documents | Cost per document |
|---|---|---|
| Without cache | **$0.0347869** | **$0.00289891** |
| With cache | **$0.0045815** | **$0.00038179** |
| **Saved** | **$0.0302054** | **$0.00251712** |

**Percent saved = 1 − ($0.0045815 ÷ $0.0347869) = 86.8%**

Where the money went (all 24 calls in each setup):

| Part of the bill | Without cache | With cache |
|---|---|---|
| Normal input | 3,024 tokens × $0.10 ÷ 1M = $0.0003024 | 3,024 tokens × $0.10 ÷ 1M = $0.0003024 |
| Cache write | 266,716 tokens × $0.125 ÷ 1M = $0.0333395 | 2,210 tokens × $0.125 ÷ 1M = $0.0002763 |
| Cache read | 0 tokens = $0.00 | 263,835 tokens × $0.01 ÷ 1M = $0.0026384 |
| Output | 2,290 tokens × $0.50 ÷ 1M = $0.0011450 | 2,729 tokens × $0.50 ÷ 1M = $0.0013645 |
| **Total** | **$0.0347869** | **$0.0045815** |

## 2. How this compares with our Problem 2 estimate

| | Problem 2 estimate (handbook only, 1 call) | Real, per document (2 calls) |
|---|---|---|
| Without cache | 10,058 × $0.10 ÷ 1M = **$0.0010058** | **$0.0028989** (about 2.9× the estimate) |
| With cache | 10,058 × $0.01 ÷ 1M = **$0.0001006** per cached call | **$0.0003818** (about 3.8× the estimate) |

Why the real numbers are higher:

- **Two calls per document, not one.** The handbook is sent on both calls, so it is paid for twice.
- **More than the handbook goes in.** Each call is about 11,200 input tokens, not 10,058. The extra comes from our instructions (`prompts/prompt.md`), the descriptions of the three tools, the request line, and, on the second call, the document text itself.
- **The answer costs money too.** Problem 2 counted input only. Output tokens are 5 times the normal input price ($0.50 vs $0.10).
- **"Without cache" was billed at the cache-write price.** The API stored nearly every token of every no-cache call: 266,716 of 269,740 input tokens were reported as cache writes. It just never got to reuse them, because each call started with a different random line. So most no-cache tokens cost $0.125, not the $0.10 normal price that Problem 2 assumed.

The percent saved holds up. Problem 2 predicted a 90% saving on the handbook at scale, and on the input side alone we saved **1 − ($0.003217 ÷ $0.0336419) = 90.4%**.

## 3. Projection: 1,000 documents a day for 30 days

30 days × 1,000 documents = **30,000 documents**

| Setup | Math | Monthly cost |
|---|---|---|
| Without cache | 30,000 × $0.00289891 | **$86.97** |
| With cache | 30,000 × $0.00038179 | **$11.45** |
| **Saved per month** | $86.97 − $11.45 | **$75.51** (86.8%) |

## 4. What surprised us, and why

1. **Not caching cost more than the normal price.** The provider automatically tries to store every prompt, and `prices.json` charges $0.125 per million tokens for storing. When every call is unique, we pay that storage fee every time and never get the $0.01 reuse price. If no-cache calls had been billed at the plain $0.10 instead, the without-cache total would have been 269,740 × $0.10 ÷ 1M + $0.001145 = **$0.028119**, and the saving would be 83.7% instead of 86.8%.
2. **The first "with cache" call was already cached.** The provider kept the handbook from our test runs a few minutes earlier. In a cold start (for example, the first document of the morning), call 1 would pay full price.
3. **Not everything gets cached.** The first call of each document reused about 10,944 of its roughly 11,094 input tokens. The last ~150 tokens (the "review this document" line, which changes per document) are always new. Only the identical opening part can be reused.
4. **Cached amounts come in steps, not a smooth amount.** Almost every call reused exactly 10,944 or about 10,967 tokens. That is the shared opening (handbook, instructions and tools). The fact that the amounts repeat so exactly suggests the provider stores prompts in fixed-size blocks, but this data can't tell us the exact block size. Three documents (p01, p04, p08) reused more on their second call (11,120 to 11,321) because we had run those exact documents earlier, so even the document text was already stored.
5. **Agent runs make several calls.** Each document needed 2 calls, which doubles the handbook cost compared with a one-call estimate.
6. **Output tokens get no discount, so the total saving is smaller than the cache discount.** Cached input is 90% cheaper, but output is full price either way. With cache, output was **$0.0013645 ÷ $0.0045815 = 29.8%** of the whole bill, which is why total savings (86.8%) are below input savings (90.4%).
7. **Output varies from run to run.** The with-cache run used 2,729 output tokens and the without-cache run used 2,290, on the same documents. The model "thinks" a different amount each time. For example, p09 (an email with hidden text) used 851 thinking tokens on its answer in one run. This has nothing to do with caching.
8. **Caching didn't change any answers.** Both setups matched the answer key on the same 8 of 12 documents. The 4 misses (p02, p03, p07, p12) are documents that contain "revised price", "corrected lead time" or "vendor of record" text, which this undefended agent believes. That is the subject of Problems 5 and 6. No trap tools were called in either setup.

*Raw data: `output/cache_test.json` (all 48 calls). Script: `cache_test.py`.*
