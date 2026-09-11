"""
Regenerate website/supported-sites.html and adult_sites.json from the installed yt-dlp.

    .venv/bin/python tools/build_supported_sites.py

Run it after every yt-dlp upgrade: the A to Z list and the adult filter are both
tied to the extractor set of the version the bot runs. Review the diff before
committing: a site that drops out of the list usually means yt-dlp marked its
extractor broken.
"""
import collections
import html
import inspect
import json
import pathlib
from urllib.parse import urlparse

MULTI = {"co.uk","com.au","co.jp","com.br","co.kr","com.tr","co.in","com.mx","com.ar","co.nz","org.uk","ne.jp",
         "or.jp","com.cn","com.tw","com.hk","co.za","com.sg","gov.uk","ac.uk","net.au","com.pl","co.il","com.ua"}
BOT_OWN_ROUTES = {"radiojavan.com", "t.me", "x.com", "twitter.com"}   # served outside yt-dlp's test URLs
SHORT_ALIASES = {"youtu.be", "redd.it", "dai.ly"}                      # the long domain is already listed


def _registrable(host):
    h = host.lower().split(":")[0]
    for p in ("www.","m.","mobile.","player.","embed.","video.","videos.","web.","music.","tv.","live.","play.","open.","api."):
        if h.startswith(p) and h.count(".") > 1:
            h = h[len(p):]
    parts = h.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


def _tests_of(ie):
    tests = []
    for key in ("_TESTS", "_TEST"):
        v = ie.__dict__.get(key)
        if isinstance(v, dict):
            tests.append(v)
        elif isinstance(v, list):
            tests += [t for t in v if isinstance(t, dict)]
    return tests


def extract():
    """
    Domains of every yt-dlp extractor, taken from its own test URLs, split into
    the public list and the adult filter.

    - The public list covers working, visible extractors only.
    - The adult filter covers every extractor, broken ones included: blocking a
      site yt-dlp cannot currently read costs nothing, and it keeps the filter
      from shrinking whenever an extractor is marked broken for a release.
    - An extractor counts as adult when most of its test cases are 18+, not when
      one is: YouTube, Reddit and Dailymotion each test an age-gated video.
    - Uses the non-lazy classes, because the lazy ones carry no _TESTS. A few
      frontend extractors pick a public instance at random when they are
      imported, so the random module is seeded first to keep the output stable.
    """
    import random
    random.seed(0)
    import yt_dlp
    from yt_dlp.extractor import _extractors as X
    from yt_dlp.extractor.common import InfoExtractor

    listed, all_clean, adult_dom, adult_ie = set(), set(), set(), set()
    for name, ie in sorted(vars(X).items()):
        if not (name.endswith("IE") and inspect.isclass(ie) and issubclass(ie, InfoExtractor)):
            continue
        tests = _tests_of(ie)
        with_info = [t for t in tests if t.get("info_dict")]
        is_adult = bool(with_info) and sum(t["info_dict"].get("age_limit") == 18 for t in with_info) > len(with_info) / 2
        public = not (ie.IE_NAME.lower().startswith("generic") or getattr(ie, "IE_DESC", None) is False or not ie.working())
        for t in tests:
            u = t.get("url") or ""
            if not u.startswith("http"):
                continue
            d = _registrable(urlparse(u).netloc)
            if "." not in d or len(d) < 4:
                continue
            if is_adult:
                adult_dom.add(d)
            else:
                all_clean.add(d)
                if public:
                    listed.add(d)
        if is_adult:
            adult_ie.update({ie.IE_NAME.split(":")[0].lower(), ie.ie_key().lower()})
    adult_dom -= all_clean                                    # a domain a general extractor serves is not adult by itself
    adult_dom = {d for d in adult_dom if "pornhub" not in d}  # PornHub has its own operator-set plan rules
    adult_ie = {x for x in adult_ie if "pornhub" not in x}
    sites = sorted((listed - SHORT_ALIASES) | BOT_OWN_ROUTES)
    adult = {"source": f"yt-dlp {yt_dlp.version.__version__}: extractors whose test cases are mostly age_limit 18",
             "domains": sorted(adult_dom), "extractors": sorted(adult_ie),
             "note": "PornHub is excluded on purpose: it has its own plan rules, set by the operator."}
    return {"ytdlp": yt_dlp.version.__version__, "sites": sites}, adult


