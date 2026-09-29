# landing-page-check

Check an ads landing page **the way paid traffic sees it**: headless Chromium, mobile viewport and mobile user agent, first visit, nothing clicked.

```
python -m landing_page_check "https://www.example.com/offer?utm_source=google&utm_medium=cpc&gclid=TEST" \
    --keywords "roof repair, roofer" --headline "Fast Roof Repair in Exampleville"
```

It answers the questions that cost ad money when they go wrong, and prints a score (0-100) with fixes ranked high / medium / low:

- **Redirect chain.** Every UTM parameter and click id (`gclid`, `fbclid`, `msclkid`, ...) is followed through each hop. The report names the hop that dropped it.
- **Indexability.** Meta robots, `X-Robots-Tag` and canonical. The report says whether the page is indexable or intentionally noindex. Neither is wrong for an ad page; conflicting signals are.
- **Message match.** The `--keywords` and the ad `--headline` are looked up in the title, the h1 and the first screen. Case- and accent-insensitive (`creation` matches `Cr&eacute;ation`), simple plurals folded.
- **Call to action above the fold.** A button, CTA link, `tel:` link or form visible in the first 412x915 screen, checked with bounding boxes, computed visibility, clipping, and whether something (a cookie banner) covers it.
- **Mobile speed.** LCP from a buffered `PerformanceObserver`, bytes transferred (Chrome DevTools protocol) and request count. `--throttle` adds slow 4G and a 4x slower CPU.
- **Tap targets** smaller than 48x48 CSS px, and which of those sit too close to another target. Links inside running text are skipped.
- **Phone number.** A visible number, and whether it is a `tel:` link.
- **Form length.** Visible fields and required fields (a radio group counts once; hidden honeypots are ignored).
- **Trust signals.** Postal address (text or schema.org `PostalAddress`), review / `AggregateRating` markup, privacy policy link.
- **Consent and tracking.** Google Analytics, Tag Manager, Google Ads / DoubleClick, Meta, Microsoft UET and Clarity, LinkedIn, TikTok and a dozen more, **fired before any interaction**, and whether a consent banner is visible. Google Consent Mode state (`gcs=G100`) is read from the hits.

## Measured result

