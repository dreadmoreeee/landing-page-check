"""Pure scoring rules. No I/O, no browser: every function here takes plain
numbers or check dicts, so the rules are easy to test and to read."""

from __future__ import annotations

ORDER = ["redirects", "indexability", "message", "cta", "speed", "tap_targets", "phone", "form", "trust", "consent"]

MAX_POINTS = {
    "redirects": 15, "indexability": 5, "message": 20, "cta": 15, "speed": 15,
    "tap_targets": 10, "phone": 5, "form": 5, "trust": 5, "consent": 5,
}

TITLES = {
    "redirects": "Redirect chain", "indexability": "Indexability", "message": "Message match",
    "cta": "Above-the-fold CTA", "speed": "Mobile speed", "tap_targets": "Tap targets",
    "phone": "Phone number", "form": "Form length", "trust": "Trust signals", "consent": "Consent and tracking",
}

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def lcp_points(lcp_ms: float | None, max_points: float = 10) -> float | None:
    """Google's thresholds: good <= 2.5 s, poor > 4 s."""
    if lcp_ms is None:
        return None
    if lcp_ms <= 2500:
        return max_points
    if lcp_ms <= 4000:
        return max_points / 2
    return 0.0


def weight_points(transferred_bytes: int | None, requests: int | None) -> float:
    """Up to 5 points: 3 for page weight, 2 for request count."""
    pts = 0.0
    if transferred_bytes is None:
        pts += 1.5
    elif transferred_bytes <= 1.5e6:
        pts += 3
    elif transferred_bytes <= 3e6:
        pts += 2
    elif transferred_bytes <= 5e6:
        pts += 1
    if requests is None or requests <= 50:
        pts += 2
    elif requests <= 100:
        pts += 1
    return pts


def tap_points(total: int, small: int, crowded: int, max_points: float = 10) -> float:
    """Crowded targets (small AND overlapping a neighbour's 48x48 zone) cost
    four times more than targets that are only small."""
    if total <= 0:
        return max_points
    penalty = 20 * (crowded / total) + 5 * (small / total)
    return round(max(0.0, max_points - penalty), 1)


def form_points(fields: int | None) -> float | None:
    if fields is None:
        return None
    if fields <= 5:
        return 5.0
    if fields <= 8:
        return 3.0
    return 1.0


def headline_points(coverage: float, max_points: float) -> float:
    return round(max_points * max(0.0, min(1.0, coverage)), 1)


def keyword_points(hits: list[dict], max_points: float) -> float:
    """hits: [{"title": bool, "h1": bool, "atf": bool}, ...]."""
    if not hits:
        return 0.0
    each = [0.3 * h["title"] + 0.4 * h["h1"] + 0.3 * h["atf"] for h in hits]
    return round(max_points * sum(each) / len(each), 1)


def overall(checks: dict) -> tuple[int, list[dict]]:
    """Score 0-100 over the checks that apply, plus fixes sorted high ->
    low (and in check order within one priority)."""
    earned = possible = 0.0
    fixes = []
    for name in ORDER:
        c = checks.get(name)
        if not c:
            continue
        if c.get("points") is not None:
            earned += c["points"]
            possible += c["max"]
        for f in c.get("fixes", []):
            fixes.append({"priority": f["priority"], "check": name, "title": TITLES[name], "fix": f["fix"]})
    fixes.sort(key=lambda f: (PRIORITY_RANK[f["priority"]], ORDER.index(f["check"])))
    score = int(round(100 * earned / possible)) if possible else 0
    return score, fixes
