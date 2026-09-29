"""Pure tests for the scoring rules and analysis helpers (no browser)."""

import pytest

from landing_page_check import analysis as A
from landing_page_check import scoring as S


def raw_page(**dom):
    base = {"viewport": {"w": 412, "h": 915}, "title": "", "h1": [], "atf_text": "", "body_text": "",
            "meta_robots": [], "canonicals": [], "ctas": [], "forms": [], "tel_links": [], "privacy_links": [],
            "jsonld": [], "microdata": [], "address_elements": [], "consent_banner": {"visible": False},
            "tap": {"total": 0, "small": 0, "crowded": 0, "examples": []}}
    base.update(dom)
    return {"input_url": "https://example.com/offer", "final_url": "https://example.com/offer",
            "final_status": 200, "chain": [{"url": "https://example.com/offer", "status": 200, "type": "http"}],
            "x_robots_tag": [], "link_headers": [], "requests": [], "error": None,
            "profile": {"name": "mobile", "throttled": False},
            "perf": {"lcp_ms": 1200, "bytes": 800_000, "requests": 30}, "dom": base}


@pytest.mark.parametrize("ms,pts", [(None, None), (800, 10), (2500, 10), (2501, 5), (4000, 5), (4001, 0)])
def test_lcp_points(ms, pts):
    assert S.lcp_points(ms) == pts


def test_weight_points():
    assert S.weight_points(1_000_000, 20) == 5
    assert S.weight_points(2_500_000, 80) == 3
    assert S.weight_points(6_000_000, 150) == 0
    assert S.weight_points(None, None) == 3.5


def test_tap_points():
    assert S.tap_points(0, 0, 0) == 10
    assert S.tap_points(10, 0, 0) == 10
    assert S.tap_points(10, 2, 0) == 9
    assert S.tap_points(10, 5, 5) == 0
    assert S.tap_points(100, 10, 5) == 8.5


def test_form_and_keyword_points():
    assert [S.form_points(n) for n in (None, 3, 5, 6, 8, 9)] == [None, 5, 5, 3, 3, 1]
    assert S.keyword_points([{"title": True, "h1": True, "atf": True}], 12) == 12
    assert S.keyword_points([{"title": False, "h1": True, "atf": True},
                             {"title": False, "h1": False, "atf": False}], 10) == 3.5
    assert S.headline_points(0.5, 8) == 4


def test_overall_ignores_not_applicable_and_sorts_fixes():
    checks = {
        "redirects": {"points": None, "max": 15, "fixes": []},
        "cta": {"points": 0, "max": 15, "fixes": [{"priority": "high", "fix": "move CTA"}]},
        "trust": {"points": 5, "max": 5, "fixes": [{"priority": "low", "fix": "reviews"}]},
        "phone": {"points": 5, "max": 5, "fixes": [{"priority": "medium", "fix": "tel"}]},
    }
    score, fixes = S.overall(checks)
    assert score == 40  # 10 of 25 applicable points
    assert [f["priority"] for f in fixes] == ["high", "medium", "low"]
    assert fixes[0]["title"] == "Above-the-fold CTA"
    assert S.overall({}) == (0, [])


def test_max_points_sum_to_100():
    assert sum(S.MAX_POINTS.values()) == 100 and set(S.MAX_POINTS) == set(S.ORDER)


def test_normalize_and_phrase_matching():
    assert A.normalize("  Cr\u00c9ATION   d'\u00e9t\u00e9!  ") == "creation d ete"
    assert A.contains_phrase("Web Designs for small shops", "website design") is False
    assert A.contains_phrase("Website Designs for small shops", "website design")
    assert A.contains_phrase("R\u00e9novation de cuisines", "renovation cuisine") is False
    assert A.contains_phrase("R\u00e9novation de cuisines", "renovation de cuisine")
    assert A.coverage("Fast roof repair in Moncton", "Roof Repair in Moncton, Fast") == 1.0
    assert A.coverage("roof", "roof repair") == 0.5
    assert A.coverage("anything", "the and") == 0.0


def test_tracking_params_and_url_key():
    url = "https://Example.com:443/a/?utm_source=g&x=1&gclid=abc&UTM_Term=z"
    assert A.tracking_params(url) == {"utm_source": "g", "gclid": "abc", "UTM_Term": "z"}
    assert A.url_key(url) == A.url_key("https://example.com/a?x=1#top")
    assert A.url_key("http://example.com/a") != A.url_key("https://example.com/a")


def test_robots_directives():
    d = A.robots_directives([{"name": "robots", "content": "noindex, nofollow"}], ["bingbot: noarchive", "max-snippet: 20"])
    assert set(d) == {"noindex", "nofollow", "max-snippet"}
    d = A.robots_directives([], ["googlebot: noindex"])
    assert d["noindex"] == ["X-Robots-Tag"]


def test_indexability_states():
    raw = raw_page(canonicals=["https://example.com/other"], meta_robots=[{"name": "robots", "content": "noindex"}])
    c = A.check_indexability(raw)
    assert c["noindex"] and c["points"] == 3 and c["fixes"][0]["priority"] == "medium"
    raw = raw_page(canonicals=["https://example.com/offer?utm_source=x"])
    c = A.check_indexability(raw)
    assert c["canonical_is_self"] and "tracking parameters" in c["fixes"][0]["fix"]
    raw = raw_page()
    raw["final_status"] = 404
    assert A.check_indexability(raw)["points"] == 0
    raw = raw_page()
    raw["link_headers"] = ['<https://example.com/offer>; rel="canonical"']
    c = A.check_indexability(raw)
    assert c["summary"] == "indexable, self-canonical" and c["points"] == 5