def build_page(data, out, MODE="all"):
    """
    MODE: "all"   - directory of every site, long tail covered by the other-sites rule
          "paid"  - directory of every site, long tail on paid plans only
          "major" - platforms with their own plan rule only; no directory
    """
    SITES = data["sites"]; YTDLP = data["ytdlp"]
    N = len(SITES)
    UPDATED_ISO = "2026-09-10"; UPDATED = "10 September 2026"
    BASE = "https://www.gheychee.xyz"; URL = BASE + "/supported-sites.html"
    BOT = "https://t.me/gheychipremium_bot"
    fmt = lambda n: f"{n:,}"
    e = html.escape

    LONGTAIL_PLANS = {"all": "All plans, from the other-sites allowance",
                      "paid": "Starter, Standard, Pro, from the other-sites allowance"}.get(MODE)

    # What each platform returns and which plans carry a rule for it (plans.py defaults).
    MAJOR = [
      ("YouTube", "youtube.com", "Video, or the audio as MP3. Length is capped by plan.", "Starter, Standard, Pro"),
      ("Instagram", "instagram.com", "Public reels and posts.", "All plans"),
      ("X / Twitter", "x.com", "Video from public posts.", "All plans"),
      ("TikTok", "tiktok.com", "Video.", "Standard, Pro"),
      ("LinkedIn", "linkedin.com", "Video from public posts.", "All plans"),
      ("Telegram, restricted", "t.me", "Posts, albums and forum topics, including channels that switch saving off.", "All plans"),
      ("Facebook", "facebook.com", "Public video.", "Pro"),
      ("Vimeo", "vimeo.com", "Video.", "Pro"),
      ("SoundCloud", "soundcloud.com", "Audio.", "Starter, Standard, Pro"),
      ("RadioJavan", "radiojavan.com", "Audio only. Video links are declined.", "Starter, Standard"),
    ]
    if LONGTAIL_PLANS:
        MAJOR.append(("Reddit, Twitch, Dailymotion, Pinterest",
                      None, f"Video. These and {fmt(N - 14)} more sites are in the A to Z list below.", LONGTAIL_PLANS))

    site_count_phrase = (f"{fmt(N)} sites" if MODE != "major" else "the platforms below")
    title = (f"Supported sites: every site Gheychi can download from ({fmt(N)})" if MODE != "major"
             else "Supported sites and platforms | Gheychi Premium")
    desc = (f"Every site the Gheychi Premium Telegram bot downloads from: YouTube, Instagram, TikTok, X, LinkedIn, "
            f"restricted Telegram channels and {fmt(N - 6)} more. Updated {UPDATED}."
            if MODE != "major" else
            f"The platforms the Gheychi Premium Telegram bot downloads from, what each one returns, and which plans include it. Updated {UPDATED}.")

    jsonld = {
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "WebPage", "@id": URL, "url": URL, "name": title, "description": desc,
         "dateModified": UPDATED_ISO, "inLanguage": "en",
         "isPartOf": {"@type": "WebSite", "name": "Gheychi Premium", "url": BASE + "/"},
         "about": {"@id": BASE + "/#app"}, "breadcrumb": {"@id": URL + "#breadcrumb"}},
        {"@type": "BreadcrumbList", "@id": URL + "#breadcrumb", "itemListElement": [
          {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"},
          {"@type": "ListItem", "position": 2, "name": "Supported sites", "item": URL}]},
        {"@type": "SoftwareApplication", "@id": BASE + "/#app", "name": "Gheychi Premium",
         "applicationCategory": "MultimediaApplication", "operatingSystem": "Telegram",
         "url": BASE + "/", "sameAs": [BOT],
         "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": "0", "highPrice": "23", "offerCount": "4"}},
        {"@type": "ItemList", "name": "Major platforms supported by Gheychi Premium",
         "numberOfItems": len([m for m in MAJOR if m[1]]),
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": m[0]} for i, m in enumerate(m for m in MAJOR if m[1])]},
      ]}

    groups = collections.OrderedDict()
    for s in SITES:
        k = s[0].upper() if s[0].isalpha() else "#"
        groups.setdefault(k, []).append(s)
    if "#" in groups: groups.move_to_end("#", last=False)
    gid = lambda k: "dir-num" if k == "#" else f"dir-{k.lower()}"

    def _dom(d):
        return '<span class="dom">' + e(d) + '</span>' if d else ""
    major_rows = "\n".join(
      '          <tr><th scope="row">' + e(n) + _dom(d) + '</th><td>' + e(w) + '</td><td class="plans">' + e(p) + '</td></tr>'
      for n, d, w, p in MAJOR)

    directory = ""
    if MODE != "major":
        jump = "".join(f'<a href="#{gid(k)}">{e(k)}</a>' for k in groups)
        body = "\n".join(
          f'        <section class="dir-group" id="{gid(k)}" data-group>\n'
          f'          <h3 class="dir-letter">{e(k)}</h3>\n'
          f'          <ul>{"".join(f"<li>{e(s)}</li>" for s in v)}</ul>\n'
          f'        </section>' for k, v in groups.items())
        note_paid = (" The long tail needs a paid plan." if MODE == "paid" else "")
        directory = f'''
  <section class="band" aria-labelledby="h-dir">
    <div class="wrap">
      <div class="sec-rule"><span class="spec spec-ink">Directory</span><span class="spec">{fmt(N)} sites · yt-dlp {e(YTDLP)}</span></div>
      <h2 class="t-h2" id="h-dir">Every supported site, A to Z</h2>
      <p class="t-body" style="margin-top:1rem">This list is built from yt-dlp {e(YTDLP)}, the open-source download engine the bot runs, and includes every site with a working extractor in that version.{note_paid} Adult sites are left off this page.</p>
      <p class="t-body">A site being listed means the bot knows how to read it. It does not mean every link from it will work: a post that needs you to sign in, a video blocked in some countries, or a site that changed its layout last week can still fail.</p>

      <div class="dir-tools">
        <label class="dir-filter" hidden data-filter-wrap>
          <span class="spec spec-ink">Filter</span>
          <input type="search" placeholder="Type a site, e.g. bandcamp" autocomplete="off" spellcheck="false" data-filter>
        </label>
        <p class="spec spec-plain" aria-live="polite" data-count>{fmt(N)} sites</p>
      </div>
      <nav class="dir-jump" aria-label="Jump to letter">{jump}</nav>

      <div class="dir">
{body}
      </div>
      <p class="spec spec-plain dir-empty" hidden data-empty>No site in the list matches that. It may still work: send the link to the bot and see.</p>
    </div>
  </section>'''

    faq = [
      ("What sites does Gheychi Premium support?",
       (f"It downloads from {fmt(N)} sites. The main ones are YouTube, Instagram, X, TikTok, LinkedIn, Facebook, Vimeo, SoundCloud and RadioJavan, plus restricted Telegram channels. The rest come from yt-dlp, the open-source engine the bot runs on, and are listed A to Z on this page."
        if MODE != "major" else
        "YouTube, Instagram, X, TikTok, LinkedIn, Facebook, Vimeo, SoundCloud and RadioJavan, plus restricted Telegram channels. The table on this page shows what each one returns and which plans include it.")),
      ("Can it download from a Telegram channel that blocks saving?",
       "Yes, if the bot's account can see the channel. It runs a real Telegram user session, so content protection that stops forwarding and saving does not stop it. Public posts, private channels, groups and forum topics all work, including whole albums. Invite links that start with t.me/+ are not supported."),
      ("Is there a file size limit?",
       "Yes, 500 MB per file. Telegram limits bots to 50 MB per upload, so anything larger is sent through a Telegram user session instead and then copied into your chat. That takes a little longer, but the file arrives the same way."),
      ("Why did a link from a listed site fail?",
       "Usually because the video needs an account to watch, is blocked in the country the bot runs from, or is private. Sites also change their pages, and the engine needs an update to catch up. If a link fails, send it to /support in the bot and we will look at it."),
      ("Does it work with Netflix, Spotify or Disney+?",
       "No. Those services encrypt their streams with DRM, and the bot does not break that protection. The same goes for anything behind a paywall you would have to log in to."),
      ("Is Gheychi Premium free?",
       "There is a free plan with a monthly allowance on X, Instagram, LinkedIn, restricted Telegram and every other site in the A to Z list. It needs no card and no sign-up form; you start by opening the bot. Paid plans run from $5 to $23 a month and raise the allowances."),
    ]
    faq_html = "\n".join(
      f'''        <div class="qa">
          <h3>{e(q)}</h3>
          <p>{e(a)}</p>
        </div>''' for q, a in faq)

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{URL}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Gheychi Premium">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
<style>
  /* The directory is a parts index: ruled letter heads over mono entries in
     newspaper columns. Scoped here because no other page carries an index. */
  .plat {{ width: 100%; border-collapse: collapse; }}
  .plat th, .plat td {{ text-align: left; vertical-align: baseline; padding: .8125rem .75rem; border-bottom: 1px solid var(--rule-soft); }}
  .plat thead th {{ font-family: var(--mono); font-size: .6875rem; font-weight: 600; letter-spacing: .13em; text-transform: uppercase; color: var(--ink-3); border-bottom-color: var(--rule); white-space: nowrap; }}
  .plat th:first-child, .plat td:first-child {{ padding-left: 0; }}
  .plat th:last-child, .plat td:last-child {{ padding-right: 0; }}
  .plat tbody th {{ font-weight: 600; color: var(--ink); font-size: .9375rem; white-space: nowrap; }}
  .plat .dom {{ display: block; font-family: var(--mono); font-size: .6875rem; font-weight: 400; color: var(--ink-3); margin-top: .125rem; }}
  .plat td {{ color: var(--ink-2); font-size: .9375rem; }}
  .plat td.plans {{ font-family: var(--mono); font-size: .75rem; color: var(--ink); white-space: nowrap; }}
  .plat tbody tr:hover > * {{ background: var(--paper-2); }}
  .table-scroll {{ overflow-x: auto; }}

  .glance {{ max-width: 34rem; }}

  .dir-tools {{ display: flex; flex-wrap: wrap; align-items: end; gap: .75rem 1.5rem; margin-top: 2rem; }}
  .dir-filter {{ display: grid; gap: .375rem; flex: 1 1 18rem; max-width: 26rem; }}
  .dir-filter input {{
    font: 500 .9375rem/1.2 var(--mono); color: var(--ink); background: var(--paper);
    border: 1px solid var(--rule); border-radius: var(--radius); padding: .6875rem .75rem;
  }}
  .dir-filter input:focus-visible {{ outline: 2px solid var(--signal); outline-offset: 1px; border-color: var(--signal); }}
  .dir-jump {{ display: flex; flex-wrap: wrap; gap: .25rem; margin-top: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--rule); }}
  .dir-jump a {{
    font-family: var(--mono); font-size: .75rem; font-weight: 600; min-width: 1.75rem; text-align: center;
    padding: .3125rem .25rem; color: var(--ink-2); text-decoration: none; border: 1px solid var(--rule-soft); border-radius: 2px;
  }}
  .dir-jump a:hover {{ color: var(--signal-deep); border-color: var(--signal); }}
  .dir {{ columns: 13rem auto; column-gap: 2rem; margin-top: 1.5rem; }}
  .dir-group {{ margin-bottom: 1.25rem; scroll-margin-top: 5rem; }}
  .dir-letter {{
    font-family: var(--mono); font-size: .75rem; font-weight: 600; letter-spacing: .13em; color: var(--signal-deep);
    border-bottom: 1px solid var(--rule); padding-bottom: .25rem; margin-bottom: .375rem; break-after: avoid;
  }}
  .dir-group ul {{ list-style: none; margin: 0; padding: 0; }}
  .dir-group li {{ font-family: var(--mono); font-size: .8125rem; line-height: 1.85; color: var(--ink-2); overflow-wrap: anywhere; }}
  .dir-empty {{ margin-top: 1rem; }}

  .faq {{ display: grid; gap: 0; border-top: 1px solid var(--rule); }}
  .qa {{ padding: 1.375rem 0; border-bottom: 1px solid var(--rule-soft); display: grid; gap: .5rem; }}
  @media (min-width: 780px) {{ .qa {{ grid-template-columns: 22rem 1fr; gap: 2rem; align-items: baseline; }} }}
  .qa h3 {{ font-size: 1rem; letter-spacing: -0.015em; text-wrap: balance; }}
  .qa p {{ color: var(--ink-2); font-size: .9375rem; max-width: 64ch; }}
