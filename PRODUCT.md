# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing codebase. The marketing site and user dashboard are plain static HTML/CSS/JS in `website/`, served by the Flask app (`admin_panel.py`) at the service root. The admin panel is a single Jinja template (`admin_template.html`) rendered by the same Flask app. No build step, no framework, no bundler.

## Users

**Primary:** people who want a file off the internet — a video, a track, a clip — and do not want to visit an ad-laden downloader site to get it. They already live in Telegram, so the product meets them there. Confirmed as an international, general audience; the site does not address the Iranian market specifically, even though the bot itself is bilingual.

**Secondary:** the operator (a single admin) who runs plans, approves payments, watches logs, and broadcasts to users through the web admin panel.

## Product Purpose

Send a link to a Telegram bot, get the media back as a file in the same chat. The website exists to explain that offer, sell a subscription against it, and give a paying user a place to see their plan, quota, and history outside the chat.

Success is a visitor who understands the offer within seconds and opens the bot.

## Positioning

The mechanism a neighboring downloader cannot truthfully copy: **Save Restricted Content.** The bot runs a real Telegram user session (MTProto), so it can retrieve media from private channels and groups that have forwarding and saving disabled — content the ordinary Bot API cannot touch. Every generic "paste a YouTube link" competitor stops at the public web; this one reaches inside Telegram itself.

Everything else the product does — 1000+ sites via yt-dlp, quality selection, audio extraction — is table stakes that the category already offers.

## Operating Context

- The whole primary workflow happens inside a Telegram chat. The website is never where the work happens; it is where the offer is understood and the account is managed.
- The user's own device is the destination. There is no cloud library, no player, no storage — the file arrives in the chat and the temporary copy is deleted server-side within the hour.
- Access to the web dashboard is by magic link issued from the bot, not by password. There is no signup form and no account creation on the site.

## Capabilities and Constraints

**Working today:**
- Download from YouTube, Instagram, Twitter/X, TikTok, Reddit, Facebook, Vimeo, Dailymotion, Twitch, SoundCloud and 1000+ other sites via yt-dlp
- Quality selection per request; audio-only (MP3) extraction
- Save Restricted Content from private Telegram channels, groups, and topics, including full albums
- Per-plan quotas by platform, with daily / weekly / monthly periods and per-platform duration caps
- Bilingual bot interface, Persian and English
- Magic-link web dashboard showing plan, quota, and history
- Admin panel: plans, subscriptions, transactions, logs, broadcast, analytics, backup

**Hard constraints that copy must respect:**
- **File size is capped at 50 MB today.** This is the Telegram Bot API's upload limit. A dump-channel workaround exists in code but is not configured in production, so no page may claim 2 GB, 4K, or any figure above 50 MB. The previous site claimed 2 GB and 4K; both were false and must not be carried forward.
- Telegram invite links (`t.me/+hash`) are not supported.
- RadioJavan is audio-only; video is rejected.
- Automated card payment is **not live**. Stripe is coded but unconfigured; subscriptions are activated manually by the admin today. Pricing pages may show plans and prices, but must not promise instant automated checkout until Stripe is configured.

## Brand Commitments

- Name: **Gheychi Premium**. "Gheychi" (قیچی) is Persian for *scissors* — the product cuts media out of the web. The scissors idea is the one piece of brand equity worth keeping; the previous site expressed it only as a ✂️ emoji.
- Bot handle: `@gheychipremium_bot`. Public domain: `gheychee.xyz`.
- Site language: English.

## Evidence on Hand

- Real, verifiable: the platform list, the plan structure and prices (Free $0, Starter $5, Standard $13, Pro $23), the bilingual bot, the magic-link dashboard, the admin panel.
- **No** customers, testimonials, user counts, download counts, uptime figures, press, reviews, or benchmarks exist. None may be invented, and none appeared on the previous site either.
- No logo file, no product photography, no screenshots exist in the repo. Any imagery must be authored.
- The roadmap on the previous site (V1–V4 with completion states) is real project history and can be preserved, with V3 corrected: Stripe is coded but not live.

## Product Principles

1. **The chat is the product; the site is the argument.** Never design the website as though it were the application.
2. **Claim only what runs.** The previous site's inflated numbers are the specific failure this rebuild corrects. 50 MB is 50 MB.
3. **Lead with the thing only we do.** Restricted Telegram content is the differentiator; generic downloading is the commodity.
4. **No account to create.** Every call to action ends in Telegram, never in a signup form.
5. **One operator, many users.** Admin surfaces optimize for a single person scanning quickly, not for a team workflow.

## Accessibility & Inclusion

No product-specific standard was established. Ordinary web baseline applies: keyboard operability, visible focus, sufficient contrast, and content that does not depend on color alone.
