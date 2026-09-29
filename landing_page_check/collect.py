"""Load one page in headless Chromium the way an ad click sees it and return
raw, JSON-serialisable facts. One GET navigation per call; nothing is ever
clicked, typed, scrolled or submitted."""

from __future__ import annotations

import time

from . import __version__
from .dom import DOM_SCRIPT, LCP_SCRIPT

UA_TOKEN = "landing-page-check/%s (+https://github.com/dreadmoreeee/landing-page-check)" % ".".join(__version__.split(".")[:2])

PROFILES = {
    "mobile": {
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 2.625,
        "is_mobile": True,
        "has_touch": True,
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Mobile Safari/537.36",
    },
    "desktop": {
        "viewport": {"width": 1366, "height": 768},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36",
    },
}

# Roughly Lighthouse's "slow 4G" plus a 4x CPU slowdown.
THROTTLE = {"offline": False, "latency": 150, "downloadThroughput": 1.6 * 1024 * 1024 / 8,
            "uploadThroughput": 750 * 1024 / 8}


def _headers(response, name: str) -> list[str]:
    try:
        return [h["value"] for h in response.headers_array() if h["name"].lower() == name]
    except Exception:
        return []


def collect(url: str, *, browser=None, profile: str = "mobile", user_agent: str | None = None,
            locale: str = "en-CA", settle: float = 2.0, timeout: float = 45.0, throttle: bool = False,
            screenshot: str | None = None, setup=None) -> dict:
    """Load `url` and return raw facts. `browser` is an already launched
    Playwright Chromium browser (one is launched if None). `setup(page)` is
    called before navigation, e.g. to install page.route handlers."""
    if browser is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                return collect(url, browser=b, profile=profile, user_agent=user_agent, locale=locale,
                               settle=settle, timeout=timeout, throttle=throttle, screenshot=screenshot,
                               setup=setup)
            finally:
                b.close()

    prof = PROFILES[profile]
    if user_agent is None:
        major = (browser.version or "0").split(".")[0]
        user_agent = prof["ua"].format(v=major + ".0.0.0") + " " + UA_TOKEN
    ctx = browser.new_context(viewport=prof["viewport"], device_scale_factor=prof["device_scale_factor"],
                              is_mobile=prof["is_mobile"], has_touch=prof["has_touch"],
                              user_agent=user_agent, locale=locale, service_workers="block")
    page = ctx.new_page()
    raw: dict = {
        "input_url": url, "profile": {"name": profile, "viewport": prof["viewport"], "user_agent": user_agent,
                                      "browser": "Chromium " + (browser.version or "?"), "throttled": throttle},
        "error": None, "chain": [], "final_url": None, "final_status": None,
        "x_robots_tag": [], "link_headers": [], "requests": [], "perf": {}, "dom": None,
    }
    t0 = time.monotonic()
    nav_requests = []
    net = {"bytes": 0, "ids": set()}

    def on_request(req):
        entry = {"url": req.url, "method": req.method, "type": req.resource_type,
                 "t_ms": int((time.monotonic() - t0) * 1000)}
        raw["requests"].append(entry)
        try:
            if req.is_navigation_request() and req.frame == page.main_frame:
                nav_requests.append(req)
        except Exception:
            pass

    page.on("request", on_request)
    try:
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.on("Network.loadingFinished", lambda p: net.__setitem__("bytes", net["bytes"] + int(p.get("encodedDataLength") or 0)))
        cdp.on("Network.requestWillBeSent", lambda p: net["ids"].add(p.get("requestId")))
        if throttle:
            cdp.send("Network.emulateNetworkConditions", THROTTLE)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    except Exception:
        cdp = None
    if setup:
        setup(page)

    try:
        response = None
        try:
            response = page.goto(url, wait_until="load", timeout=timeout * 1000)
        except Exception as e:  # a client-side redirect can interrupt the first navigation
            if not nav_requests:
                raise
            page.wait_for_load_state("load", timeout=timeout * 1000)
            if "interrupted" not in str(e).lower() and "aborted" not in str(e).lower():
                raise
        try:
            page.wait_for_load_state("networkidle", timeout=min(10.0, timeout) * 1000)
        except Exception:
            pass
        if settle > 0:
            page.wait_for_timeout(settle * 1000)

        for i, req in enumerate(nav_requests):
            resp = req.response()
            client = i > 0 and req.redirected_from is None
            raw["chain"].append({"url": req.url, "status": resp.status if resp else None,
                                 "type": "client" if client else "http"})
        final_resp = nav_requests[-1].response() if nav_requests else response
        raw["final_url"] = page.url
        raw["final_status"] = final_resp.status if final_resp else None
        if final_resp:
            raw["x_robots_tag"] = _headers(final_resp, "x-robots-tag")
            raw["link_headers"] = _headers(final_resp, "link")
        if raw["chain"] and raw["chain"][-1]["url"] != page.url:
            raw["chain"].append({"url": page.url, "status": None, "type": "client"})

        perf = page.evaluate(LCP_SCRIPT)
        raw["dom"] = page.evaluate(DOM_SCRIPT)
        raw["perf"] = {
            "lcp_ms": (perf.get("lcp") or {}).get("ms"),
            "lcp_element": (perf.get("lcp") or {}).get("element"),
            "lcp_url": (perf.get("lcp") or {}).get("url"),
            "nav": perf.get("nav"),
            "bytes": net["bytes"] if cdp else None,
            "requests": len(raw["requests"]),
        }
        if screenshot:
            page.screenshot(path=screenshot)
    except Exception as e:
        raw["error"] = "%s: %s" % (type(e).__name__, str(e).splitlines()[0] if str(e) else "")
    finally:
        raw["elapsed_s"] = round(time.monotonic() - t0, 2)
        ctx.close()
    return raw
