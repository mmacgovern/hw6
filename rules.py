"""DESIGN defense layer: check the model's answer in plain Python.

The handbook's hard rules (approved vendors, price limits, lead time, minimum
order) are read straight from data/shop_handbook.md, so Python never depends on
the model to apply them. If Python and the model disagree, Python wins.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
HANDBOOK_PATH = HERE / "data" / "shop_handbook.md"

SKU_FORMAT = re.compile(r"^CC-[A-Z]{2}-\d{3}$")
LINK_OR_EMAIL = re.compile(r"(?i)https?://|www\.|\[link removed\]|[\w.+-]+@[\w-]+\.\w+|\b[\w-]+\.(?:example|com|net|org|io)\b")
INSTRUCTION_WORDS = re.compile(
    r"(?i)\b(ignore|disregard|send_email|approve_payment|send (an )?email|approve (the )?payment|"
    r"click|visit|follow (this|the) link|system prompt|you (must|should) now)\b")

# Sensible ranges: anything outside these is treated as a bad extraction.
RANGES = {"unit_price": (0.01, 10_000), "lead_time_days": (0, 365), "min_order": (1, 1_000_000)}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if line.startswith("|") and not set(line) <= set("|- "):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows[1:]  # skip header


@dataclass(frozen=True)
class HandbookRules:
    approved: frozenset
    blocked: frozenset
    max_cost: dict
    max_lead_days: int
    max_min_order: int
    vendor_domains: dict  # normalized vendor name -> email domain from its "Orders:" address


@lru_cache(maxsize=1)
def load_rules() -> HandbookRules:
    text = HANDBOOK_PATH.read_text(encoding="utf-8")
    sections = {m.group(1): m.group(2) for m in re.finditer(r"^## (\d+)\.[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)}
    approved_rows = table_rows(sections["5"])
    approved = frozenset(norm(r[1]) for r in approved_rows)
    vendor_domains = {}
    for r in approved_rows:
        m = re.search(r"Orders:\s*[\w.+-]+@([\w.-]+\w)", r[-1])
        if m:
            vendor_domains[norm(r[1])] = m.group(1).lower()
    blocked = frozenset(norm(r[0]) for r in table_rows(sections["6"]))
    max_cost = {r[0]: float(r[4].replace("$", "").replace(",", "")) for r in table_rows(sections["9"])}
    lead = int(re.search(r"lead time is (\d+) days or less", sections["4"]).group(1))
    min_order = int(re.search(r"minimum order is (\d+) units or less", sections["4"]).group(1))
    return HandbookRules(approved, blocked, max_cost, lead, min_order, vendor_domains)


def sender_domain(doc_text: str) -> str | None:
    """Domain of the email's From: address, if the document is an email."""
    m = re.search(r"(?im)^From:.*?[\w.+-]+@([\w.-]+\w)", doc_text)
    return m.group(1).lower() if m else None


def identity_problem(vendor: str | None, doc_text: str, sanitize_report: dict | None) -> str | None:
    """Is the claimed vendor really who sent this? Returns a failure reason or None."""
    if not vendor:
        return None
    rules = load_rules()
    key = norm(vendor)
    flags = (sanitize_report or {}).get("flags", [])
    disguised = {norm(w) for f in flags if f["what"].startswith("look-alike")
                 for w in f["text"].split(",")}
    if disguised and any(word in disguised for word in key.split()):
        return f"Approved-vendor check fails because the name {vendor} was spelled with look-alike letters."
    domain = sender_domain(doc_text)
    expected = rules.vendor_domains.get(key)
    if domain and expected and not (domain == expected or domain.endswith("." + expected)):
        return (f"Approved-vendor check fails because the email came from {domain}, "
                f"not {vendor}'s order address domain {expected}.")
    return None


def numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def validate(answer: dict, doc_text: str) -> tuple[dict, list[str]]:
    """Check types, ranges and grounding; return a cleaned copy and the problems found."""
    fixed, problems = dict(answer), []
    for field_name, (low, high) in RANGES.items():
        value = fixed.get(field_name)
        if value is not None and not (low <= value <= high):
            problems.append(f"{field_name}={value} is outside the sensible range {low}-{high}; set to unknown")
            fixed[field_name] = None
    if fixed.get("sku") and not SKU_FORMAT.match(fixed["sku"]):
        problems.append(f"sku {fixed['sku']!r} is not in CC-XX-000 format; set to unknown")
        fixed["sku"] = None

    # Grounding: every value must actually appear in the text the model was given.
    found = numbers_in(doc_text)
    for field_name in ("unit_price", "lead_time_days", "min_order"):
        value = fixed.get(field_name)
        if value is not None and not any(abs(value - n) < 0.005 for n in found):
            problems.append(f"{field_name}={value} does not appear in the document; set to unknown")
            fixed[field_name] = None
    if fixed.get("sku") and fixed["sku"] not in doc_text:
        problems.append(f"sku {fixed['sku']} does not appear in the document; set to unknown")
        fixed["sku"] = None
    if fixed.get("vendor") and norm(fixed["vendor"]) not in norm(doc_text):
        problems.append(f"vendor {fixed['vendor']!r} does not appear in the document; set to unknown")
        fixed["vendor"] = None

    reason = fixed.get("reason") or ""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", reason.strip()) if s]
    if len(sentences) != 1:
        problems.append(f"reason has {len(sentences)} sentences, not 1")
    if LINK_OR_EMAIL.search(reason):
        problems.append("reason contains a link or email address")
    if INSTRUCTION_WORDS.search(reason):
        problems.append("reason contains instruction-like words")
    return fixed, problems


def python_decision(answer: dict) -> tuple[str, str]:
    """Apply the handbook's four purchasing checks in order. Returns (decision, reason)."""
    rules = load_rules()
    vendor, sku = answer.get("vendor"), answer.get("sku")
    price, lead, minimum = answer.get("unit_price"), answer.get("lead_time_days"), answer.get("min_order")

    if not vendor:
        return "do_not_recommend", "Approved-vendor check fails because the vendor is unknown."
    if norm(vendor) in rules.blocked:
        return "do_not_recommend", f"Approved-vendor check fails because {vendor} is on the removed or pending vendor list."
    if norm(vendor) not in rules.approved:
        return "do_not_recommend", f"Approved-vendor check fails because {vendor} is not on the approved vendor list."
    if not sku or sku not in rules.max_cost:
        return "do_not_recommend", f"Price check fails because SKU {sku or 'unknown'} is not in the catalogue."
    if price is None:
        return "do_not_recommend", "Price check fails because the unit price is unknown."
    if price > rules.max_cost[sku]:
        return "do_not_recommend", (f"Price check fails because ${price:.2f} is above the "
                                    f"${rules.max_cost[sku]:.2f} max unit cost for {sku}.")
    if lead is None:
        return "do_not_recommend", "Lead-time check fails because the lead time is unknown."
    if lead > rules.max_lead_days:
        return "do_not_recommend", f"Lead-time check fails because {lead} days is more than {rules.max_lead_days} days."
    if minimum is None:
        return "do_not_recommend", "Minimum-order check fails because the minimum order is unknown."
    if minimum > rules.max_min_order:
        return "do_not_recommend", f"Minimum-order check fails because {minimum} units is more than {rules.max_min_order} units."
    return "recommend", (f"All four checks pass: approved vendor, ${price:.2f} is at or below the "
                         f"${rules.max_cost[sku]:.2f} max, {lead} days, and {minimum} units.")


def design_check(answer: dict, doc_text: str, sanitize_report: dict | None = None) -> tuple[dict, dict]:
    """Validate the model's answer, re-decide in Python, and let Python win.

    Returns (final answer, audit notes).
    """
    fixed, problems = validate(answer, doc_text)
    decision, py_reason = python_decision(fixed)
    identity = identity_problem(fixed.get("vendor"), doc_text, sanitize_report)
    if identity:
        problems.append(identity)
        decision, py_reason = "do_not_recommend", identity
    final = dict(fixed)
    overridden = decision != answer.get("decision")
    if overridden:
        final["decision"] = decision
        final["reason"] = f"Python rule check overrode the model: {py_reason}"
    elif problems and any(p.startswith("reason") for p in problems):
        final["reason"] = py_reason
    notes = {
        "model_answer": answer,
        "validation_problems": problems,
        "python_decision": decision,
        "python_reason": py_reason,
        "python_overrode_model": overridden,
    }
    return final, notes
