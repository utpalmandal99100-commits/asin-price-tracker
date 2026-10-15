"""Platform detection: turn a URL or bare ID into (platform, platform_id)."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, quote_plus, urlparse

PLATFORMS = {
    "amazon": "Amazon India",
    "myntra": "Myntra",
    "nykaa": "Nykaa",
    "tatacliq": "Tata CLiQ",
}

ID_LABELS = {
    "amazon": "ASIN",
    "myntra": "Style ID",
    "nykaa": "Product ID",
    "tatacliq": "Product ID",
}


class InputError(ValueError):
    """The input could not be understood."""


class AmbiguousInput(InputError):
    """The input matches more than one platform; the user has to choose."""

    def __init__(self, value, candidates):
        self.value = value
        self.candidates = candidates
        names = ", ".join(PLATFORMS[c] for c in candidates)
        super().__init__(f"'{value}' could be an ID on {names}. Choose the platform.")


@dataclass
class ParsedInput:
    platform: str
    platform_id: str
    url: str | None  # the URL the user gave, if any


ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
TATACLIQ_RE = re.compile(r"^MP\d{9,18}$")
DIGITS_RE = re.compile(r"^\d{4,12}$")

AMAZON_PATH_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|product|exec/obidos/ASIN)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
MYNTRA_PATH_RE = re.compile(r"/(\d{5,12})(?:/buy)?/?$")
NYKAA_PATH_RE = re.compile(r"/p/(\d+)/?$")
TATACLIQ_PATH_RE = re.compile(r"/p-(mp\d{9,18})/?$", re.I)


def _host_platform(host):
    host = host.lower()
    if host.endswith("amazon.in"):
        return "amazon"
    if host in ("amzn.in", "amzn.to", "a.co"):
        raise InputError("Short Amazon links can't be expanded without visiting them. Paste the full amazon.in product URL or the ASIN.")
    if host.endswith("myntra.com"):
        return "myntra"
    if host.endswith("nykaa.com") or host.endswith("nykaafashion.com"):
        return "nykaa"
    if host.endswith("tatacliq.com"):
        return "tatacliq"
    if "amazon." in host:
        raise InputError("Only Amazon India (amazon.in) is supported.")
    raise InputError(f"'{host}' is not a supported platform. Use Amazon India, Myntra, Nykaa or Tata CLiQ.")


def _parse_url(text):
    url = text if re.match(r"^https?://", text, re.I) else "https://" + text
    parts = urlparse(url)
    platform = _host_platform(parts.hostname or "")
    path = parts.path
    query = parse_qs(parts.query)

    if platform == "amazon":
        m = AMAZON_PATH_RE.search(path)
        if not m:
            raise InputError("Couldn't find an ASIN in that Amazon URL. Use a product page link (…/dp/ASIN).")
        return ParsedInput("amazon", m.group(1).upper(), url)
    if platform == "myntra":
        m = MYNTRA_PATH_RE.search(path)
        if not m:
            raise InputError("Couldn't find a Style ID in that Myntra URL. Use a product page link (…/<style id>/buy).")
        return ParsedInput("myntra", m.group(1), url)
    if platform == "nykaa":
        m = NYKAA_PATH_RE.search(path)
        pid = m.group(1) if m else (query.get("productId") or [None])[0]
        if not pid:
            raise InputError("Couldn't find a Product ID in that Nykaa URL. Use a product page link (…/p/<id>).")
        return ParsedInput("nykaa", pid, url)
    m = TATACLIQ_PATH_RE.search(path)
    if not m:
        raise InputError("Couldn't find a Product ID in that Tata CLiQ URL. Use a product page link (…/p-mp…).")
    return ParsedInput("tatacliq", m.group(1).upper(), url)


def _id_candidates(value):
    up = value.upper()
    candidates = []
    if TATACLIQ_RE.match(up):
        candidates.append("tatacliq")
    if ASIN_RE.match(up) and not TATACLIQ_RE.match(up):
        # Letters mean a real ASIN; ten digits can also be an ISBN-10 ASIN.
        candidates.append("amazon")
    if DIGITS_RE.match(value):
        candidates += ["myntra", "nykaa"]
    return candidates


def normalise_id(platform, value):
    value = value.strip()
    return value.upper() if platform in ("amazon", "tatacliq") else value


def parse_input(text, platform_hint=None):
    """Return ParsedInput for a URL or ID. Raises InputError / AmbiguousInput."""
    text = (text or "").strip()
    if not text:
        raise InputError("Enter a product URL or ID.")
    if platform_hint and platform_hint not in PLATFORMS:
        raise InputError(f"Unknown platform '{platform_hint}'.")

    if "/" in text or re.match(r"^(https?://)?(www\.)?[\w.-]+\.(com|in|to|co)\b", text, re.I):
        parsed = _parse_url(text)
        if platform_hint and parsed.platform != platform_hint:
            raise InputError(f"That URL is for {PLATFORMS[parsed.platform]}, not {PLATFORMS[platform_hint]}.")
        return parsed

    candidates = _id_candidates(text)
    if platform_hint:
        if platform_hint not in candidates:
            raise InputError(f"'{text}' doesn't look like a {PLATFORMS[platform_hint]} {ID_LABELS[platform_hint]}.")
        return ParsedInput(platform_hint, normalise_id(platform_hint, text), None)
    if not candidates:
        raise InputError(f"'{text}' doesn't look like an ASIN, Myntra Style ID, Nykaa Product ID or Tata CLiQ Product ID.")
    if len(candidates) > 1:
        raise AmbiguousInput(text, candidates)
    return ParsedInput(candidates[0], normalise_id(candidates[0], text), None)


def product_url(platform, platform_id):
    """Canonical product page link built from the ID."""
    if platform == "amazon":
        return f"https://www.amazon.in/dp/{platform_id}"
    if platform == "myntra":
        return f"https://www.myntra.com/{platform_id}"
    if platform == "nykaa":
        return f"https://www.nykaa.com/p/{platform_id}"
    return f"https://www.tatacliq.com/p-{platform_id.lower()}"


def search_url(platform, query):
    """A link that opens the platform's own search page, for manual matching."""
    if platform == "amazon":
        return f"https://www.amazon.in/s?k={quote_plus(query)}"
    if platform == "myntra":
        slug = quote(re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-"))
        return f"https://www.myntra.com/{slug}?rawQuery={quote_plus(query)}"
    if platform == "nykaa":
        return f"https://www.nykaa.com/search/result/?q={quote_plus(query)}"
    return f"https://www.tatacliq.com/search/?searchCategory=all&text={quote_plus(query)}"
