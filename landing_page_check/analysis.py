"""Turn raw page facts (collect.py) into checks with points and fixes.
Everything here is pure Python and runs without a browser."""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from . import __version__
from .scoring import (MAX_POINTS, form_points, headline_points, keyword_points, lcp_points, overall,
                      tap_points, weight_points)

# ---------------------------------------------------------------- text

STOPWORDS = set("""a an and are as at be by for from in is it of on or our the to we with you your
au aux avec ce ces dans de des du en est et la le les leur ma mes mon nos notre ou par pour qui sa
se ses son sur ta un une vos votre""".split())


def normalize(text: str | None) -> str:
    """Casefold, strip accents, turn punctuation into spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).replace("_", " ").split())


def _stem(token: str) -> str:
    """Tiny plural folding for English and French ("designs" -> "design",
    "travaux" -> "travau")."""
    if len(token) > 3 and token.endswith(("s", "x")):
        return token[:-1]
    return token


def tokens(text: str | None) -> list[str]:
    return [_stem(t) for t in normalize(text).split()]


def contains_phrase(text: str | None, phrase: str | None) -> bool:
    """Case-, accent- and simple-plural-insensitive phrase search on word
    boundaries."""
    needle, hay = tokens(phrase), tokens(text)
    if not needle:
        return False
    n = len(needle)
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def coverage(text: str | None, phrase: str | None) -> float:
    """Share of the meaningful words of `phrase` that appear in `text`."""
    words = [t for t in tokens(phrase) if t not in STOPWORDS and len(t) > 1]
    if not words:
        return 0.0
    hay = set(tokens(text))
    return sum(1 for w in words if w in hay) / len(words)


# ---------------------------------------------------------------- URLs

CLICK_IDS = {"gclid", "gbraid", "wbraid", "dclid", "gclsrc", "fbclid", "msclkid", "ttclid", "li_fat_id",
             "twclid", "yclid", "epik", "sccid", "irclickid"}


def is_tracking_param(name: str) -> bool:
    n = name.lower()
    return n.startswith("utm_") or n in CLICK_IDS


def tracking_params(url: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if is_tracking_param(k) and k not in out:
            out[k] = v
    return out


def url_key(url: str) -> str:
    """Comparable form of a URL: no tracking params, no fragment, lowercase
    scheme/host, default ports and trailing slash ignored."""
    s = urlsplit(url)
    host = (s.hostname or "").lower()
    if s.port and not ((s.scheme == "http" and s.port == 80) or (s.scheme == "https" and s.port == 443)):
        host += ":%d" % s.port
    query = urlencode(sorted((k, v) for k, v in parse_qsl(s.query, keep_blank_values=True) if not is_tracking_param(k)))
    path = s.path.rstrip("/") or "/"
    return urlunsplit((s.scheme.lower(), host, path, query, ""))


def _short(url: str, n: int = 90) -> str:
    return url if len(url) <= n else url[: n - 3] + "..."


def _n(count: int, word: str) -> str:
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def _check(name: str, points, status: str, summary: str, fixes=None, **details) -> dict:
    d = {"points": None if points is None else round(float(points), 1), "max": MAX_POINTS[name],
         "status": status, "summary": summary, "fixes": fixes or [], "notes": []}
    d.update(details)
    return d


def _fix(priority: str, text: str) -> dict:
    return {"priority": priority, "fix": text}


def _status(points, max_points) -> str:
    if points is None:
        return "n/a"
    if points >= max_points - 1e-9:
        return "pass"
    return "warn" if points >= max_points / 2 else "fail"


# ---------------------------------------------------------------- checks

def check_redirects(raw: dict) -> dict:
    wanted = tracking_params(raw["input_url"])
    chain = raw.get("chain") or [{"url": raw.get("final_url") or raw["input_url"], "status": raw.get("final_status"), "type": "http"}]
    hops = []
    lost_at = []
    prev_present = set(wanted)
    for i, hop in enumerate(chain):
        got = tracking_params(hop["url"])
        missing = [k for k in wanted if k not in got]
        changed = [k for k in wanted if k in got and got[k] != wanted[k]]
        dropped_here = [k for k in missing if k in prev_present]
        if dropped_here and i > 0:
            lost_at.append({"hop": i + 1, "from": chain[i - 1]["url"], "to": hop["url"], "params": dropped_here})
        prev_present = set(wanted) - set(missing)
        hops.append({"n": i + 1, "url": hop["url"], "status": hop.get("status"), "type": hop.get("type", "http"),
                     "missing": missing, "changed": changed})
    redirects = len(hops) - 1
    final = hops[-1]
    if not wanted:
        return _check("redirects", None, "n/a",
                      "%s; the URL has no UTM or click-id parameters to follow" % _n(redirects, "redirect"),
                      hops=hops, params=[], lost_at=[], redirects=redirects)
    fixes = []
    if final["missing"]:
        pts = 0.0
        for la in lost_at:
            fixes.append(_fix("high", "Hop %d drops %s (%s -> %s). Keep the query string on every redirect, "
                                      "or point the ad straight at the final URL."
                              % (la["hop"], ", ".join(la["params"]), _short(la["from"], 60), _short(la["to"], 60))))
        summary = "%s; lost on the final URL: %s" % (_n(redirects, "redirect"), ", ".join(final["missing"]))
    else:
        pts = MAX_POINTS["redirects"] - min(3, redirects)
        summary = "%s; all %s reach the final URL" % (_n(redirects, "redirect"), _n(len(wanted), "tracked parameter"))
        if final["changed"]:
            pts -= 3
            fixes.append(_fix("medium", "Parameter value(s) rewritten on the way: %s." % ", ".join(final["changed"])))
            summary += " (value changed: %s)" % ", ".join(final["changed"])
        if redirects:
            fixes.append(_fix("low", "%s before the page loads; use %s as the ad's final URL to save "
                                     "a round trip on every click." % (_n(redirects, "redirect"), _short(final["url"].split("?")[0], 70))))
    return _check("redirects", pts, _status(pts, MAX_POINTS["redirects"]), summary, fixes,
                  hops=hops, params=list(wanted), lost_at=lost_at, redirects=redirects)


_UA_SCOPE = re.compile(r"^\s*([a-z0-9_-]+)\s*:\s*(.*)$", re.I)
_NOT_SCOPES = {"unavailable_after", "max-snippet", "max-image-preview", "max-video-preview"}


def robots_directives(meta: list[dict], x_robots: list[str]) -> dict:
    """Directives that apply to Google, with where each came from."""
    found: dict[str, list[str]] = {}
    for m in meta:
        for d in (m.get("content") or "").split(","):
            d = d.strip().lower()
            if d:
                found.setdefault(d.split(":")[0].strip(), []).append("meta " + m.get("name", "robots"))
    for value in x_robots:
        scope = None
        m = _UA_SCOPE.match(value)
        if m and m.group(1).lower() not in _NOT_SCOPES and m.group(1).lower() not in ("noindex", "none", "all", "index"):
            scope, value = m.group(1).lower(), m.group(2)
        if scope not in (None, "googlebot"):
            continue
        for d in value.split(","):
            d = d.strip().lower()
            if d:
                found.setdefault(d.split(":")[0].strip(), []).append("X-Robots-Tag")
    return found


def _link_canonicals(link_headers: list[str]) -> list[str]:
    out = []
    for h in link_headers:
        for part in h.split(","):
            m = re.search(r"<([^>]+)>\s*;.*rel\s*=\s*\"?canonical", part, re.I)
            if m:
                out.append(m.group(1).strip())
    return out


def check_indexability(raw: dict) -> dict:
    dom = raw.get("dom") or {}
    final_url = raw.get("final_url") or raw["input_url"]
    status = raw.get("final_status")
    directives = robots_directives(dom.get("meta_robots", []), raw.get("x_robots_tag", []))
    noindex_src = directives.get("noindex", []) + directives.get("none", [])
    canon = [c for c in dom.get("canonicals", []) if c] + _link_canonicals(raw.get("link_headers", []))
    distinct = sorted(set(canon))
    fixes, notes = [], []
    pts = MAX_POINTS["indexability"]
    canonical = distinct[0] if distinct else None
    canonical_self = canonical is not None and url_key(canonical) == url_key(final_url)

    if status is None or status >= 400:
        state = "not indexable (HTTP %s)" % status
        pts = 0.0
        fixes.append(_fix("high", "The landing page answers HTTP %s." % status))
    elif noindex_src:
        state = "noindex (%s)" % ", ".join(sorted(set(noindex_src)))
        notes.append("Intentional for many ad-only pages: Google Ads does not need the page indexed. "
                     "Remove noindex only if it should also rank in organic search.")
    elif canonical and not canonical_self:
        state = "indexable, canonical points to another URL (%s)" % _short(canonical, 70)
        notes.append("Fine for an ad variant of an organic page; that URL is the one that ranks.")
    else:
        state = "indexable" + (", self-canonical" if canonical_self else ", no canonical")

    if status is not None and status < 400:
        if len(distinct) > 1:
            pts -= 2
            fixes.append(_fix("medium", "%d different canonical URLs; Google may ignore all of them. Keep one." % len(distinct)))
        if noindex_src and canonical and not canonical_self:
            pts -= 2
            fixes.append(_fix("medium", "Mixed signals: noindex plus a canonical pointing to another URL. Pick one."))
        if canonical and tracking_params(canonical):
            pts -= 2
            fixes.append(_fix("medium", "The canonical URL carries tracking parameters (%s); strip them."
                              % ", ".join(tracking_params(canonical))))
        if not canonical and not noindex_src:
            pts -= 1
            fixes.append(_fix("low", "No canonical. A self-referencing canonical folds the many ?gclid=... "
                                     "variants of this URL into one."))
    pts = max(0.0, pts)
    return _check("indexability", pts, _status(pts, MAX_POINTS["indexability"]), state, fixes,
                  noindex=bool(noindex_src), directives=sorted(directives), canonical=canonical,
                  canonical_is_self=canonical_self, canonicals=distinct, notes=notes)


def split_keywords(keywords) -> list[str]:
    if not keywords:
        return []
    if isinstance(keywords, str):
        keywords = [keywords]
    out = []
    for k in keywords:
        out.extend(p.strip() for p in k.split(",") if p.strip())
    return out


def check_message(raw: dict, keywords=None, headline: str | None = None) -> dict:
    dom = raw.get("dom") or {}
    title, h1, atf = dom.get("title", ""), " | ".join(dom.get("h1", [])), dom.get("atf_text", "")
    kws = split_keywords(keywords)
    regions = {"title": title, "h1": h1, "atf": atf}
    kw_hits = [dict(keyword=k, **{r: contains_phrase(t, k) for r, t in regions.items()}) for k in kws]
    head = None
    if headline:
        cov = {r: round(coverage(t, headline), 2) for r, t in regions.items()}
        head = {"headline": headline, "coverage": cov, "exact_in_h1": contains_phrase(h1, headline),
                "best": max(cov["h1"], cov["atf"])}
    details = {"title": title, "h1": dom.get("h1", []), "keywords": kw_hits, "headline": head}
    if not kws and not headline:
        return _check("message", None, "n/a", "pass --keywords and/or --headline to check message match", **details)

    max_pts = MAX_POINTS["message"]
    kw_max = max_pts if not headline else (0 if not kws else 12)
    pts = keyword_points(kw_hits, kw_max) if kws else 0.0
    if headline:
        pts += headline_points(1.0 if head["exact_in_h1"] else head["best"], max_pts - kw_max)
    fixes, parts = [], []
    for h in kw_hits:
        where = [r for r in ("title", "h1", "atf") if h[r]]
        parts.append("'%s' in %s" % (h["keyword"], "/".join(where) if where else "nothing"))
        if not where:
            fixes.append(_fix("high", "Keyword '%s' is not in the title, the h1 or the first screen." % h["keyword"]))
        else:
            if not h["h1"]:
                fixes.append(_fix("medium", "Put '%s' in the h1." % h["keyword"]))
            if not h["title"]:
                fixes.append(_fix("low", "Add '%s' to the <title>." % h["keyword"]))
    if head:
        best = 1.0 if head["exact_in_h1"] else head["best"]
        parts.append("headline %d%% matched" % round(100 * best))
        if best < 0.5:
            fixes.append(_fix("high", "Ad headline '%s' is barely echoed on the first screen (%d%% of its words). "
                                      "Repeat the ad's promise in the h1." % (headline, round(100 * best))))
        elif best < 0.8:
            fixes.append(_fix("medium", "Only %d%% of the ad headline's words appear in the h1 or first screen."
                              % round(100 * best)))
    return _check("message", pts, _status(pts, max_pts), "; ".join(parts), fixes, **details)


def check_cta(raw: dict) -> dict:
    dom = raw.get("dom") or {}
    vp = dom.get("viewport") or {}
    ctas = dom.get("ctas", [])
    clear = [c for c in ctas if not c.get("covered_by")]
    size = "%sx%s" % (vp.get("w", "?"), vp.get("h", "?"))
    if clear:
        c = clear[0]
        pts = MAX_POINTS["cta"]
        summary = "%s '%s' at y=%s in the first %s screen" % (c["kind"], c["text"], c["box"]["y"], size)
        if len(clear) > 1:
            summary += " (+%d more)" % (len(clear) - 1)
        fixes = []
    elif ctas:
        c = ctas[0]
        pts = 7.0
        summary = "%s '%s' is in the first screen but covered by %s" % (c["kind"], c["text"], c["covered_by"])
        fixes = [_fix("medium", "The first-screen CTA is covered by %s on load; keep the banner from hiding it." % c["covered_by"])]
    else:
        pts = 0.0
        summary = "no button, CTA link, tel: link or form visible in the first %s screen" % size
        fixes = [_fix("high", "Nothing to tap in the first %s screen. Move the main call to action above the fold." % size)]
    return _check("cta", pts, _status(pts, MAX_POINTS["cta"]), summary, fixes, ctas=ctas[:10])


def _mb(n: int | None) -> str:
    return "?" if n is None else "%.2f MB" % (n / 1e6)


def _secs(ms: float) -> str:
    return "%d ms" % ms if ms < 1000 else "%.1f s" % (ms / 1000)


def check_speed(raw: dict) -> dict:
    perf = raw.get("perf") or {}
    lcp, size, reqs = perf.get("lcp_ms"), perf.get("bytes"), perf.get("requests")
    lp = lcp_points(lcp)
    pts = (lp if lp is not None else 5.0) + weight_points(size, reqs)
    fixes = []
    el = perf.get("lcp_element") or "?"
    if lcp is None:
        fixes.append(_fix("low", "No LCP entry was recorded; check the page renders visible content without interaction."))
    elif lcp > 4000:
        fixes.append(_fix("high", "LCP %.1f s on mobile (element %s). Aim for 2.5 s: compress and preload the hero, "
                                  "cut render-blocking CSS/JS." % (lcp / 1000, el)))
    elif lcp > 2500:
        fixes.append(_fix("medium", "LCP %.1f s on mobile (element %s); 2.5 s or less is 'good'." % (lcp / 1000, el)))
    if size is not None and size > 3e6:
        fixes.append(_fix("medium", "%s transferred on first load; mobile ad clicks pay for every byte." % _mb(size)))
    elif size is not None and size > 1.5e6:
        fixes.append(_fix("low", "%s transferred on first load." % _mb(size)))
    if reqs is not None and reqs > 100:
        fixes.append(_fix("low", "%d requests on load." % reqs))
    lcp_txt = "LCP ?" if lcp is None else "LCP %s (%s)" % (_secs(lcp), el)
    summary = "%s, %s transferred, %s requests" % (lcp_txt, _mb(size), reqs)
    prof = raw.get("profile") or {}
    notes = [] if prof.get("throttled") else ["Measured without network or CPU throttling; use --throttle for slow-4G numbers."]
    return _check("speed", pts, _status(pts, MAX_POINTS["speed"]), summary, fixes,
                  lcp_ms=lcp, lcp_element=perf.get("lcp_element"), lcp_url=perf.get("lcp_url"),
                  bytes=size, requests=reqs, nav=perf.get("nav"), notes=notes)


def check_tap_targets(raw: dict) -> dict:
    tap = (raw.get("dom") or {}).get("tap") or {}
    total, small, crowded = tap.get("total", 0), tap.get("small", 0), tap.get("crowded", 0)
    pts = tap_points(total, small, crowded)
    fixes = []
    ex = tap.get("examples", [])
    eg = ""
    if ex:
        e = ex[0]
        eg = " (e.g. %s '%s' %dx%d)" % (e["element"].split(".")[0].split("#")[0], e["text"][:30], e["w"], e["h"])
    if total and crowded / total > 0.25:
        fixes.append(_fix("medium", "%d of %d tap targets are under 48x48 px and crowded by a neighbour%s." % (crowded, total, eg)))
    elif crowded:
        fixes.append(_fix("low", "%d of %d tap targets are under 48x48 px and crowded by a neighbour%s." % (crowded, total, eg)))
    elif small:
        fixes.append(_fix("low", "%s under 48x48 px, none crowded%s." % (_n(small, "tap target"), eg)))
    summary = "%s: %d under 48x48 px, %d of those too close to another" % (_n(total, "target"), small, crowded)
    if tap.get("inline_links_skipped"):
        summary += "; %d inline text link(s) not counted" % tap["inline_links_skipped"]
    return _check("tap_targets", pts, _status(pts, MAX_POINTS["tap_targets"]), summary, fixes, **tap)


_PHONE_NANP = re.compile(r"(?<![\w+])(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")
_PHONE_INTL = re.compile(r"(?<![\w+])\+\d[\d\s().-]{6,18}\d(?!\d)")


def find_phone_numbers(text: str | None) -> list[str]:
    out, seen = [], set()
    for rx in (_PHONE_NANP, _PHONE_INTL):
        for m in rx.finditer(text or ""):
            digits = re.sub(r"\D", "", m.group(0))
            if not 10 <= len(digits) <= 15:
                continue
            key = digits[-10:]
            if key not in seen:
                seen.add(key)
                out.append(m.group(0).strip())
    return out


def check_phone(raw: dict) -> dict:
    dom = raw.get("dom") or {}
    numbers = find_phone_numbers(dom.get("body_text"))
    tel = dom.get("tel_links", [])
    tel_digits = {re.sub(r"\D", "", t["href"])[-10:] for t in tel}
    phones = [{"number": n, "click_to_call": re.sub(r"\D", "", n)[-10:] in tel_digits} for n in numbers]
    plain = [p["number"] for p in phones if not p["click_to_call"]]
    visible_tel = [t for t in tel if t.get("visible")]
    fixes = []
    if plain:
        pts = 1.0
        fixes.append(_fix("medium", "Phone number %s is plain text; make it a tel: link so a tap starts the call." % plain[0]))
        summary = "%d visible number(s), %d not click-to-call" % (len(phones), len(plain))
    elif phones or visible_tel:
        pts = 5.0
        summary = "%d visible number(s), %d tel: link(s)" % (len(phones), len(visible_tel))
        if any(t.get("above_fold") for t in visible_tel):
            summary += ", one in the first screen"
    else:
        pts = 2.0
        summary = "no visible phone number or tel: link"
        fixes.append(_fix("low", "No phone number. For local services a tap-to-call link often converts better than a form."))
    return _check("phone", pts, _status(pts, MAX_POINTS["phone"]), summary, fixes, phones=phones, tel_links=tel)


def check_form(raw: dict) -> dict:
    forms = (raw.get("dom") or {}).get("forms", [])
    if not forms:
        return _check("form", None, "n/a", "no visible form", forms=[])
    main = max(forms, key=lambda f: f["fields"])
    pts = form_points(main["fields"])
    fixes = []
    if main["fields"] > 8:
        fixes.append(_fix("medium", "The form asks for %d fields (%d required). Cut it to what you need for a first contact."
                          % (main["fields"], main["required"])))
    elif main["fields"] > 5:
        fixes.append(_fix("low", "The form has %d fields; 5 or fewer usually convert better on mobile." % main["fields"]))
    summary = "%d form(s); largest has %d visible field(s), %d required" % (len(forms), main["fields"], main["required"])
    if main.get("above_fold"):
        summary += ", starts in the first screen"
    return _check("form", pts, _status(pts, MAX_POINTS["form"]), summary, fixes, forms=forms)


def _walk_jsonld(node, types: set, flags: dict):
    if isinstance(node, list):
        for n in node:
            _walk_jsonld(n, types, flags)
    elif isinstance(node, dict):
        t = node.get("@type")
        for x in (t if isinstance(t, list) else [t]):
            if isinstance(x, str):
                types.add(x)
        if node.get("address") or "PostalAddress" in types:
            flags["address"] = True
        if "aggregateRating" in node or "review" in node:
            flags["reviews"] = True
        for v in node.values():
            if isinstance(v, (dict, list)):
                _walk_jsonld(v, types, flags)


def schema_signals(jsonld: list[str], microdata: list[str]) -> dict:
    types: set = set()
    flags = {"address": False, "reviews": False}
    errors = 0
    for block in jsonld:
        try:
            _walk_jsonld(json.loads(block), types, flags)
        except (ValueError, TypeError):
            errors += 1
    for it in microdata:
        types.add((it or "").rstrip("/").rsplit("/", 1)[-1])
    if "PostalAddress" in types:
        flags["address"] = True
    if types & {"AggregateRating", "Review"}:
        flags["reviews"] = True
    return {"types": sorted(t for t in types if t), "address": flags["address"], "reviews": flags["reviews"],
            "invalid_jsonld": errors}


_POSTAL_CA = re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[A-Z][ -]?\d[A-Z]\d\b")
_ZIP_US = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_STREET = re.compile(r"\b\d{1,5}(?:\s+[A-Za-z][\w'-]*){0,4}\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|"
                     r"Lane|Ln|Way|Court|Ct|Place|Pl|Crescent|Cres|Highway|Hwy)\b\.?|\b\d{1,5},?\s+(?:rue|chemin|boul|"
                     r"boulevard|avenue|route|rang|place)\b", re.I)


def text_has_address(text: str | None) -> bool:
    text = text or ""
    return bool(_POSTAL_CA.search(text) or _ZIP_US.search(text) or _STREET.search(text))


def check_trust(raw: dict) -> dict:
    dom = raw.get("dom") or {}
    schema = schema_signals(dom.get("jsonld", []), dom.get("microdata", []))
    addr_text = text_has_address(dom.get("body_text")) or bool(dom.get("address_elements"))
    privacy = dom.get("privacy_links", [])
    has = {"address": addr_text or schema["address"], "reviews": schema["reviews"], "privacy": bool(privacy)}
    pts = 2.0 * has["address"] + 1.5 * has["reviews"] + 1.5 * has["privacy"]
    fixes = []
    if not has["privacy"]:
        fixes.append(_fix("medium", "No privacy policy link. Ad platforms and privacy law expect one wherever you collect data."))
    if not has["address"]:
        fixes.append(_fix("low", "No postal address (text or schema.org PostalAddress); a real address builds trust for local services."))
    if not has["reviews"]:
        fixes.append(_fix("low", "No review or AggregateRating markup found."))
    bits = []
    bits.append("address: " + ("schema.org" if schema["address"] else "text" if addr_text else "no"))
    bits.append("reviews schema: " + ("yes" if has["reviews"] else "no"))
    bits.append("privacy link: " + ("yes" if privacy else "no"))
    return _check("trust", pts, _status(pts, MAX_POINTS["trust"]), ", ".join(bits), fixes,
                  schema=schema, address_text=addr_text, privacy_links=privacy)


# name, category, host suffixes, path prefixes (None = any path)
TRACKERS = [
    ("Google Analytics", "analytics", ("google-analytics.com", "analytics.google.com"), None),
    ("Google Tag Manager", "tag manager", ("googletagmanager.com",), None),
    ("Google Ads", "ads conversion", ("googleadservices.com", "doubleclick.net", "googlesyndication.com"), None),
    ("Meta Pixel", "ads conversion", ("connect.facebook.net",), None),
    ("Meta Pixel", "ads conversion", ("facebook.com",), ("/tr",)),
    ("Microsoft Ads UET", "ads conversion", ("bat.bing.com",), None),
    ("Microsoft Clarity", "session recording", ("clarity.ms",), None),
    ("LinkedIn Insight", "ads conversion", ("snap.licdn.com", "px.ads.linkedin.com"), None),
    ("TikTok Pixel", "ads conversion", ("analytics.tiktok.com",), None),
    ("X Pixel", "ads conversion", ("static.ads-twitter.com", "analytics.twitter.com", "ads-api.twitter.com"), None),
    ("Pinterest Tag", "ads conversion", ("ct.pinterest.com",), None),
    ("Reddit Pixel", "ads conversion", ("alb.reddit.com", "pixel-config.reddit.com"), None),
    ("Snap Pixel", "ads conversion", ("tr.snapchat.com", "sc-static.net"), None),
    ("Quora Pixel", "ads conversion", ("q.quora.com",), None),
    ("Hotjar", "session recording", ("hotjar.com", "hotjar.io"), None),
    ("Yandex Metrica", "analytics", ("mc.yandex.ru", "mc.yandex.com"), None),
    ("HubSpot", "analytics", ("hs-analytics.net", "track.hubspot.com", "hs-scripts.com"), None),
    ("Segment", "analytics", ("cdn.segment.com", "api.segment.io"), None),
    ("Mixpanel", "analytics", ("mixpanel.com", "mxpnl.com"), None),
    ("Amplitude", "analytics", ("amplitude.com",), None),
    ("Heap", "analytics", ("heapanalytics.com",), None),
    ("FullStory", "session recording", ("fullstory.com",), None),
]
_GOOGLE_HOST = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")


def classify_request(url: str, extra_hosts=()) -> tuple[str, str] | None:
    """(vendor, category) for a known tracking/conversion request, else None."""
    s = urlsplit(url)
    host = (s.hostname or "").lower()
    hostport = host + (":%d" % s.port if s.port else "")
    for pat in extra_hosts or ():
        p = pat.lower().strip()
        if p and (hostport == p or host == p or host.endswith("." + p)):
            return ("Custom (%s)" % pat, "custom")
    for name, cat, hosts, paths in TRACKERS:
        if any(host == h or host.endswith("." + h) for h in hosts):
            if paths is None or any(s.path.startswith(p) for p in paths):
                return (name, cat)
    if _GOOGLE_HOST.search(host) and s.path.startswith(("/pagead/", "/ads/", "/ccm/")):
        return ("Google Ads", "ads conversion")
    return None


def google_consent_state(url: str) -> str | None:
    """Google Consent Mode 'gcs' value: G1<ad_storage><analytics_storage>,
    e.g. G100 = both denied, G111 = both granted."""
    v = parse_qs(urlsplit(url).query).get("gcs")
    return v[0] if v else None


def check_consent(raw: dict, extra_hosts=()) -> dict:
    dom = raw.get("dom") or {}
    banner = dom.get("consent_banner") or {"visible": False}
    found: dict[str, dict] = {}
    hits, unconsented = 0, 0
    for r in raw.get("requests", []):
        c = classify_request(r["url"], extra_hosts)
        if not c:
            continue
        kind = "script" if r.get("type") == "script" else "hit"
        gcs = google_consent_state(r["url"])
        v = found.setdefault(c[0], {"vendor": c[0], "category": c[1], "scripts": 0, "hits": 0,
                                    "consent_mode": set(), "first_ms": r.get("t_ms"), "example": _short(r["url"], 110)})
        v["scripts" if kind == "script" else "hits"] += 1
        if gcs:
            v["consent_mode"].add(gcs)
        if kind == "hit":
            hits += 1
            if gcs != "G100":
                unconsented += 1
    trackers = []
    for v in found.values():
        v["consent_mode"] = sorted(v["consent_mode"])
        trackers.append(v)
    names = ", ".join(t["vendor"] for t in trackers)
    fixes, notes = [], []
    if unconsented and not banner.get("visible"):
        pts = 0.0
        summary = "%d tracking hit(s) before any interaction (%s), no consent banner visible" % (unconsented, names)
        fixes.append(_fix("high", "Tracking fires on load (%s) and no consent banner is shown. Load these tags only "
                                  "after consent, or run Google Consent Mode with everything denied by default." % names))
    elif unconsented:
        pts = 2.0
        summary = "%d tracking hit(s) before any consent choice (%s); consent banner visible" % (unconsented, names)
        fixes.append(_fix("medium", "A consent banner is shown, but %s already sent data before any choice was made. "
                                    "Hold the tags until consent." % names))
    elif hits:
        pts = 4.0
        summary = "only cookieless Google Consent Mode pings (gcs=G100) before interaction (%s)" % names
        notes.append("Consent Mode is in 'denied' state on load; pings without cookies are still sent.")
    else:
        pts = 5.0
        summary = ("no tracking data sent before interaction" +
                   ("; tag script(s) loaded: %s" % names if trackers else ""))
    summary += "" if not banner.get("visible") or "banner" in summary else "; consent banner visible"
    if not any(t["category"] == "ads conversion" for t in trackers):
        notes.append("No ads conversion tag was seen before interaction; if you track conversions it may load after "
                     "consent (not verifiable without clicking).")
    return _check("consent", pts, _status(pts, MAX_POINTS["consent"]), summary, fixes,
                  trackers=trackers, banner=banner, notes=notes)


# ---------------------------------------------------------------- all

def analyze(raw: dict, keywords=None, headline: str | None = None, tracker_hosts=None) -> dict:
    result = {
        "tool": "landing-page-check", "version": __version__, "url": raw["input_url"],
        "final_url": raw.get("final_url"), "final_status": raw.get("final_status"),
        "profile": raw.get("profile"), "error": raw.get("error"), "score": None, "fixes": [], "checks": {},
    }
    if raw.get("error") or not raw.get("dom"):
        result["error"] = raw.get("error") or "page did not load"
        return result
    checks = {
        "redirects": check_redirects(raw),
        "indexability": check_indexability(raw),
        "message": check_message(raw, keywords, headline),
        "cta": check_cta(raw),
        "speed": check_speed(raw),
        "tap_targets": check_tap_targets(raw),
        "phone": check_phone(raw),
        "form": check_form(raw),
        "trust": check_trust(raw),
        "consent": check_consent(raw, tracker_hosts or ()),
    }
    result["score"], result["fixes"] = overall(checks)
    result["checks"] = checks
    return result
