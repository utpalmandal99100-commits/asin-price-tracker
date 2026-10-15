from creatorsapi_python_sdk.models.item import Item

from tracker.amazon import parse_item

RAW = {
    "asin": "B0TEST1234",
    "detailPageURL": "https://www.amazon.in/dp/B0TEST1234?tag=x-21",
    "itemInfo": {
        "title": {"displayValue": "Maybelline New York Colossal Kajal, Black, 0.35g"},
        "byLineInfo": {"brand": {"displayValue": "Maybelline"}},
        "externalIds": {"eans": {"displayValues": ["8901526203546"]}},
    },
    "offersV2": {"listings": [{
        "isBuyBoxWinner": True,
        "availability": {"type": "IN_STOCK", "message": "In stock"},
        "price": {
            "money": {"amount": 199.0, "currency": "INR", "displayAmount": "₹199.00"},
            "savingBasis": {"money": {"amount": 249.0, "currency": "INR"},
                            "savingBasisType": "LIST_PRICE", "savingBasisTypeLabel": "M.R.P.:"},
        },
    }]},
}


def test_parses_sdk_item_round_trip():
    # Goes through the real SDK model so field names match what the API client returns.
    item = Item.from_dict(RAW)
    p = parse_item(item.to_dict())
    assert p["platform_id"] == "B0TEST1234"
    assert p["price"] == 199.0 and p["mrp"] == 249.0
    assert p["status"] == "live"
    assert p["brand"] == "Maybelline"
    assert p["eans"] == ["8901526203546"]


def test_no_offer_is_unavailable_not_zero():
    p = parse_item({"asin": "B0TEST1234", "itemInfo": {}, "offersV2": {"listings": []}})
    assert p["status"] == "unavailable" and p["price"] is None


def test_was_price_is_not_treated_as_mrp():
    raw = {**RAW, "offersV2": {"listings": [{"price": {
        "money": {"amount": 199.0, "currency": "INR"},
        "savingBasis": {"money": {"amount": 229.0}, "savingBasisType": "WAS_PRICE", "savingBasisTypeLabel": "Was:"}}}]}}
    p = parse_item(Item.from_dict(raw).to_dict())
    assert p["mrp"] is None and p["note"]