My own site, [demarkstudio.ca](https://demarkstudio.ca), one page load each, with an ad-style URL for the English page:

```
$ python -m landing_page_check "https://demarkstudio.ca/en/website?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST" --keywords "website design" --headline "Website Design for Small Businesses" --fail-under 70
# Landing page check

- URL: https://demarkstudio.ca/en/website?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST
- Final URL: https://demarkstudio.ca/en/website?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST (HTTP 200)
- Profile: mobile 412x915, Chromium 151.0.7922.34, unthrottled
- **Score: 78/100**

## Fixes

1. **high** Message match: Keyword 'website design' is not in the title, the h1 or the first screen.
2. **medium** Message match: Only 75% of the ad headline's words appear in the h1 or first screen.
3. **low** Tap targets: 11 tap targets under 48x48 px, none crowded (e.g. a 'De Mark' 96x30).
4. **low** Phone number: No phone number. For local services a tap-to-call link often converts better than a form.
5. **low** Trust signals: No review or AggregateRating markup found.

## Checks

| Check | Points | Result |
|---|---|---|
| Redirect chain | 15/15 | 0 redirects; all 4 tracked parameters reach the final URL |
| Indexability | 5/5 | indexable, self-canonical |
| Message match | 6/20 | 'website design' in nothing; headline 75% matched |
| Above-the-fold CTA | 15/15 | link 'START YOUR FREE TRIAL' at y=449 in the first 412x915 screen (+2 more) |
| Mobile speed | 15/15 | LCP 396 ms (h1#titulo-at-apertura), 0.35 MB transferred, 20 requests |
| Tap targets | 7.2/10 | 20 targets: 11 under 48x48 px, 0 of those too close to another |
| Phone number | 2/5 | no visible phone number or tel: link |
| Form length | n/a | no visible form |
| Trust signals | 3.5/5 | address: schema.org, reviews schema: no, privacy link: yes |
| Consent and tracking | 5/5 | no tracking data sent before interaction |

## Redirect chain

Tracked: utm_source, utm_medium, utm_campaign, gclid

1. 200 https://demarkstudio.ca/en/website?utm_source=google&utm_medium=cpc&utm_campaign=test&gclid=TEST  all kept

## Message match

| Phrase | Title | H1 | First screen |
|---|---|---|---|
| website design | no | no | no |
| headline: Website Design for Small Businesses | 25% | 25% | 75% |

Title: A professional website for your business, included - DeMark
H1: A professional website for your business, included

## Tracking before any interaction

- none
- consent banner: not visible

## Notes

- Mobile speed: Measured without network or CPU throttling; use --throttle for slow-4G numbers.
- Consent and tracking: No ads conversion tag was seen before interaction; if you track conversions it may load after consent (not verifiable without clicking).
$ echo $?
0

$ python -m landing_page_check "https://demarkstudio.ca/fr/site-web" --keywords "site web, creation de site web" --headline "Creation de site web pour PME"
# Landing page check

- URL: https://demarkstudio.ca/fr/site-web
- Final URL: https://demarkstudio.ca/fr/site-web (HTTP 200)
- Profile: mobile 412x915, Chromium 151.0.7922.34, unthrottled
- **Score: 78/100**

## Fixes

1. **high** Message match: Keyword 'creation de site web' is not in the title, the h1 or the first screen.
2. **medium** Message match: Only 50% of the ad headline's words appear in the h1 or first screen.
3. **low** Tap targets: 11 tap targets under 48x48 px, none crowded (e.g. a 'De Mark' 96x30).
4. **low** Phone number: No phone number. For local services a tap-to-call link often converts better than a form.
5. **low** Trust signals: No review or AggregateRating markup found.

## Checks

| Check | Points | Result |
|---|---|---|
| Redirect chain | n/a | 0 redirects; the URL has no UTM or click-id parameters to follow |
| Indexability | 5/5 | indexable, self-canonical |
| Message match | 10/20 | 'site web' in title/h1/atf; 'creation de site web' in nothing; headline 50% matched |
| Above-the-fold CTA | 15/15 | link 'COMMENCEZ VOTRE ESSAI GRATUIT' at y=517 in the first 412x915 screen (+2 more) |
| Mobile speed | 15/15 | LCP 352 ms (h1#titulo-at-apertura), 0.35 MB transferred, 20 requests |
| Tap targets | 7.2/10 | 20 targets: 11 under 48x48 px, 0 of those too close to another |
| Phone number | 2/5 | no visible phone number or tel: link |
| Form length | n/a | no visible form |
| Trust signals | 3.5/5 | address: schema.org, reviews schema: no, privacy link: yes |
| Consent and tracking | 5/5 | no tracking data sent before interaction |

## Redirect chain

1. 200 https://demarkstudio.ca/fr/site-web

## Message match

| Phrase | Title | H1 | First screen |
|---|---|---|---|
| site web | yes | yes | yes |
| creation de site web | no | no | no |
| headline: Creation de site web pour PME | 50% | 50% | 50% |

Title: Un site Web professionnel pour votre entreprise, inclus - DeMark
H1: Un site Web professionnel pour votre entreprise, inclus

## Tracking before any interaction

- none
- consent banner: not visible

## Notes

- Mobile speed: Measured without network or CPU throttling; use --throttle for slow-4G numbers.
- Consent and tracking: No ads conversion tag was seen before interaction; if you track conversions it may load after consent (not verifiable without clicking).

$ python -m pytest -q
..................................................
50 passed in 35.14s
```

What that says about my pages, good and bad:

- **Good:** no redirect, so `gclid` and the three UTM parameters land intact; self-canonical, indexable; two CTAs ("Start your free trial", "Book a free 20-minute call") in the first screen, nothing covering them; LCP under 0.4 s and 0.35 MB in 20 requests (unthrottled, one cold load from the machine that ran the check); no tracker fires before a visitor does anything; privacy link and a schema.org address are there.
- **Bad:** the pages never say "website design" or "cr&eacute;ation de site web". They say "a professional website" / "un site Web professionnel". An ad on those keywords would promise one thing and the h1 another; that is the one high-priority fix. There is also no phone number, no review markup, and 11 targets under 48 px (the logo link is 96x30, the language and "See it live" links 44 px tall). They have room around them, so they are only low priority.
- **Not checked:** there is no conversion tag before interaction, so I cannot see from a page load whether conversions are tracked after consent. That would take a click, and the tool never clicks.

Each run is one GET navigation (plus the page's own resources), with the User-Agent `... Mobile Safari/537.36 landing-page-check/1.0 (+https://github.com/dreadmoreeee/landing-page-check)`.

## CLI

```
landing-page-check URL [URL ...] [--keywords "a, b"] [--headline TEXT] [--format markdown|json]
                   [--fail-under SCORE] [--fail-on high|medium|low] [--desktop] [--throttle]
                   [--user-agent UA] [--locale en-CA] [--tracker-host HOST] [--settle 3]
                   [--timeout 45] [--delay 2] [--screenshot first-screen.png] [-o FILE]
```

Same as `python -m landing_page_check`. Exit codes: **0** ok, **1** a score is under `--fail-under` or a fix is at or above `--fail-on`, **2** the page could not be loaded. Several URLs are checked one after the other, at least 1 s apart. [examples/github-actions.yml](examples/github-actions.yml) runs it weekly in CI; [examples/api.py](examples/api.py) uses it from Python (`from landing_page_check import check`).

## Scoring

| Check | Points | High-priority when |
|---|---|---|
| Redirect chain | 15 | a tracked parameter is missing on the final URL (-1 per redirect otherwise) |
| Message match | 20 | a keyword is in none of title / h1 / first screen, or under half the headline's words appear |
| Above-the-fold CTA | 15 | nothing to tap in the first screen (7 points if it is covered) |
| Mobile speed | 15 | LCP over 4 s (10 points for LCP <= 2.5 s, 5 up to 4 s; 5 for weight and requests) |
| Tap targets | 10 | never; medium when over 25% are small and crowded |
| Indexability | 5 | HTTP 4xx/5xx; noindex alone costs nothing |
| Phone, form, trust, consent | 5 each | trackers fire on load with no consent banner |

Checks that do not apply (no parameters in the URL, no form, no `--keywords`) are left out and the score is scaled over the rest. `--format json` gives every detail: each hop, each CTA box, each small tap target, each tracker request.

## Limitations

- One mobile profile (412x915, Pixel 7 user agent) or `--desktop` (1366x768). Chromium only.
- Speed is one cold load from where you run it, not field data. Use `--throttle` for comparable lab numbers.
- A tracker proxied through your own domain (server-side tagging) is not recognised; add hosts with `--tracker-host`.
- The consent banner is found by known CMP selectors and fixed-position text about cookies; banners inside iframes are missed.
- Phone detection knows North American numbers and `+` international numbers.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