</style>
</head>
<body>
<a class="sr-only" href="#main">Skip to content</a>

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <g id="i-scissors" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
      <line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>
    </g>
    <g id="i-send" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4Z"/>
    </g>
    <g id="i-lock" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>
    </g>
    <g id="i-audio" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>
    </g>
    <g id="i-gauge" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 14 16 9"/><circle cx="12" cy="14" r="1"/><path d="M3.5 17a9 9 0 1 1 17 0"/>
    </g>
    <g id="i-langs" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 5h10"/><path d="M8 3v2c0 4.5-2 7-5 8"/><path d="M5 10c1.5 2.5 3.5 4 6 5"/><path d="M12 21l4.5-10 4.5 10"/><path d="M14 17h5"/>
    </g>
    <g id="i-shield" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>
    </g>
    <g id="i-check" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="m4 12 5.5 5.5L20 7"/>
    </g>
    <g id="i-menu" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
      <path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>
    </g>
  </defs>
</svg>

<header class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="index.html">
      <svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-scissors"/></svg>
      <span class="stack-s" style="gap:0">
        <b>Gheychi Premium</b>
        <span>Media tool · TG</span>
      </span>
    </a>
    <nav class="nav-links" aria-label="Primary">
      <a href="features.html">Capabilities</a>
      <a href="pricing.html">Plans</a>
      <a href="about-product.html">Roadmap</a>
      <a href="about-us.html">About</a>
      <a href="contact.html">Contact</a>
    </nav>
    <a class="btn btn-signal btn-sm nav-cta" href="{BOT}" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-send"/></svg> Open bot
    </a>
    <button class="nav-toggle" data-nav-toggle aria-expanded="false" aria-label="Open menu" aria-controls="navdrawer">
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><use href="#i-menu"/></svg>
    </button>
  </div>
  <div class="nav-drawer" id="navdrawer" data-nav-drawer>
    <div class="wrap">
      <a href="features.html">Capabilities</a>
      <a href="pricing.html">Plans</a>
      <a href="about-product.html">Roadmap</a>
      <a href="about-us.html">About</a>
      <a href="contact.html">Contact</a>
    </div>
  </div>
