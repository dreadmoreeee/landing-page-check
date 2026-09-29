"""End-to-end checks against local fixture pages (no internet)."""

import json

from landing_page_check.analysis import analyze
from landing_page_check.collect import collect



def html(body, head="", title="Test page"):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>%s</title>%s<style>body{margin:0;font:16px sans-serif}</style></head><body>%s</body></html>"
            % (title, head, body))


QUERY = "utm_source=google&utm_medium=cpc&utm_campaign=spring&gclid=TESTCLICK"


def run(browser, url, setup=None, **kw):
    raw = collect(url, browser=browser, settle=0.2, timeout=15, setup=setup)
    assert raw["error"] is None, raw["error"]
    return analyze(raw, **kw)


def test_redirect_keeps_parameters(site, browser):
    site.routes["/go"] = lambda q: (301, {"Location": "/landing?" + q}, "")
    site.page("/landing", html("<h1>Hello</h1>"))
    r = run(browser, site.base + "/go?" + QUERY)
    red = r["checks"]["redirects"]
    assert [h["status"] for h in red["hops"]] == [301, 200]
    assert red["params"] == ["utm_source", "utm_medium", "utm_campaign", "gclid"]
    assert red["hops"][-1]["missing"] == []
    assert red["points"] == 14 and red["redirects"] == 1  # one hop costs a point
    assert not any(f["priority"] == "high" for f in red["fixes"])


def test_redirect_drops_parameters(site, browser):
    # hop 2 drops the click id, hop 3 drops everything
    site.routes["/ad"] = lambda q: (302, {"Location": "/step?" + q.replace("&gclid=TESTCLICK", "")}, "")
    site.routes["/step"] = (301, {"Location": "/landing"}, "")
    site.page("/landing", html("<h1>Hello</h1>"))
    r = run(browser, site.base + "/ad?" + QUERY)
    red = r["checks"]["redirects"]
    assert len(red["hops"]) == 3
    assert red["points"] == 0
    assert red["lost_at"][0]["hop"] == 2 and red["lost_at"][0]["params"] == ["gclid"]
    assert red["lost_at"][1]["hop"] == 3 and "utm_source" in red["lost_at"][1]["params"]
    assert red["hops"][-1]["missing"] == ["utm_source", "utm_medium", "utm_campaign", "gclid"]
    assert any(f["priority"] == "high" and "Hop 2 drops gclid" in f["fix"] for f in r["fixes"])


def test_noindex_meta_and_header(site, browser):
    site.page("/a", html("<h1>A</h1>", head='<meta name="robots" content="noindex, follow">'))
    site.page("/b", html("<h1>B</h1>"), headers={"X-Robots-Tag": "googlebot: noindex"})
    site.page("/c", html("<h1>C</h1>", head='<link rel="canonical" href="/c">'))
    a = run(browser, site.base + "/a")["checks"]["indexability"]
    b = run(browser, site.base + "/b")["checks"]["indexability"]
    c = run(browser, site.base + "/c?" + QUERY)["checks"]["indexability"]
    assert a["noindex"] and a["summary"].startswith("noindex (meta robots)")
    assert b["noindex"] and "X-Robots-Tag" in b["summary"]
    assert not c["noindex"] and c["canonical_is_self"] and c["summary"] == "indexable, self-canonical"
    assert c["points"] == 5


def test_cta_above_and_below_fold(site, browser):
    site.page("/top", html('<h1>Roof repair</h1><a class="btn" href="/quote">Get a free quote</a>'))
    site.page("/low", html('<h1>Roof repair</h1><div style="height:1600px"></div>'
                           '<a class="btn" href="/quote">Get a free quote</a>'))
    top = run(browser, site.base + "/top")["checks"]["cta"]
    low = run(browser, site.base + "/low")
    assert top["points"] == 15 and top["ctas"][0]["text"] == "Get a free quote"
    assert low["checks"]["cta"]["points"] == 0
    assert low["fixes"][0]["priority"] == "high" and low["fixes"][0]["check"] == "cta"


def test_cta_covered_by_cookie_banner(site, browser):
    body = ('<h1>Roof repair</h1><div style="height:500px"></div><a class="btn" href="/quote" '
            'style="display:block;padding:20px">Book now</a>'
            '<div id="cookie-box" style="position:fixed;left:0;right:0;bottom:0;height:500px;background:#fff">'
            'We use cookies. <button>Accept</button> <button>Reject</button></div>')
    site.page("/p", html(body))
    r = run(browser, site.base + "/p")
    assert r["checks"]["consent"]["banner"]["visible"]
    cta = r["checks"]["cta"]
    assert cta["points"] == 7 and "cookie-box" in cta["ctas"][0]["covered_by"]
    assert all(c["text"] not in ("Accept", "Reject") for c in cta["ctas"])


def test_tel_link_and_plain_number(site, browser):
    site.page("/tel", html('<h1>Plumber</h1><a href="tel:+15065550142">Call (506) 555-0142</a>'))
    site.page("/plain", html("<h1>Plumber</h1><p>Call us at 506-555-0199 today.</p>"))
    tel = run(browser, site.base + "/tel")["checks"]["phone"]
    plain = run(browser, site.base + "/plain")["checks"]["phone"]
    assert tel["points"] == 5 and tel["phones"] == [{"number": "(506) 555-0142", "click_to_call": True}]
    assert tel["tel_links"][0]["above_fold"]
    assert plain["points"] == 1 and plain["phones"][0]["click_to_call"] is False
    assert plain["fixes"][0]["priority"] == "medium"


