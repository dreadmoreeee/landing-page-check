"""Markdown and JSON output."""

from __future__ import annotations

import json

from .scoring import ORDER, TITLES


def _pts(c: dict) -> str:
    if c["points"] is None:
        return "n/a"
    p = c["points"]
    return "%s/%d" % (int(p) if p == int(p) else p, c["max"])


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def to_markdown(result: dict) -> str:
    out = ["# Landing page check", ""]
    prof = result.get("profile") or {}
    vp = prof.get("viewport") or {}
    out.append("- URL: %s" % result["url"])
    if result.get("error"):
        out += ["- **Error:** %s" % result["error"], ""]
        return "\n".join(out)
    out.append("- Final URL: %s (HTTP %s)" % (result["final_url"], result["final_status"]))
    out.append("- Profile: %s %sx%s, %s, %s" % (prof.get("name"), vp.get("width"), vp.get("height"), prof.get("browser"),
                                                "throttled (slow 4G, 4x CPU)" if prof.get("throttled") else "unthrottled"))
    out.append("- **Score: %s/100**" % result["score"])
    out.append("")
    out.append("## Fixes")
    out.append("")
    if result["fixes"]:
        for i, f in enumerate(result["fixes"], 1):
            out.append("%d. **%s** %s: %s" % (i, f["priority"], f["title"], f["fix"]))
    else:
        out.append("None.")
    out += ["", "## Checks", "", "| Check | Points | Result |", "|---|---|---|"]
    checks = result["checks"]
    for name in ORDER:
        c = checks[name]
        out.append("| %s | %s | %s |" % (TITLES[name], _pts(c), _cell(c["summary"])))

    red = checks["redirects"]
    out += ["", "## Redirect chain", ""]
    if red["params"]:
        out.append("Tracked: %s" % ", ".join(red["params"]))
        out.append("")
    for h in red["hops"]:
        state = ""
        if red["params"]:
            state = "all kept" if not h["missing"] else "MISSING " + ", ".join(h["missing"])
        line = "%d. %s %s%s  %s" % (h["n"], h["status"] if h["status"] is not None else "-",
                                     "(client-side) " if h["type"] == "client" else "", h["url"], state)
        out.append(line.rstrip())

    msg = checks["message"]
    if msg["keywords"] or msg["headline"]:
        out += ["", "## Message match", "", "| Phrase | Title | H1 | First screen |", "|---|---|---|---|"]
        yn = lambda b: "yes" if b else "no"
        for k in msg["keywords"]:
            out.append("| %s | %s | %s | %s |" % (_cell(k["keyword"]), yn(k["title"]), yn(k["h1"]), yn(k["atf"])))
        if msg["headline"]:
            cv = msg["headline"]["coverage"]
            out.append("| headline: %s | %d%% | %d%% | %d%% |" % (_cell(msg["headline"]["headline"]),
                       100 * cv["title"], 100 * cv["h1"], 100 * cv["atf"]))
        out += ["", "Title: %s" % msg["title"], "H1: %s" % (" | ".join(msg["h1"]) or "(none visible)")]

    con = checks["consent"]
    out += ["", "## Tracking before any interaction", ""]
    if con["trackers"]:
        for t in con["trackers"]:
            cm = " consent mode %s" % "/".join(t["consent_mode"]) if t["consent_mode"] else ""
            out.append("- %s (%s): %d script(s), %d hit(s)%s" % (t["vendor"], t["category"], t["scripts"], t["hits"], cm))
    else:
        out.append("- none")
    b = con["banner"]
    out.append("- consent banner: %s" % (("visible, " + b.get("element", "")) if b.get("visible") else "not visible"))

    notes = [(TITLES[n], x) for n in ORDER for x in checks[n].get("notes", [])]
    if notes:
        out += ["", "## Notes", ""]
        out += ["- %s: %s" % n for n in notes]
    out.append("")
    return "\n".join(out)


def to_json(result) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False, default=list)
