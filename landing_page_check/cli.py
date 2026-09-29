"""Command line: landing-page-check URL [URL ...] [options]

Exit codes: 0 ok, 1 a page scored under --fail-under or has a fix at or
above --fail-on, 2 a page could not be loaded (or bad arguments)."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .analysis import analyze
from .collect import collect
from .report import to_json, to_markdown
from .scoring import PRIORITY_RANK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="landing-page-check",
                                description="Check an ads landing page the way paid mobile traffic sees it.")
    p.add_argument("urls", nargs="+", metavar="URL", help="landing page URL, ideally with the ad's UTM and click-id parameters")
    p.add_argument("--keywords", action="append", help="comma-separated ad keywords (repeatable)")
    p.add_argument("--headline", help="ad headline to look for in the h1 and first screen")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.add_argument("--fail-under", type=int, metavar="SCORE", help="exit 1 if a score is below SCORE")
    p.add_argument("--fail-on", choices=["high", "medium", "low"], help="exit 1 if a fix of this priority or higher exists")
    p.add_argument("--desktop", action="store_true", help="use a 1366x768 desktop profile instead of mobile")
    p.add_argument("--throttle", action="store_true", help="emulate slow 4G and a 4x slower CPU")
    p.add_argument("--user-agent", help="full User-Agent string (default: mobile Chrome + landing-page-check token)")
    p.add_argument("--locale", default="en-CA", help="browser locale / Accept-Language (default en-CA)")
    p.add_argument("--tracker-host", action="append", default=[], metavar="HOST",
                   help="extra host to count as a tracker (repeatable)")
    p.add_argument("--settle", type=float, default=3.0, help="seconds to wait after load for late tags (default 3)")
    p.add_argument("--timeout", type=float, default=45.0, help="navigation timeout in seconds (default 45)")
    p.add_argument("--delay", type=float, default=2.0, help="pause between URLs in seconds (default 2, minimum 1)")
    p.add_argument("--screenshot", metavar="PNG", help="save the first screen (single URL only)")
    p.add_argument("-o", "--output", help="write the report to this file instead of stdout")
    p.add_argument("--version", action="version", version="landing-page-check " + __version__)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return 2

    results = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            print("could not start Chromium (%s); run: python -m playwright install chromium" % str(e).splitlines()[0],
                  file=sys.stderr)
            return 2
        try:
            for i, url in enumerate(args.urls):
                if i:
                    time.sleep(max(1.0, args.delay))
                raw = collect(url, browser=browser, profile="desktop" if args.desktop else "mobile",
                              user_agent=args.user_agent, locale=args.locale, settle=args.settle,
                              timeout=args.timeout, throttle=args.throttle,
                              screenshot=args.screenshot if len(args.urls) == 1 else None)
                results.append(analyze(raw, keywords=args.keywords, headline=args.headline,
                                       tracker_hosts=args.tracker_host))
        finally:
            browser.close()

    if args.format == "json":
        text = to_json(results[0] if len(results) == 1 else results) + "\n"
    else:
        text = "\n".join(to_markdown(r) for r in results)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)

    if any(r.get("error") for r in results):
        return 2
    code = 0
    for r in results:
        if args.fail_under is not None and r["score"] < args.fail_under:
            code = 1
        if args.fail_on and any(PRIORITY_RANK[f["priority"]] <= PRIORITY_RANK[args.fail_on] for f in r["fixes"]):
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
