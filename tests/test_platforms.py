import pytest

from tracker.platforms import AmbiguousInput, InputError, parse_input


@pytest.mark.parametrize("text,platform,pid", [
    ("https://www.amazon.in/Lakme-Kajal/dp/B07XYZ1234/ref=sr_1_1?keywords=x", "amazon", "B07XYZ1234"),
    ("amazon.in/gp/product/b0abcdefgh", "amazon", "B0ABCDEFGH"),
    ("B0CHX1W1XY", "amazon", "B0CHX1W1XY"),
    ("https://www.myntra.com/tshirts/roadster/roadster-men-black-tshirt/11546402/buy", "myntra", "11546402"),
    ("https://www.nykaa.com/maybelline-new-york-colossal-kajal/p/14498?skuId=14498", "nykaa", "14498"),
    ("https://www.nykaa.com/x?productId=99812", "nykaa", "99812"),
    ("https://www.tatacliq.com/puma-shoes/p-mp000000017021234", "tatacliq", "MP000000017021234"),
    ("mp000000017021234", "tatacliq", "MP000000017021234"),
])
def test_detects_platform(text, platform, pid):
    p = parse_input(text)
    assert (p.platform, p.platform_id) == (platform, pid)


def test_bare_number_is_ambiguous_until_platform_given():
    with pytest.raises(AmbiguousInput) as exc:
        parse_input("11546402")
    assert exc.value.candidates == ["myntra", "nykaa"]
    assert parse_input("11546402", "myntra").platform == "myntra"


def test_rejects_other_sites_and_short_links():
    with pytest.raises(InputError):
        parse_input("https://www.flipkart.com/x/p/itm123")
    with pytest.raises(InputError):
        parse_input("https://amzn.in/d/abc")
    with pytest.raises(InputError):
        parse_input("https://www.amazon.com/dp/B0CHX1W1XY")


def test_url_platform_must_match_hint():
    with pytest.raises(InputError):
        parse_input("https://www.myntra.com/123456/buy", "nykaa")
