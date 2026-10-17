"""CODE defense layer: clean a vendor document BEFORE any model sees it.

Keeps only what a person would actually see, and reports everything it
removed or flagged so it can go into output/audit_trail.json.

    text, report = sanitize_document(Path("data/practice_docs/p02_elmcity_quote.html"))
"""

import email
import re
import unicodedata
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup, Comment


@dataclass
class Report:
    removed: list[dict] = field(default_factory=list)   # {"what", "where", "text"}
    flags: list[dict] = field(default_factory=list)     # {"what", "text"}

    def remove(self, what: str, where: str, text: str) -> None:
        text = " ".join(INVISIBLE.sub("", text).split())
        if text:
            self.removed.append({"what": what, "where": where, "text": text[:300]})

    def flag(self, what: str, text: str) -> None:
        entry = {"what": what, "text": " ".join(text.split())[:300]}
        if entry not in self.flags:
            self.flags.append(entry)

    def as_dict(self) -> dict:
        return {"removed": self.removed, "flags": self.flags}


# ---------------------------------------------------------------- everything

# Zero-width spaces/joiners, direction controls, soft hyphen, word joiner, BOM, etc.
INVISIBLE = re.compile("[­͏؜ᅟᅠ឴឵᠎​-‏"
                       "‪-‮⁠-⁯ㅤ﻿ﾠ]")

# Common look-alike letters (Cyrillic / Greek) that pass for Latin ones.
CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o", "ν": "v",
})

LINK = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>\"')\]]+")

SUSPICIOUS = [
    ("asks the reader to ignore instructions",
     re.compile(r"(?i)\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(instruction|rule|prompt|guideline)s?\b")),
    ("tries to change the AI's role", re.compile(r"(?i)\byou are now\b|\bact as\b|\bnew instructions\b")),
    ("mentions system prompt", re.compile(r"(?i)\bsystem (prompt|message)\b")),
    ("asks to send an email", re.compile(r"(?i)\bsend(_email| an? email| (the|this|our) [^.]{0,40}\bto\b[^.]*@)")),
    ("asks to approve a payment",
     re.compile(r"(?i)\bapprove_payment\b|\bapprove (the |a )?(\d+ percent )?(payment|deposit|invoice)")),
    ("claims to replace facts stated elsewhere",
     re.compile(r"(?i)\b(this|it) replaces the\b|\breplaces the (unit )?(price|lead time|quote)")),
    ("asks to insert a link", re.compile(r"(?i)\b(put|add|include) (this|the) [^.]{0,30}\blink\b")),
    ("claims a standing instruction from Campus Customs", re.compile(r"(?i)\bstanding instruction\b")),
    ("asks to share confidential data", re.compile(r"(?i)\bmax unit cost list\b|\bmargins?\b[^.]{0,30}\bsend\b")),
]


def flag_suspicious(text: str, report: Report, prefix: str = "suspicious phrase") -> None:
    for label, pattern in SUSPICIOUS:
        for m in pattern.finditer(text):
            # Flag the whole sentence around the match so a person can review it.
            start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
            end_dot = text.find(".", m.end())
            end = len(text) if end_dot == -1 else end_dot + 1
            report.flag(f"{prefix}: {label}", text[start:end])


def clean_text(text: str, report: Report, where: str) -> str:
    """Steps applied to every document type after its own extraction."""
    hidden_chars = len(INVISIBLE.findall(text))
    if hidden_chars:
        report.remove(f"{hidden_chars} invisible Unicode characters", where, "zero-width / control characters")
    text = INVISIBLE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    # Record each disguised word (in its normal spelling) so the design layer can
    # refuse a vendor name that was faked with look-alike letters.
    disguised = sorted({w.translate(CONFUSABLES) for w in re.findall(r"\w+", text)
                        if any(ord(ch) > 127 and ch.translate(CONFUSABLES) != ch for ch in w)})
    if disguised:
        report.flag("look-alike letters normalized", ", ".join(disguised))
    text = text.translate(CONFUSABLES)
    for link in LINK.findall(text):
        report.remove("link", where, link)
    text = LINK.sub("[link removed]", text)
    flag_suspicious(text, report)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


# --------------------------------------------------------------------- HTML

def parse_style(style: str) -> dict:
    decls = {}
    for part in style.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            decls[key.strip().lower()] = value.strip().lower()
    return decls


def parse_color(value: str):
    """Return (r, g, b) 0-255 for simple CSS colors, else None."""
    value = value.strip().lower().replace("!important", "").strip()
    named = {"white": (255, 255, 255), "black": (0, 0, 0), "transparent": None}
    if value in named:
        return named[value]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", value)
    if m:
        if m.group(4) is not None and float(m.group(4)) < 0.1:
            return None
        return tuple(int(m.group(i)) for i in (1, 2, 3))
    return None