def test_required_field_form(site, browser):
    form = ('<form action="/send"><input name="name" required><input type="email" name="email" required>'
            '<input name="phone"><textarea name="message" aria-required="true"></textarea>'
            '<input type="hidden" name="token" value="x"><input name="website" style="display:none">'
            '<label><input type="radio" name="when" value="am"> AM</label><label><input type="radio" name="when" value="pm"> PM</label>'
            '<button type="submit">Send request</button></form>')
    site.page("/f", html("<h1>Contact</h1>" + form))
    r = run(browser, site.base + "/f")
    f = r["checks"]["form"]
    assert f["forms"][0]["fields"] == 5  # name, email, phone, message, one radio group
    assert f["forms"][0]["required"] == 3
    assert f["forms"][0]["above_fold"] and f["points"] == 5
    assert any(c["kind"] == "form" for c in r["checks"]["cta"]["ctas"])


def test_schema_trust_markup(site, browser):
    ld = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": "Example Roofing",
          "address": {"@type": "PostalAddress", "streetAddress": "1 Example Road", "addressLocality": "Exampleville"},
          "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "reviewCount": "31"}}
    head = '<script type="application/ld+json">%s</script>' % json.dumps(ld)
    site.page("/t", html('<h1>Roofing</h1><footer><a href="/privacy-policy">Privacy policy</a></footer>', head=head))
    site.page("/none", html("<h1>Roofing</h1>"))
    t = run(browser, site.base + "/t")["checks"]["trust"]
    n = run(browser, site.base + "/none")["checks"]["trust"]
    assert t["schema"]["address"] and t["schema"]["reviews"] and t["privacy_links"]
    assert "LocalBusiness" in t["schema"]["types"] and t["points"] == 5
    assert n["points"] == 0 and [f["priority"] for f in n["fixes"]] == ["medium", "low", "low"]


def test_tracker_fired_on_load_intercepted(site, browser):
    head = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-TEST0001"></script>'
            '<script>new Image().src="https://www.google-analytics.com/g/collect?v=2&tid=G-TEST0001&gcs=G111";'
            'new Image().src="https://www.facebook.com/tr?id=1234&ev=PageView";</script>')
    site.page("/p", html("<h1>Offer</h1>", head=head))
    seen = []

    def setup(page):
        def fake(route):
            seen.append(route.request.url)
            route.fulfill(status=200, body="", content_type="text/javascript")
        for pattern in ("https://www.googletagmanager.com/**", "https://www.google-analytics.com/**",
                        "https://www.facebook.com/**"):
            page.route(pattern, fake)

    r = run(browser, site.base + "/p", setup=setup)
    con = r["checks"]["consent"]
    vendors = {t["vendor"]: t for t in con["trackers"]}
    assert len(seen) == 3
    assert vendors["Google Tag Manager"]["scripts"] == 1
    assert vendors["Google Analytics"]["hits"] == 1 and vendors["Google Analytics"]["consent_mode"] == ["G111"]
    assert vendors["Meta Pixel"]["category"] == "ads conversion"
    assert con["points"] == 0 and not con["banner"]["visible"]
    assert any(f["priority"] == "high" and f["check"] == "consent" for f in r["fixes"])


def test_tracker_on_second_host_with_banner(site, site2, browser):
    site2.routes["/collect"] = (204, {"Access-Control-Allow-Origin": "*"}, "")
    body = ('<h1>Offer</h1><div class="consent-bar" style="position:fixed;bottom:0;left:0;right:0;padding:20px">'
            'This site uses cookies (traceurs). <button>OK</button></div>'
            '<script>fetch("%s/collect?event=page_view", {mode: "no-cors"})</script>' % site2.base)
    site.page("/p", html(body))
    raw = collect(site.base + "/p", browser=browser, settle=0.3, timeout=15)
    r = analyze(raw, tracker_hosts=["127.0.0.1:%d" % site2.port])
    con = r["checks"]["consent"]
    assert con["banner"]["visible"]
    assert con["trackers"][0]["hits"] == 1 and con["points"] == 2
    assert con["fixes"][0]["priority"] == "medium"
    assert any(h.startswith("/collect") for h in site2.hits)


def test_message_match_accents_and_case(site, browser):
    page = html('<h1>CR\u00c9ATION DE SITES WEB \u00e0 Moncton</h1><p>Soumission gratuite en 24 h.</p>',
                title="Cr\u00e9ation de site web | Studio Exemple")
    site.page("/fr", page)
    r = run(browser, site.base + "/fr", keywords=["creation de site web, referencement"],
            headline="Creation de site web a Moncton")
    msg = r["checks"]["message"]
    kw = {k["keyword"]: k for k in msg["keywords"]}
    assert kw["creation de site web"]["title"] and kw["creation de site web"]["h1"] and kw["creation de site web"]["atf"]
    assert not any(kw["referencement"][x] for x in ("title", "h1", "atf"))
    assert msg["headline"]["exact_in_h1"]
    assert any(f["priority"] == "high" and "referencement" in f["fix"] for f in msg["fixes"])


def test_tap_targets_and_speed(site, browser):
    links = "".join('<a href="/p%d" style="display:inline-block;width:20px;height:20px;margin:2px">%d</a>' % (i, i)
                    for i in range(6))
    site.page("/tap", html("<h1>Pages</h1><nav>%s</nav><a class=\"btn\" href=\"/go\" "
                           "style=\"display:block;height:60px\">Get started</a>" % links))
    r = run(browser, site.base + "/tap")
    tap = r["checks"]["tap_targets"]
    assert tap["total"] == 7 and tap["small"] == 6 and tap["crowded"] == 6
    assert tap["points"] < 10
    speed = r["checks"]["speed"]
    assert speed["lcp_ms"] is not None and speed["lcp_ms"] > 0
    assert speed["requests"] >= 1 and speed["bytes"] > 0