</header>

<main id="main">
  <section class="wrap" style="padding-block: clamp(2.25rem,5.5vw,3.75rem)">
    <div class="sec-rule"><span class="spec spec-ink">Supported sites</span><span class="spec">Updated <time datetime="{UPDATED_ISO}">{UPDATED}</time></span></div>
    <div class="cols cols-2" style="align-items:end">
      <div class="stack">
        <h1 class="t-display" style="font-size:clamp(2.25rem,6vw,4rem)">Every site Gheychi can download from</h1>
        <p class="t-lead">Gheychi Premium is a Telegram bot that downloads video and audio from a link. It works with {site_count_phrase}, including YouTube, Instagram, X, TikTok and LinkedIn, and it can read Telegram channels that switch saving off. Send the link to <a href="{BOT}" target="_blank" rel="noopener">@gheychipremium_bot</a> and the file comes back in the same chat.</p>
        <div class="row" style="margin-top:.5rem">
          <a class="btn btn-signal" href="{BOT}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-send"/></svg> Open the bot</a>
          <a class="btn btn-line" href="pricing.html">Compare plans</a>
        </div>
      </div>
      <dl class="specs glance">
        <div class="spec-row"><dt>Sites supported</dt><span class="leader"></span><dd>{fmt(N) if MODE != "major" else str(len([m for m in MAJOR if m[1]]))}</dd></div>
        <div class="spec-row"><dt>Largest file</dt><span class="leader"></span><dd>500 MB</dd></div>
        <div class="spec-row"><dt>Audio as MP3</dt><span class="leader"></span><dd>yes</dd></div>
        <div class="spec-row"><dt>Account needed</dt><span class="leader"></span><dd>no</dd></div>
        <div class="spec-row"><dt>Files kept on the server</dt><span class="leader"></span><dd>&lt; 1 hr</dd></div>
        <div class="spec-row"><dt>Download engine</dt><span class="leader"></span><dd>yt-dlp {e(YTDLP)}</dd></div>
      </dl>
    </div>
  </section>

  <section class="band band-tight" aria-labelledby="h-plat">
    <div class="wrap">
      <div class="sec-rule"><span class="spec spec-ink">Platforms</span><span class="spec">What comes back, and on which plan</span></div>
      <h2 class="t-h2" id="h-plat">Which platforms are supported?</h2>
      <p class="t-body" style="margin-top:1rem">These are the platforms people send most. Each one is counted separately against your plan, so a busy week on YouTube does not use up your Instagram allowance.</p>
      <div class="table-scroll" style="margin-top:1.5rem">
        <table class="plat">
          <thead><tr><th scope="col">Platform</th><th scope="col">What you get</th><th scope="col">Plans</th></tr></thead>
          <tbody>
{major_rows}
          </tbody>
        </table>
      </div>
      <p class="spec spec-plain" style="margin-top:1rem">Allowances per plan are on the <a href="pricing.html">plans page</a>.</p>
    </div>
  </section>

  <section class="band" aria-labelledby="h-why">
    <div class="wrap cols cols-doc" style="align-items:start">
      <div class="stack">
        <div class="sec-rule"><span class="spec spec-ink">Why Gheychi</span></div>
        <h2 class="t-h2" id="h-why" style="font-size:clamp(1.5rem,2.8vw,2.125rem)">Why use a Telegram bot instead of a downloader website?</h2>
        <p class="t-body">Downloader websites put a page, and usually a stack of ads, between you and the file. Gheychi works from inside Telegram, where you already are, and does a few things those sites cannot.</p>
      </div>
      <div class="caps">
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-lock"/></svg></span>
          <h3>Reads channels that block saving</h3>
          <p>Many Telegram channels switch off forwarding and saving. The bot runs a real Telegram user session, so it can still read those posts, as long as its account can see the channel. Albums come through whole.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-send"/></svg></span>
          <h3>No site, no app, no ads</h3>
          <p>You paste a link into a chat and the file arrives in that chat. There is nothing to install, no page full of pop-ups, and no fake download buttons to avoid.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-gauge"/></svg></span>
          <h3>Files up to 500 MB</h3>
          <p>Telegram stops bots at 50 MB per upload. Larger files go through a user session and are copied to you, so a long video still arrives instead of failing halfway.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-shield"/></svg></span>
          <h3>Nothing stays on the server</h3>
          <p>The bot keeps a temporary copy only while it sends the file, and deletes it within the hour. Your history is a list of links you sent, not a library of your files.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-audio"/></svg></span>
          <h3>Pick the quality, or just the audio</h3>
          <p>Choose a resolution before the download starts, or take the soundtrack as an MP3.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-langs"/></svg></span>
          <h3>English and Persian</h3>
          <p>The whole bot works in either language. Switch any time with /lang.</p>
        </div>
        <div class="cap">
          <span class="cap-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-check"/></svg></span>
          <h3>Free to start</h3>
          <p>The free plan needs no card and no sign-up form. Open the bot and send a link.</p>
        </div>
      </div>
    </div>
  </section>
{directory}

  <section class="band" aria-labelledby="h-faq">
    <div class="wrap">
      <div class="sec-rule"><span class="spec spec-ink">Questions</span></div>
      <h2 class="t-h2" id="h-faq">Questions about supported sites</h2>
      <div class="faq" style="margin-top:1.5rem">
{faq_html}
      </div>
    </div>
  </section>

  <section class="band band-plate" aria-labelledby="h-go">
    <div class="wrap row" style="justify-content:space-between;gap:1.5rem">
      <div class="stack-s">
        <h2 class="t-h3" id="h-go">Not sure your site works? Send the link and find out.</h2>
        <p class="t-body">The free plan is enough to try it.</p>
      </div>
      <a class="btn btn-signal" href="{BOT}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-send"/></svg> Open @gheychipremium_bot</a>
    </div>
  </section>
