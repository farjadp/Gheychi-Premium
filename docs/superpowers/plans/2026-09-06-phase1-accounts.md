# Phase 1 — Web Accounts and Telegram Linking

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every user one account they can reach two ways — by email on the site, or by the existing magic link from the bot — and let that account hold several verified Telegram accounts.

**Architecture:** A new `accounts` table becomes the identity, with `account_telegram_links` mapping Telegram accounts onto it (`telegram_user_id` is the primary key there, so one Telegram account can only ever have one owner). Login is passwordless throughout: a six-digit code by email, and for Telegram a proof that flows *from* Telegram *to* the web. Entitlements still hang off `telegram_user_id` in this phase — moving them is Phase 2 — so nothing about quota behaviour changes yet.

**Tech Stack:** Python 3.11, Flask, SQLite (WAL), python-telegram-bot 21.6, itsdangerous, Resend for email. No framework, no build step: the site stays static HTML served by Flask.

**Spec:** the analysis in the Gheychee Board Notion tasks (`collection://6fbbbd3c-c609-4381-945f-1a0cca1794e7`), model C.

## Global Constraints

- Identity model is **C**: the plan belongs to the account, and the number of linked Telegram accounts is capped by tier — Free 1, Starter 1, Standard 2, Pro 3 — with a 7-day cooldown before a freed slot can be reused.
- **Telegram verification runs Telegram → web, never the reverse.** A bot cannot message anyone who has not started it, and resolving a `@username` needs the MTProto userbot session, which is not worth the ban risk.
- No passwords anywhere. Email proves itself by receiving a code.
- All one-time codes: hashed at rest, single use, 5-minute TTL, 5-attempt ceiling, and rate limited through the existing `rate_limit_hit`.
- Persian and English both, following `bot_users.language_code`; English is the default.
- Nothing may claim a file-size limit above 50 MB, and card payment is still not live.
- File size cap and payment copy in `PRODUCT.md` stay true; principle 4 ("no account to create") must be rewritten, not quietly ignored.

---

## File Structure

| File | Responsibility |
|---|---|
| `accounts.py` *(new)* | The account model: create/lookup by email, link and unlink Telegram accounts, tier caps, cooldowns. All account SQL lives here. |
| `auth_codes.py` *(new)* | Issue, verify and burn one-time codes. Shared by email login and Telegram linking so the TTL/attempt/hashing rules exist once. |
| `mailer.py` *(new)* | Resend wrapper. One `send_login_code()`. Fails loudly and never blocks a request for long. |
| `runtime_store.py` | Schema only — the three new tables join the existing `init_logs_db()` block. |
| `plans.py` | `max_linked_accounts` per tier, with a safe default of 1. |
| `admin_panel.py` | New `/auth/email/*` and `/account/*` routes; `/auth/magic` resolves through the account. |
| `bot.py` | `/start link_<token>` deep-link handler, `/link <code>` fallback, both with a confirm step. |
| `website/account.html` *(new)* | Sign-in and profile screens. |
| `locales.py` | Strings for the linking flow, both languages. |

---

## Task 1 — Schema and the account model

- [ ] Add `accounts`, `account_telegram_links`, `link_cooldowns` to `init_logs_db()` in `runtime_store.py`
- [ ] Write `accounts.py`: `create_account(email)`, `get_account_by_email`, `get_account_by_telegram`, `list_links`, `link_telegram`, `unlink_telegram`
- [ ] `link_telegram` must refuse when the Telegram account already belongs to a different account, when the tier cap is reached, and when a cooldown is still running — each with a distinct, testable error
- [ ] Test: linking twice to different accounts fails; cap is enforced; unlink then relink inside 7 days fails
- [ ] Commit

