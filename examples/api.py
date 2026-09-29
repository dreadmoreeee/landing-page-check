"""Use landing-page-check from Python and act on the result."""

from landing_page_check import check

result = check(
    "https://www.example.com/offer?utm_source=google&utm_medium=cpc&utm_campaign=spring&gclid=TEST",
    keywords=["roof repair", "roofer"],
    headline="Fast Roof Repair in Exampleville",
    profile="mobile",   # or "desktop"
    throttle=False,     # True = slow 4G + 4x CPU
)

print(result["score"])
for fix in result["fixes"]:
    print(fix["priority"], fix["title"], fix["fix"])

lost = result["checks"]["redirects"]["lost_at"]
if lost:
    print("parameters lost at hop", lost[0]["hop"], lost[0]["params"])