def test_redirects_without_params_is_not_applicable():
    c = A.check_redirects(raw_page())
    assert c["points"] is None and c["status"] == "n/a"


def test_redirect_value_changed():
    raw = raw_page()
    raw["input_url"] = "https://example.com/go?gclid=ABC"
    raw["chain"] = [{"url": "https://example.com/go?gclid=ABC", "status": 301, "type": "http"},
                    {"url": "https://example.com/offer?gclid=abc", "status": 200, "type": "http"}]
    c = A.check_redirects(raw)
    assert c["hops"][-1]["changed"] == ["gclid"] and c["points"] == 11


def test_phone_numbers():
    text = "Call 1-506-555-0142 or +33 1 23 45 67 89. Order #2026-0001, 12 345 visits, (506) 555 0199."
    nums = A.find_phone_numbers(text)
    assert nums == ["1-506-555-0142", "(506) 555 0199", "+33 1 23 45 67 89"]
    raw = raw_page(body_text="Call 506-555-0142", tel_links=[{"href": "tel:+1 506 555 0142", "visible": True, "above_fold": True}])
    assert A.check_phone(raw)["points"] == 5
    assert A.check_phone(raw_page())["points"] == 2


def test_address_text():
    assert A.text_has_address("Example Co, 12 Main Street, Exampleville")
    assert A.text_has_address("Exampleville NB E1A 2B3")
    assert A.text_has_address("450, rue Principale")
    assert not A.text_has_address("Open 9 to 5, 7 days a week")


def test_schema_signals_graph_and_microdata():
    s = A.schema_signals(['{"@graph": [{"@type": ["Organization"], "address": "1 Main St"}]}', "{bad"],
                         ["https://schema.org/AggregateRating"])
    assert s["address"] and s["reviews"] and s["invalid_jsonld"] == 1 and "Organization" in s["types"]


@pytest.mark.parametrize("url,vendor", [
    ("https://www.google-analytics.com/g/collect?v=2", "Google Analytics"),
    ("https://region1.google-analytics.com/g/collect", "Google Analytics"),
    ("https://www.googletagmanager.com/gtm.js?id=GTM-X", "Google Tag Manager"),
    ("https://googleads.g.doubleclick.net/pagead/viewthroughconversion/1/", "Google Ads"),
    ("https://www.google.ca/pagead/1p-conversion/1/", "Google Ads"),
    ("https://www.facebook.com/tr?id=1&ev=PageView", "Meta Pixel"),
    ("https://bat.bing.com/action/0?ti=1", "Microsoft Ads UET"),
    ("https://y.clarity.ms/collect", "Microsoft Clarity"),
    ("https://www.facebook.com/examplepage", None),
    ("https://www.google.com/search?q=x", None),
    ("https://cdn.example.com/app.js", None),
])
def test_classify_request(url, vendor):
    c = A.classify_request(url)
    assert (c[0] if c else None) == vendor


def test_classify_custom_host():
    assert A.classify_request("http://127.0.0.1:5001/c", ["127.0.0.1:5001"])[1] == "custom"
    assert A.classify_request("https://px.tracker.example/c", ["tracker.example"])[0] == "Custom (tracker.example)"


def test_consent_verdicts():
    def run(requests, banner):
        raw = raw_page(consent_banner={"visible": banner, "element": "div#cmp"})
        raw["requests"] = requests
        return A.check_consent(raw)
    hit = {"url": "https://www.google-analytics.com/g/collect?gcs=G111", "type": "image", "t_ms": 5}
    denied = {"url": "https://www.google-analytics.com/g/collect?gcs=G100", "type": "ping", "t_ms": 5}
    script = {"url": "https://www.googletagmanager.com/gtag/js?id=G-1", "type": "script", "t_ms": 1}
    assert run([hit], False)["points"] == 0
    assert run([hit], True)["points"] == 2
    assert run([script, denied], True)["points"] == 4
    ok = run([script], True)
    assert ok["points"] == 5 and "tag script(s) loaded" in ok["summary"] and ok["summary"].endswith("consent banner visible")
    assert run([], False)["points"] == 5


def test_message_not_applicable_and_weights():
    raw = raw_page(title="Website design in Exampleville", h1=["Website design that brings calls"],
                   atf_text="Website design that brings calls. Get a quote.")
    assert A.check_message(raw)["points"] is None
    full = A.check_message(raw, ["website design"], "Website design that brings calls")
    assert full["points"] == 20 and full["fixes"] == []
    miss = A.check_message(raw, ["logo design"], "Cheap logos in one day")
    assert miss["points"] < 5 and [f["priority"] for f in miss["fixes"]] == ["high", "high"]


def test_cta_and_form_checks():
    cta = {"kind": "button", "text": "Book", "element": "button", "box": {"x": 0, "y": 300, "w": 100, "h": 50}, "covered_by": None}
    assert A.check_cta(raw_page(ctas=[cta]))["points"] == 15
    assert A.check_cta(raw_page(ctas=[dict(cta, covered_by="div#cmp")]))["points"] == 7
    assert A.check_cta(raw_page())["fixes"][0]["priority"] == "high"
    forms = [{"element": "form", "fields": 11, "required": 9, "names": [], "above_fold": False, "box": None}]
    f = A.check_form(raw_page(forms=forms))
    assert f["points"] == 1 and f["fixes"][0]["priority"] == "medium"
    assert A.check_form(raw_page())["points"] is None


def test_analyze_full_and_error():
    r = A.analyze(raw_page(title="t"))
    assert 0 <= r["score"] <= 100 and set(r["checks"]) == set(S.ORDER)
    bad = raw_page()
    bad["error"], bad["dom"] = "TimeoutError: boom", None
    r = A.analyze(bad)
    assert r["score"] is None and r["error"] == "TimeoutError: boom"