</main>

<footer class="foot">
  <div class="wrap">
    <div class="foot-grid">
      <div>
        <a class="brand" href="index.html">
          <svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-scissors"/></svg>
          <span class="stack-s" style="gap:0"><b>Gheychi Premium</b><span>Media tool · TG</span></span>
        </a>
        <p class="foot-note">A media downloader that lives in Telegram, including the channels other tools cannot reach.</p>
      </div>
      <div class="foot-col">
        <p class="foot-title">Product</p>
        <a href="features.html">Capabilities</a>
        <a href="supported-sites.html">Supported sites</a>
        <a href="pricing.html">Plans</a>
        <a href="about-product.html">Roadmap</a>
      </div>
      <div class="foot-col">
        <p class="foot-title">Company</p>
        <a href="about-us.html">About</a>
        <a href="contact.html">Contact</a>
      </div>
      <div class="foot-col">
        <p class="foot-title">Legal</p>
        <a href="privacy.html">Privacy</a>
        <a href="terms.html">Terms</a>
      </div>
    </div>
    <div class="foot-base">
      <span class="spec spec-plain">© 2026 Gheychi Premium</span>
      <span class="spec spec-plain">gheychee.xyz · @gheychipremium_bot</span>
    </div>
  </div>
</footer>

<script src="script.js"></script>
<script>
  // Filtering is an enhancement: the full list is in the HTML for readers and
  // crawlers, and the control only appears once this script can drive it.
  (function () {{
    var input = document.querySelector('[data-filter]');
    if (!input) return;
    document.querySelector('[data-filter-wrap]').hidden = false;
    var groups = [].slice.call(document.querySelectorAll('[data-group]'));
    var count = document.querySelector('[data-count]');
    var empty = document.querySelector('[data-empty]');
    var total = {N};
    input.addEventListener('input', function () {{
      var q = input.value.trim().toLowerCase(), shown = 0;
      groups.forEach(function (g) {{
        var any = false;
        [].forEach.call(g.querySelectorAll('li'), function (li) {{
          var hit = !q || li.textContent.indexOf(q) !== -1;
          li.hidden = !hit; if (hit) {{ any = true; shown++; }}
        }});
        g.hidden = !any;
      }});
      count.textContent = q ? shown.toLocaleString('en') + ' of ' + total.toLocaleString('en') + ' sites' : total.toLocaleString('en') + ' sites';
      empty.hidden = shown !== 0;
    }});
  }})();
</script>
</body>
</html>
'''
    open(out, "w").write(page)
    return N


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parent.parent
    data, adult = extract()
    with open(root / "adult_sites.json", "w") as f:
        json.dump(adult, f, ensure_ascii=False, indent=1)
    n = build_page(data, str(root / "website" / "supported-sites.html"), "all")
    print(f"yt-dlp {data['ytdlp']}: {n:,} sites, {len(adult['domains'])} adult domains, "
          f"{len(adult['extractors'])} adult extractors")
