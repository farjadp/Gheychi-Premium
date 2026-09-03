# Design

Recorded from the built site, not from intention. Source of truth: `website/style.css`.

## World

**A precision-instrument trade catalogue.** The product is a tool named after a tool, so the site is set the way a tool catalogue is set: a paper ground, hairline registration rules, dotted spec leaders, part-numbered figure plates, and one saturated tool-signal orange. The persuading is done by measured figures, not by claims.

It is the deliberate opposite of the site it replaced (dark ground, glass panels, indigo→violet gradient, emoji icons, "Lightning Fast"). Those devices are the anti-reference and must not return.

Direction: candidate 5 of 7 on the grounded list, seed key `dd384b0b`. Every page carries the direction contract as an HTML comment directly inside `<body>`.

## Color

Strategy: **restrained neutrals with one signal**, escalating to committed where the signal owns a whole band. Dark or light was decided from the use scene — someone on a phone in daylight, mid-errand — so the site is lit paper, not a console.

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#EFEFEA` | Page ground |
| `--paper-2` | `#E7E7E0` | Recessed plates, footer, table hover |
| `--ink` | `#16160F` | Headings, values |
| `--ink-2` | `#5A5A4E` | Body text (6.05:1 on paper) |
| `--ink-3` | `#66665C` | Spec labels (5.03:1 on paper, 4.67:1 on paper-2) |
| `--rule` / `--rule-soft` | `#C9C9BC` / `#DBDBD0` | Registration rules, row dividers |
| `--signal` | `#D63C0B` | Primary action, figure routing, list marks (white text 4.66:1) |
| `--signal-deep` | `#A82C05` | Hover, signal-coloured text on paper |
| `--hazard` | `#E0A400` | **Restricted-content surfaces only** — never decorative |
| `--plate` | `#16160F` | Inverted band |

Every text/ground pair in the shipped CSS clears WCAG AA 4.5:1. The CTA band uses `#B93107` rather than `--signal` specifically so its secondary text (`#FFE2D8`, 4.88:1) can be tinted from the hue instead of going gray.

## Type

- **Archivo** — headings, body, UI. Chosen as a grotesk with real character; not one of the defaults the brief warns about.
- **JetBrains Mono** — every measured value: part numbers, file sizes, timestamps, quotas, platform slugs, bot commands. Monospace here is measurement, not costume.

Scale: display `clamp(2.75rem, 8.5vw, 5.75rem)` at `-0.045em`; `.t-h2` `clamp(1.85rem, 4.2vw, 3rem)`; `.t-h3` `clamp(1.2rem, 2.2vw, 1.5rem)`. Body measure is capped at 62–70ch. No functional text below 11px.

`.spec` is the label voice — 11px mono, uppercase, `.13em` tracking. Past a few words it becomes `.spec-plain`, which keeps the voice and drops the shouting.

## Components

- **`.spec-row`** — the catalogue's core element: term, dotted leader, monospace value. Used for every figure on the site, including the dashboard's plan and allowance tables.
- **`.plate`** — a bordered figure ground holding an SVG diagram and a `Fig. n` caption.
- **`.caps` / `.cap`** — capabilities as a ruled list with an icon rail. Deliberately *not* a grid of equal cards.
- **`.restricted`** — the only surface allowed hazard yellow, marked with a diagonal hazard stripe.
- **`.tiers`** — pricing as a four-column ruled table, not four floating cards.
- **`.ledger`** — the dashboard's download record: ruled columns, tabular numerals, monospace timestamps.

**Not in this system:** cards as page structure, nested cards, glass or backdrop decoration, gradient text, hard offset shadows, colored left borders, progress rings, sparklines, emoji-as-icon, eyebrows above headings, decorative section numbering.

## Icons

Authored SVG in one 1.6px stroke on a 24px grid, defined once per page in a hidden `<defs>` sprite and referenced with `<use>`. Any new icon must match that stroke and grid.

## Motion

One authored moment: the hero figure's routing and dimension lines draw themselves once on entry, each stroke measured by `getTotalLength()` so the draw reads as measurement rather than as a generic dash animation. Section content rises 14px on entry with an exponential ease-out.

Content is visible by default — the reveal is applied only after `script.js` adds `.js`, so the page is complete with JavaScript off. `prefers-reduced-motion` settles everything immediately.

## Browser surfaces

Selection, caret, focus ring, and scrollbar are all themed from the palette. Tabular numerals are on wherever figures are compared.

## Modes

- `index`, `features`, `pricing`, `about-product`, `about-us`, `contact` — **Persuade**.
- `privacy`, `terms` — **Read**: sticky section rail plus a 68ch prose measure.
- `user_dashboard` — **Operate**: the same world tuned for scanning, with a real empty state and an expired-plan state.
- `admin_template.html` — **Operate**: the operator's control room.

## Control room

The admin panel is English and LTR, and it links `/style.css` rather than
carrying its own palette, so the operator surface cannot drift from the public
site. It adds only the chrome that surface lacks: an index rail, ledger tables,
form controls, badges and the plan editor.

Two decisions worth keeping:

- **Key figures are a ruled row, not coloured stat cards.** Four terms with
  monospace values across one rule, so the operator reads them as a set.
- **The language switch was removed.** The panel is no longer bilingual, so a
  FA/EN toggle would have been a control that changes nothing. `format_rule` is
  bound to English in `admin_panel.py` for this surface.

The catch-all platform `"و بیش از ۱۰۰۰ سایت دیگر"` is a **stored value the bot
matches on** (`bot.py:499`). It is displayed as "Everything else yt-dlp
supports" and the value itself is never rewritten. Renaming it would silently
break platform gating.

## Verification on this build

- Detector: 152 findings → 50. Every contrast and heading-order finding resolved.
- The 35 remaining `cramped-padding` findings were checked in the browser and are false positives: the detector does not evaluate `clamp()`, and the flagged elements compute to 102px, 32px and 28px of real padding.
- The 8 `repeating-stripes-gradient` findings (advisory) are the hazard stripe on `.restricted`, which is meaningful rather than decorative and is kept deliberately.
- Screenshots at 1440 and 390 for all nine surfaces are in `.impeccable/review/`.
- The shipped `impeccable-finish-reviewer` subagent is not available in this harness, so the finish review was not run; the inspection above was done in-thread. This is a disclosed substitution, not a completed review.
