import base64

from auth import credentials_match, origin_allowed, parse_basic_auth


def basic(user_pass: str) -> str:
    return "Basic " + base64.b64encode(user_pass.encode()).decode()


def test_parse_basic_auth():
    assert parse_basic_auth(basic("admin:secret")) == ("admin", "secret")
    assert parse_basic_auth(basic("admin:se:cret")) == ("admin", "se:cret")


def test_parse_basic_auth_rejects_bad_headers():
    assert parse_basic_auth(None) is None
    assert parse_basic_auth("") is None
    assert parse_basic_auth("Bearer abc") is None
    assert parse_basic_auth("Basic !!!not-base64!!!") is None
    assert parse_basic_auth(basic("no-colon")) is None


def test_credentials_match():
    assert credentials_match(("admin", "secret"), "admin", "secret")
    assert not credentials_match(("admin", "wrong"), "admin", "secret")
    assert not credentials_match(("root", "secret"), "admin", "secret")
    assert not credentials_match(None, "admin", "secret")


def test_origin_allowed():
    assert origin_allowed(None, "host:7417")
    assert origin_allowed("http://host:7417", "host:7417")
    assert origin_allowed("https://HOST:7417", "host:7417")
    assert not origin_allowed("http://evil.example", "host:7417")
    assert not origin_allowed("http://host:9999", "host:7417")
