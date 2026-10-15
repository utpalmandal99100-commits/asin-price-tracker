from tracker.matching import HIGH, MEDIUM, extract_variant, score


def test_same_product_scores_high():
    a = {"brand": "Maybelline", "title": "Maybelline New York Colossal Kajal, Black, 0.35g"}
    b = {"brand": "Maybelline New York", "title": "Maybelline Colossal Kajal Black 0.35 g"}
    assert score(a, b)["score"] >= HIGH


def test_different_pack_size_is_never_a_match():
    a = {"brand": "Cetaphil", "title": "Cetaphil Gentle Skin Cleanser 125ml"}
    b = {"brand": "Cetaphil", "title": "Cetaphil Gentle Skin Cleanser 250 ml"}
    s = score(a, b)
    assert s["score"] < MEDIUM
    assert any("Variant differs" in r for r in s["reasons"])


def test_litres_and_ml_compare_equal():
    assert extract_variant("Shampoo 1 L")["quantity"] == extract_variant("Shampoo 1000ml")["quantity"]


def test_different_brand_scores_zero():
    assert score({"brand": "Nike", "title": "Running shoe"}, {"brand": "Puma", "title": "Running shoe"})["score"] == 0


def test_shared_ean_is_certain():
    a = {"brand": "X", "title": "foo", "eans": ["8901030865278"]}
    b = {"brand": "X", "title": "bar baz", "eans": ["8901030865278"]}
    assert score(a, b)["score"] == 100