**Schema:**
```sql
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,           -- uuid4 hex
    email      TEXT NOT NULL UNIQUE,       -- stored lowercased and stripped
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE account_telegram_links (
    telegram_user_id INTEGER PRIMARY KEY,  -- PK, so one Telegram account has exactly one owner
    account_id       TEXT NOT NULL,
    linked_at        TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts (account_id)
);
CREATE TABLE link_cooldowns (
    account_id       TEXT NOT NULL,
    telegram_user_id INTEGER NOT NULL,
    unlinked_at      TEXT NOT NULL,
    reusable_at      TEXT NOT NULL
);
```

Emails are lowercased before storage, so `UNIQUE` does the work without `COLLATE NOCASE` surprises.

## Task 2 — One-time codes

- [ ] `auth_codes.py`: `issue_code(purpose, subject, length)` and `verify_code(purpose, subject, code)`
- [ ] Codes are HMAC-SHA256 keyed by `FLASK_SECRET_KEY`, never stored in the clear — a bare hash of six digits is a 10^6 offline search
- [ ] Purposes are distinct so a 6-digit code can never be replayed as a deep-link token: `email_login`, `telegram_link_deep`, `telegram_link_code`
- [ ] Test: correct code passes once; replay fails; wrong code burns an attempt; sixth attempt fails even with the right code; expired code fails
- [ ] Commit

## Task 3 — Resend

- [ ] `mailer.py` with `send_login_code(email, code, lang)`; no-op with a loud log when `RESEND_API_KEY` is unset, exactly as backups behave
- [ ] Plain-text and HTML body, both languages, no tracking pixels
- [ ] **Blocked on Farjad:** Resend account, `RESEND_API_KEY`, and SPF/DKIM/DMARC on `gheychee.xyz`. Until the DNS is authenticated, codes land in spam and this path is untestable in the real world.
- [ ] Commit

## Task 4 — Email sign-in

- [ ] `POST /auth/email/request` → issue + send, always answering "check your email" so the response cannot enumerate who has an account
- [ ] `POST /auth/email/verify` → on success create the account if new, set `role=user`, redirect to the profile
- [ ] Rate limit per IP **and** per email
- [ ] Test: unknown email creates an account on verify, not on request; bad code does not
- [ ] Commit

## Task 5 — Telegram linking, both directions

- [ ] Profile issues a `telegram_link_deep` token and renders `t.me/<bot>?start=link_<token>` as a button and a QR, plus a 6-digit code for the desktop case
- [ ] `bot.py`: `/start link_<token>` and `/link <code>` both resolve the token, then **ask for confirmation** before linking — the user must see which email they are joining
- [ ] Refusals are specific: already linked here / linked to `f***@gmail.com` / tier cap reached / cooldown until date
- [ ] Profile polls and turns green without a reload
- [ ] Test: deep link and code both link; both refuse a Telegram account owned elsewhere
- [ ] Commit

## Task 6 — Fold the existing magic link into accounts

- [ ] `/auth/magic` resolves `telegram_user_id` → account, creating an account with no email when none exists, so a bot-first user is never orphaned
- [ ] A user who later signs in by email and links that same Telegram account joins the *existing* account rather than creating a second
- [ ] Test: bot-first then email-first converges on one account
- [ ] Commit

## Task 7 — Profile page and docs

- [ ] `website/account.html`: linked accounts, slots used vs. tier cap, add and remove, RTL when Persian
- [ ] Copy states plainly that quota is one shared pool across linked accounts
- [ ] Rewrite `PRODUCT.md` principle 4 and the "no signup form" claim
- [ ] Commit

---

## Risks

- **Losing the DB now destroys real accounts.** Backups exist as of Phase 0 but have never been restored in anger. Do a restore drill before this ships.
- **Deliverability is the whole email path.** A young domain without authenticated DNS means codes silently land in spam; treat Task 3 as blocking for Task 4's real-world use, not for its tests.
- **The tier cap is only half the anti-sharing design.** The shared quota pool is the other half and does not land until Phase 2, so between the two phases a Standard user genuinely gets two independent quotas. Either accept that window knowingly or hold the cap increase until Phase 2.