def css_length_px(value: str):
    m = re.match(r"(-?[\d.]+)\s*(px|pt|em|rem|%)?", value.strip())
    if not m:
        return None
    number, unit = float(m.group(1)), (m.group(2) or "px")
    return {"px": number, "pt": number * 4 / 3, "em": number * 16, "rem": number * 16, "%": number * 0.16}[unit]


def background_of(tag, css_rules: dict) -> tuple:
    """Nearest background color set on the tag or its ancestors (default page white)."""
    node = tag
    while node is not None and getattr(node, "name", None):
        decls = {**css_rules.get(id(node), {}), **parse_style(node.get("style", ""))}
        for key in ("background-color", "background"):
            if key in decls:
                color = parse_color(decls[key].split()[0])
                if color is not None:
                    return color
        node = node.parent
    return (255, 255, 255)


def hidden_reason(tag, decls: dict, css_rules: dict):
    """Why a person can't see this element, or None if it's visible."""
    if tag.has_attr("hidden"):
        return "hidden attribute"
    if tag.get("aria-hidden", "").lower() == "true":
        return "aria-hidden attribute"
    if tag.name == "input" and tag.get("type", "").lower() == "hidden":
        return "hidden form field"
    if decls.get("display", "").startswith("none"):
        return "display:none"
    if decls.get("visibility", "") in ("hidden", "collapse"):
        return "visibility:hidden"
    try:
        if "opacity" in decls and float(decls["opacity"]) <= 0.05:
            return "opacity:0"
    except ValueError:
        pass
    if "font-size" in decls:
        size = css_length_px(decls["font-size"])
        if size is not None and size < 4:
            return f"tiny font ({decls['font-size']})"
    for key in ("left", "top", "text-indent", "margin-left", "margin-top"):
        if key in decls:
            offset = css_length_px(decls[key])
            if offset is not None and offset <= -500:
                return f"off-screen ({key}:{decls[key]})"
    if "clip" in decls and "rect(0" in decls["clip"].replace(" ", ""):
        return "clipped to nothing"
    if "clip-path" in decls and "inset(50%" in decls["clip-path"].replace(" ", ""):
        return "clipped to nothing"
    if "transform" in decls and re.search(r"scale\(\s*0(\.0*)?\s*[,)]", decls["transform"]):
        return "scaled to nothing"
    for key in ("width", "height", "max-height", "max-width"):
        if key in decls and css_length_px(decls[key]) == 0 and "hidden" in decls.get("overflow", ""):
            return f"zero size ({key}:0, overflow hidden)"
    if "color" in decls:
        color = parse_color(decls["color"])
        if color is not None:
            bg = background_of(tag, css_rules)
            if sum(abs(a - b) for a, b in zip(color, bg)) < 60:
                return f"text same color as background ({decls['color']})"
    return None


