"""Check an ads landing page the way paid mobile traffic sees it."""

__version__ = "1.0.0"


def check(url: str, keywords=None, headline: str | None = None, tracker_hosts=None, **collect_options) -> dict:
    """Load `url` in headless Chromium (mobile profile by default) and return
    the full result: score, prioritized fixes and every check."""
    from .analysis import analyze
    from .collect import collect

    raw = collect(url, **collect_options)
    return analyze(raw, keywords=keywords, headline=headline, tracker_hosts=tracker_hosts)


__all__ = ["check", "__version__"]
