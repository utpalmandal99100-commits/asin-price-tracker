"""Cross-platform product matching by brand, name, SKU/EAN and variant.

The score is deliberately conservative: a different pack size, shade or
clothing size is a different product, so a variant conflict caps the score
below the confirmation threshold no matter how similar the names are.
"""

import re

HIGH = 85
MEDIUM = 65

STOPWORDS = {
    "the", "a", "an", "and", "for", "with", "of", "in", "by", "to", "on",
    "men", "mens", "women", "womens", "unisex", "pack", "new", "buy", "online",
    "india", "original", "combo", "set", "free",
}

UNIT_ALIASES = {
    "ml": "ml", "millilitre": "ml", "milliliter": "ml",
    "l": "l", "ltr": "l", "litre": "l", "liter": "l",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "kg": "kg", "mg": "mg", "oz": "oz",
}
TO_BASE = {"l": ("ml", 1000), "kg": ("g", 1000), "mg": ("g", 0.001)}

QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|millilitre|milliliter|ltr|litre|liter|l|gms|gm|grams|gram|g|kg|mg|oz)\b", re.I)
COUNT_RE = re.compile(r"\b(?:pack|set)\s+of\s+(\d+)\b|\b(\d+)\s*(?:pcs|pieces|pc|count|n)\b", re.I)
SIZE_RE = re.compile(r"\b(?:size|uk|us|eu)\s*[:\-]?\s*(\d{1,2}(?:\.\d)?|xxs|xs|s|m|l|xl|xxl|xxxl|[2-5]xl)\b", re.I)

COLOURS = {
    "black", "white", "blue", "navy", "red", "green", "olive", "grey", "gray",
    "brown", "beige", "pink", "purple", "yellow", "orange", "maroon", "cream",
    "gold", "silver", "khaki", "tan", "teal", "peach", "nude", "lavender",
}


def normalise(text):
    text = (text or "").lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9.]+", " ", text).strip()


def tokens(text):
    return {t for t in normalise(text).split() if t not in STOPWORDS and len(t) > 1}


def extract_variant(*texts):
    """Pull pack size, count, clothing/shoe size and colour from free text."""
    text = " ".join(t for t in texts if t)
    out = {}
    q = QTY_RE.search(text)
    if q:
        amount, unit = float(q.group(1)), UNIT_ALIASES[q.group(2).lower()]
        if unit in TO_BASE:
            unit, factor = TO_BASE[unit]
            amount *= factor
        out["quantity"] = (round(amount, 2), unit)
    c = COUNT_RE.search(text)
    if c:
        out["count"] = int(c.group(1) or c.group(2))
    s = SIZE_RE.search(text)
    if s:
        out["size"] = s.group(1).upper()
    colours = tokens(text) & COLOURS
    if colours:
        out["colours"] = {"grey" if x == "gray" else x for x in colours}
    return out


def _variant_conflicts(a, b):
    conflicts = []
    for key in ("quantity", "count", "size"):
        if key in a and key in b and a[key] != b[key]:
            conflicts.append(key)
    if "colours" in a and "colours" in b and not (a["colours"] & b["colours"]):
        conflicts.append("colour")
    return conflicts


def _clean_codes(values):
    return {re.sub(r"[^0-9A-Z]", "", str(v).upper()) for v in (values or []) if v} - {""}


def score(source, candidate):
    """Score how likely `candidate` is the same product as `source`.

    Each side is a dict with optional keys: title, brand, variant (text),
    eans (list), model (str). Returns {score, confidence, reasons}.
    """
    reasons = []
    src_codes = _clean_codes(source.get("eans")) | _clean_codes([source.get("model")])
    cand_codes = _clean_codes(candidate.get("eans")) | _clean_codes([candidate.get("model")])
    shared_codes = src_codes & cand_codes

    src_var = extract_variant(source.get("title"), source.get("variant"))
    cand_var = extract_variant(candidate.get("title"), candidate.get("variant"))
    conflicts = _variant_conflicts(src_var, cand_var)

    if shared_codes and not conflicts:
        return {"score": 100, "confidence": "high", "reasons": [f"Same EAN/model code ({sorted(shared_codes)[0]})"]}

    points = 0.0
    sb, cb = normalise(source.get("brand")), normalise(candidate.get("brand"))
    if sb and cb:
        if sb == cb or sb in cb or cb in sb:
            points += 30
            reasons.append("Same brand")
        else:
            reasons.append(f"Different brand ({source.get('brand')} vs {candidate.get('brand')})")
            return {"score": 0, "confidence": "low", "reasons": reasons}
    elif sb and sb in normalise(candidate.get("title")):
        points += 25
        reasons.append("Brand found in title")

    brand_tokens = tokens(source.get("brand")) | tokens(candidate.get("brand"))
    st = tokens(source.get("title")) - brand_tokens
    ct = tokens(candidate.get("title")) - brand_tokens
    if st and ct:
        overlap = len(st & ct) / len(st | ct)
        containment = len(st & ct) / min(len(st), len(ct))
        name_sim = 0.5 * overlap + 0.5 * containment
        points += 45 * name_sim
        reasons.append(f"Name similarity {round(name_sim * 100)}%")

    shared_variant = [k for k in ("quantity", "count", "size") if k in src_var and src_var.get(k) == cand_var.get(k)]
    if shared_variant:
        points += 25
        reasons.append("Same " + ", ".join(shared_variant))
    elif not src_var and not cand_var:
        points += 10

    if conflicts:
        reasons.append("Variant differs: " + ", ".join(conflicts))
        points = min(points, MEDIUM - 15)

    final = round(min(points, 99))
    confidence = "high" if final >= HIGH else "medium" if final >= MEDIUM else "low"
    return {"score": final, "confidence": confidence, "reasons": reasons}


def search_query(brand, title, variant=None):
    """A short search phrase for the other platforms' search pages."""
    words = []
    for part in (brand, title):
        for w in (part or "").split():
            if w.lower() not in {x.lower() for x in words}:
                words.append(w)
    q = " ".join(words[:12])
    if variant and variant.lower() not in q.lower():
        q += " " + variant
    return q.strip()
