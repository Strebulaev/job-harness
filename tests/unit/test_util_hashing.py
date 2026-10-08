"""M2-2 tests: URL canonicalization, url_hash, jd_raw_hash, fuzzy dedup."""

from __future__ import annotations

from jobharness.util.hashing import (
    canonicalize_url,
    company_title_key,
    fuzzy_similarity,
    jd_raw_hash,
    url_hash,
)


def test_canonicalize_url_drops_tracking_params():
    url = "https://Example.com/path/?utm_source=test&utm_medium=email&ref=abc&q=1"
    canon = canonicalize_url(url)
    assert "utm_" not in canon
    assert "ref=" not in canon
    assert "q=1" in canon
    assert "example.com" in canon


def test_canonicalize_url_lowercases_host():
    assert canonicalize_url("https://Example.COM/x") == "https://example.com/x"


def test_canonicalize_url_drops_default_ports():
    assert canonicalize_url("http://example.com:80/x") == "http://example.com/x"
    assert canonicalize_url("https://example.com:443/x") == "https://example.com/x"


def test_canonicalize_url_strips_fragment():
    assert canonicalize_url("https://example.com/x#section") == "https://example.com/x"


def test_canonicalize_url_trailing_slash():
    assert canonicalize_url("https://example.com/path/") == "https://example.com/path"


def test_url_hash_deterministic():
    assert url_hash("https://example.com/a") == url_hash("https://example.com/a")


def test_url_hash_distinguishes_paths():
    assert url_hash("https://example.com/a") != url_hash("https://example.com/b")


def test_url_hash_equivalent_tracking():
    # Two URLs that differ only in tracking params should hash the same.
    a = "https://example.com/job?utm_source=x&ref=y"
    b = "https://example.com/job"
    assert url_hash(a) == url_hash(b)


def test_jd_raw_hash_whitespace_insensitive():
    a = "Hello   World\n  Foo"
    b = "Hello World Foo"
    assert jd_raw_hash(a) == jd_raw_hash(b)


def test_jd_raw_hash_distinguishes():
    assert jd_raw_hash("Hello") != jd_raw_hash("Goodbye")


def test_fuzzy_similarity_identical():
    assert fuzzy_similarity("Acme Corp, Senior Backend Engineer",
                            "Acme Corp, Senior Backend Engineer") == 1.0


def test_fuzzy_similarity_high():
    # One character difference on a long string.
    a = "Acme Corp, Senior Backend Engineer"
    b = "Acme Corp, Senior Backend Engneer"  # typo
    assert fuzzy_similarity(a, b) >= 0.92


def test_fuzzy_similarity_low():
    a = "Acme Corp, Senior Backend Engineer"
    b = "Globex Inc., Junior Frontend Developer"
    assert fuzzy_similarity(a, b) < 0.5


def test_company_title_key():
    assert company_title_key("Acme", "Senior BE") == "acme :: senior be"
    assert company_title_key(None, "Senior BE") == " :: senior be"
    assert company_title_key("Acme", None) == "acme :: "