def stylesheet_rules(soup: BeautifulSoup) -> dict:
    """Map element id() -> declarations from <style> blocks (simple selectors only)."""
    rules: dict = {}
    for style in soup.find_all("style"):
        css = re.sub(r"/\*.*?\*/", "", style.get_text(), flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            decls = parse_style(body)
            for selector in selectors.split(","):
                try:
                    for el in soup.select(selector.strip()):
                        rules.setdefault(id(el), {}).update(decls)
                except Exception:
                    continue
    return rules


def html_visible_text(raw: str, report: Report, where: str = "HTML") -> str:
    soup = BeautifulSoup(raw, "html.parser")
    css_rules = stylesheet_rules(soup)

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        report.remove("HTML comment", where, str(comment))
        comment.extract()
    for tag in soup.find_all(["script", "noscript", "template", "iframe", "object", "embed"]):
        report.remove(f"<{tag.name}> block", where, tag.get_text())
        tag.decompose()

    for tag in list(soup.find_all(True)):
        if tag.decomposed if hasattr(tag, "decomposed") else tag.parent is None:
            continue
        if tag.name in ("html", "head", "body", "style", "meta", "link", "title"):
            continue
        decls = {**css_rules.get(id(tag), {}), **parse_style(tag.get("style", ""))}
        reason = hidden_reason(tag, decls, css_rules)
        if reason:
            report.remove(f"hidden text ({reason})", where, tag.get_text(" "))
            tag.decompose()

    for tag in soup.find_all(["style", "meta", "link", "head"]):
        tag.decompose()
    return soup.get_text("\n")


# ---------------------------------------------------------------------- PDF

MIN_PDF_FONT = 4.0  # points; normal body text is 9-12


def pdf_color_is_white(color) -> bool:
    if color is None:
        return False
    values = color if isinstance(color, (list, tuple)) else (color,)
    try:
        values = [float(v) for v in values]
    except (TypeError, ValueError):
        return False
    if len(values) == 4:  # CMYK: white is no ink
        return all(v <= 0.05 for v in values)
    return all(v >= 0.95 for v in values)


def pdf_visible_text(path: Path, report: Report) -> str:
    pages = []
    with pdfplumber.open(path) as pdf:
        if pdf.metadata:
            report.remove("PDF metadata (not read)", "PDF", ", ".join(f"{k}={v}" for k, v in pdf.metadata.items()))
        for number, page in enumerate(pdf.pages, start=1):
            where = f"PDF page {number}"
            hidden: dict[str, list[str]] = {}

            def why_hidden(ch) -> str | None:
                if ch["size"] < MIN_PDF_FONT:
                    return f"tiny text ({ch['size']:.1f}pt)"
                if pdf_color_is_white(ch.get("non_stroking_color")):
                    return "white text"
                if ch["x1"] < 0 or ch["x0"] > page.width or ch["bottom"] < 0 or ch["top"] > page.height:
                    return "text outside the page"
                return None

            def keep(obj) -> bool:
                if obj.get("object_type") != "char":
                    return True
                reason = why_hidden(obj)
                if reason:
                    hidden.setdefault(reason, []).append(obj["text"])
                    return False
                return True

            text = page.filter(keep).extract_text() or ""
            for reason, chars in hidden.items():
                report.remove(f"hidden text ({reason})", where, "".join(chars))
            if page.annots:
                report.remove("PDF annotations (not read)", where, f"{len(page.annots)} annotation(s)")
            pages.append(text)
    return "\n".join(pages)


# -------------------------------------------------------------------- Email

HEADERS_KEPT = ("From", "To", "Subject", "Date")
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return {n.replace("$", "").replace(",", "") for n in NUMBER.findall(text)}


def eml_visible_text(path: Path, report: Report) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    dropped = [k for k in msg.keys() if k not in HEADERS_KEPT and not k.lower().startswith(("content-", "mime-"))]
    if dropped:
        report.remove("email headers ignored", "email headers", ", ".join(dropped))
    headers = [f"{h}: {msg[h]}" for h in HEADERS_KEPT if msg[h]]

    plain = html = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_filename() or part.get_content_disposition() == "attachment":
            report.remove("email attachment ignored", "email attachment", part.get_filename() or "unnamed")
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain is None:
            plain = part.get_content()
        elif ctype == "text/html" and html is None:
            html = part.get_content()

    # An email app shows the HTML part when there is one, so that is what a person reads.
    if html is not None:
        html_report = Report()
        visible_html = html_visible_text(html, html_report, where="email HTML part")
        report.removed.extend(html_report.removed)
        body = visible_html
        if plain is not None:
            raw_html_text = BeautifulSoup(html, "html.parser").get_text(" ")
            if numbers_in(INVISIBLE.sub("", raw_html_text)) != numbers_in(plain):
                report.flag("plain-text and HTML parts disagree",
                            f"plain has {sorted(numbers_in(plain))}; HTML has "
                            f"{sorted(numbers_in(INVISIBLE.sub('', raw_html_text)))}")
            if numbers_in(visible_html) != numbers_in(plain):
                report.flag("visible HTML and plain-text parts disagree",
                            f"plain has {sorted(numbers_in(plain))}; visible HTML has {sorted(numbers_in(visible_html))}")
    else:
        body = plain or ""
    return "\n".join(headers) + "\n\n" + body


# -------------------------------------------------------------------- Entry

def sanitize_document(path: Path) -> tuple[str, dict]:
    """Return (text a person would see, report of what was removed or flagged)."""
    path = Path(path)
    report = Report()
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        text = html_visible_text(path.read_text(encoding="utf-8"), report)
    elif suffix == ".pdf":
        text = pdf_visible_text(path, report)
    elif suffix == ".eml":
        text = eml_visible_text(path, report)
    else:
        text = path.read_text(encoding="utf-8")
    text = clean_text(text, report, where=suffix.lstrip(".").upper() or "text")
    # Also flag attacks inside the hidden text we removed, so the audit trail shows intent.
    for item in list(report.removed):
        if item["what"].startswith(("hidden text", "HTML comment")):
            flag_suspicious(unicodedata.normalize("NFKC", item["text"]), report,
                            prefix="in removed hidden text")
    return text, report.as_dict()
