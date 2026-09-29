"""CLI: output formats and CI exit codes, against a local page."""

import json
import os
import socket
import subprocess
import sys

from landing_page_check.report import to_markdown

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    """Run `python -m landing_page_check` in a child process (its own
    Playwright instance) and return the exit code; stdout is echoed."""
    env = dict(os.environ, PYTHONPATH=TOOL_DIR, PYTHONUTF8="1")
    p = subprocess.run([sys.executable, "-m", "landing_page_check"] + argv, cwd=TOOL_DIR, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    sys.stdout.write(p.stdout)
    return p.returncode


PAGE = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Website design | Example Studio</title><link rel="canonical" href="/landing"></head>'
        '<body><h1>Website design for small businesses</h1><a class="btn" href="tel:+15065550100">Call 506-555-0100</a>'
        '<a href="/privacy">Privacy</a></body></html>')


def _serve(site):
    site.routes["/ad"] = lambda q: (301, {"Location": "/landing?" + q}, "")
    site.page("/landing", PAGE)
    return site.base + "/ad?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST"


def test_cli_json_and_fail_under(site, tmp_path, capsys):
    url = _serve(site)
    out = tmp_path / "r.json"
    code = main([url, "--format", "json", "--keywords", "website design", "--headline", "Website design for small businesses",
                 "--settle", "0.2", "--fail-under", "50", "-o", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0, data["fixes"]
    assert data["final_url"].endswith("/landing?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST")
    assert data["checks"]["message"]["points"] == 20
    assert data["checks"]["redirects"]["hops"][-1]["missing"] == []
    assert "landing-page-check/1.0" in data["profile"]["user_agent"] and "Mobile" in data["profile"]["user_agent"]
    md = to_markdown(data)
    assert "**Score: %d/100**" % data["score"] in md and "## Redirect chain" in md

    assert main([url, "--settle", "0", "--fail-under", "101"]) == 1
    assert main([url, "--settle", "0", "--fail-on", "low"]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("# Landing page check") and "| Redirect chain | 14/15 |" in printed


def test_cli_unreachable_exits_2(capsys):
    while True:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        if port not in (8765, 8737, 8787):
            break
    code = main(["http://127.0.0.1:%d/" % port, "--settle", "0", "--timeout", "10"])
    assert code == 2
    assert "Error" in capsys.readouterr().out
