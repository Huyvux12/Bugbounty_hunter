from feed_bot.classify import classify_kind


def test_url_and_domain():
    assert classify_kind("https://login.starbucks.co.jp", "URL") == "url"
    assert classify_kind("www.starbucks.co.jp", "URL") == "domain"


def test_wildcard_cidr_mobile_repo():
    assert classify_kind("*.example.com", "WILDCARD") == "wildcard"
    assert classify_kind("10.0.0.0/24", "CIDR") == "cidr"
    assert classify_kind("https://apps.apple.com/app/x", "APPLE_STORE_APP_ID") == "mobile"
    assert classify_kind("https://github.com/org/repo", "SOURCE_CODE") == "repo"
