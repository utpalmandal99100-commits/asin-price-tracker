"""Amazon India via the official Amazon Creators API (successor of PA-API 5).

Needs an Amazon Associates (India) account with Creators API credentials.
Only data returned by the API is used; nothing is scraped from amazon.in.
"""

import logging

from . import config

log = logging.getLogger(__name__)


class AmazonNotConfigured(RuntimeError):
    pass


class AmazonError(RuntimeError):
    pass


def configured():
    c = config.amazon()
    return bool(c["credential_id"] and c["credential_secret"] and c["partner_tag"])


_client = None


def _api():
    global _client
    if not configured():
        raise AmazonNotConfigured("Amazon Creators API credentials are not set.")
    if _client is None:
        from amazon_creatorsapi import AmazonCreatorsApi

        c = config.amazon()
        # One request per second is the default Creators API allowance.
        _client = AmazonCreatorsApi(
            credential_id=c["credential_id"],
            credential_secret=c["credential_secret"],
            version=c["version"],
            tag=c["partner_tag"],
            country="IN",
            throttling=1.0,
        )
    return _client


def _get(d, *path):
    for key in path:
        if d is None:
            return None
        if isinstance(key, int):
            d = d[key] if isinstance(d, list) and len(d) > key else None
        else:
            d = d.get(key) if isinstance(d, dict) else None
    return d


def parse_item(item):
    """Turn one Creators API item (as a camelCase dict) into our listing fields."""
    info = item.get("itemInfo") or {}
    listings = _get(item, "offersV2", "listings") or []
    listing = next((l for l in listings if l.get("isBuyBoxWinner")), listings[0] if listings else None)

    price = _get(listing, "price", "money", "amount")
    currency = _get(listing, "price", "money", "currency") or "INR"
    basis = _get(listing, "price", "savingBasis") or {}
    basis_type = str(basis.get("savingBasisType") or "")
    basis_label = str(basis.get("savingBasisTypeLabel") or "")
    mrp = None
    # Amazon India shows the MRP as the list-price saving basis ("M.R.P.").
    if basis_type.endswith("LIST_PRICE") or "M.R.P" in basis_label.upper() or "MRP" in basis_label.upper():
        mrp = _get(basis, "money", "amount")

    availability = (_get(listing, "availability", "type") or "").upper()
    if listing is None or price is None:
        status = "unavailable"
    elif availability in ("OUT_OF_STOCK", "UNAVAILABLE"):
        status = "unavailable"
    else:
        status = "live"
    if mrp is None and price is not None:
        # The API omits the saving basis when there is no discount, in which
        # case the selling price is the MRP. Flag it rather than assume silently.
        mrp_note = "MRP not returned by Amazon (no discount shown)"
    else:
        mrp_note = None

    pinfo = info.get("productInfo") or {}
    variant_bits = [_get(pinfo, "size", "displayValue"), _get(pinfo, "color", "displayValue")]
    return {
        "platform_id": item.get("asin"),
        "title": _get(info, "title", "displayValue"),
        "brand": _get(info, "byLineInfo", "brand", "displayValue") or _get(info, "byLineInfo", "manufacturer", "displayValue"),
        "variant": ", ".join(v for v in variant_bits if v) or None,
        "eans": _get(info, "externalIds", "eans", "displayValues") or [],
        "model": _get(info, "manufactureInfo", "model", "displayValue") or _get(info, "manufactureInfo", "itemPartNumber", "displayValue"),
        "url": item.get("detailPageURL"),
        "mrp": float(mrp) if mrp is not None else None,
        "price": float(price) if price is not None else None,
        "currency": currency,
        "status": status,
        "note": mrp_note if status == "live" else (_get(listing, "availability", "message") or "No offer returned by Amazon"),
    }


def _to_dict(item):
    return item.to_dict() if hasattr(item, "to_dict") else item


def get_items(asins):
    """Fetch ASINs (any number; the client batches 10 per call). Returns {asin: fields}."""
    from amazon_creatorsapi.errors import ItemsNotFoundError

    try:
        items = _api().get_items(list(asins))
    except ItemsNotFoundError:
        return {}
    except Exception as exc:  # network, auth, throttling
        log.warning("Creators API get_items failed: %s", exc)
        raise AmazonError(str(exc)) from exc
    out = {}
    for item in items:
        parsed = parse_item(_to_dict(item))
        if parsed["platform_id"]:
            out[parsed["platform_id"].upper()] = parsed
    return out


def search(keywords, brand=None, count=10):
    """Search Amazon India for candidate matches."""
    try:
        result = _api().search_items(keywords=keywords, brand=brand or None, item_count=count)
    except Exception as exc:
        if type(exc).__name__ == "ItemsNotFoundError":
            return []
        log.warning("Creators API search_items failed: %s", exc)
        raise AmazonError(str(exc)) from exc
    items = getattr(result, "items", None) or []
    return [parse_item(_to_dict(i)) for i in items]
