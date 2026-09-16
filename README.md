# Tennis Trader Alerts — instant Telegram break-point alerts

[![CI](https://github.com/stephanepatteux/tennis-trader-alerts/actions/workflows/ci.yml/badge.svg)](https://github.com/stephanepatteux/tennis-trader-alerts/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)

A self-hosted Python worker that connects to the **Live Tennis API Ultra
WebSocket** and sends **instant Telegram alerts** when a tennis match hits a
trading trigger: **0–40**, **15–40**, **30–40**, any break point, deuce, or
tiebreak. Point-by-point, no polling. Scores are informational — **not tips**.

Companion to the open-source
[Tennis Trader Board](https://github.com/stephanepatteux/live-tennis-scoreboard).

> ## ⚡ Real-time push requires a Live Tennis API **Ultra** key
> The point-by-point push feed is an **Ultra-only** capability. Get an Ultra key
> here (affiliate link) and use code **`botblog`** for 10% off:
> **[Subscribe to Ultra](https://affiliates.livetennisapi.com/r/botblog)**.
> _[Why Ultra is required](#why-an-ultra-key-is-required-for-real-time-push) ·
> [Affiliate disclosure](#affiliate-disclosure)._

## Contents

- [Who it's for](#who-its-for)
- [Why an Ultra key is required](#why-an-ultra-key-is-required-for-real-time-push)
- [Features](#features)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Per-user rules](#per-user-rules)
- [FAQ](#faq)
- [Affiliate disclosure](#affiliate-disclosure) · [Disclaimer](#disclaimer)

## Who it's for

Betfair (and other exchange) **in-play tennis traders** who want the 15–40 / 0–40
moment on their phone the instant it is scored — not after the next poll, and
not buried in a scoreboard tab. Pair it with the
[Tennis Trader Board](https://github.com/stephanepatteux/live-tennis-scoreboard)
on a second screen.

## Why an Ultra key is required for real-time push

**The whole point of this service is that a break point hits Telegram the moment
it is played.** That "server pushes each point to you" model is only available
on Live Tennis API's **Ultra** plan.

### Push vs. polling

- **Polling (lower tiers): _you_ ask, on a timer.** Free/basic keys expose only
  REST endpoints (e.g. `GET /matches?status=live`). A break point can come and
  go between two calls. The free plan is capped at **30 requests/min and 100
  requests/day**, so "every few seconds" burns quota immediately — and you still
  only see the score as it was at each poll.
- **Push (Ultra): _the server_ tells you, the instant it changes.** Ultra opens
  a **WebSocket**. You connect once and the server sends a frame **on every
  score commit**. That is the only way to get true point-by-point, zero-delay
  alerts.

### The push feed is gated to Ultra by the API itself

Real-time push is minted through `GET /ws-token`, documented as **"Plan
required: ULTRA."** With a lower-tier key the token request is rejected
(HTTP 401/403). It is not a client setting we can toggle.

### This worker is push-only on purpose

There is **no polling fallback**. Without an Ultra key the process exits and
tells you why. Add an
[Ultra key](https://affiliates.livetennisapi.com/r/botblog) (code `botblog`) and
it connects to the Ultra WebSocket and alerts on real matches, point by point.

> **No API key ships with this project.** This repository contains **no key at
> all** — not even a hidden or example one. You buy your own Live Tennis API
> Ultra key and create your own Telegram bot, then supply both at runtime via
> `LIVE_TENNIS_API_KEY` and `TELEGRAM_BOT_TOKEN` (kept in an untracked `.env`,
> never committed).

```
Telegram  ◀── sendMessage ──  this worker  ── WebSocket ──▶ Live Tennis API Ultra
                              (GET /ws-token → connect → subscribe → rising-edge)
```

Your **API keys stay on the server**. The Ultra key is sent to Live Tennis API
as an `Authorization: Bearer` header; the Telegram token is used only to call
Bot API `sendMessage`. Neither is committed to this repo.

## Features

- Live Tennis API **Ultra WebSocket** client (ported from the trader board):
  token mint, reconnect with a fresh token, heartbeat reply, score-frame mapping.
- Local alert detection — same codes as the board: `0–40`, `15–40`, `30–40`,
  any break point, deuce, tiebreak. Computed here so filters mean the same thing
  on live data.
- **Per-user rules**: each Telegram chat chooses triggers and optional
  tour / surface / player-watchlist filters. JSON file, reload-on-change.
- **Rising-edge de-dup**: a 15–40 that sits for three points is one Telegram
  message, not three. The same break point can fire again after it clears.
- **Per-chat rate limiting** so a busy slate cannot flood a phone.
- Telegram Bot API `sendMessage` (HTML). Dry-run mode logs the same text.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# set LIVE_TENNIS_API_KEY (Ultra) and TELEGRAM_BOT_TOKEN
# set TELEGRAM_CHAT_ID, or copy data/rules.example.json → data/rules.json

python -m app                 # live alerts
python -m app --dry-run       # log messages, do not call Telegram
pytest                        # unit tests (no keys required)
```

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and put the
   token in `TELEGRAM_BOT_TOKEN`.
2. Message your bot, then put your numeric chat id in `TELEGRAM_CHAT_ID` (or in
   `data/rules.json`).
3. Subscribe to Ultra with code **`botblog`**:
   [https://affiliates.livetennisapi.com/r/botblog](https://affiliates.livetennisapi.com/r/botblog).

## Configuration

All configuration is via environment variables — see
[`.env.example`](.env.example):

| Variable                  | Default                                       | Purpose |
| ------------------------- | --------------------------------------------- | ------- |
| `LIVE_TENNIS_API_KEY`     | _(required)_                                  | Live Tennis API **Ultra** key. Server-side only. |
| `LIVE_TENNIS_API_BASE`    | `https://api.livetennisapi.com/api/public/v1` | API base URL (`/ws-token` is minted from here). |
| `LIVE_TENNIS_API_TIMEOUT` | `10`                                          | Token-mint / connect timeout (seconds). |
| `TELEGRAM_BOT_TOKEN`      | _(required unless `--dry-run`)_               | Telegram bot token from @BotFather. |
| `TELEGRAM_CHAT_ID`        | _(or use `data/rules.json`)_                  | Default chat when no rules file is present. |
| `RULES_PATH`              | `data/rules.json`                             | Per-user rules JSON. |
| `ALERT_TRIGGERS`          | all of `0-40,15-40,30-40,break-point,deuce,tiebreak` | Env bootstrap triggers. |
| `ALERT_TOURS`             | _(all)_                                       | e.g. `atp` or `wta`. |
| `ALERT_SURFACES`          | _(all)_                                       | e.g. `clay,hard,grass`. |
| `ALERT_WATCHLIST`         | _(all)_                                       | Comma-separated player-name substrings. |
| `RATE_LIMIT_MAX`          | `20`                                          | Max Telegram sends per chat per window. |
| `RATE_LIMIT_WINDOW_S`     | `60`                                          | Rate-limit window (seconds). |
| `LOG_LEVEL`               | `INFO`                                        | `DEBUG` / `INFO` / `WARNING`. |

Operations notes (reconnect behaviour, rules reload, state): see
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Per-user rules

Copy [`data/rules.example.json`](data/rules.example.json) to `data/rules.json`
(git-ignored) for more than one chat:

```json
{
  "users": [
    {
      "chat_id": "123456789",
      "enabled": true,
      "name": "phone",
      "triggers": ["0-40", "15-40", "break-point"],
      "tours": ["atp"],
      "surfaces": ["hard", "grass"],
      "watchlist": ["Sinner", "Alcaraz"]
    }
  ]
}
```

- **`break-point`** is *any* break point (including advantage-returner). It
  fires when a match *enters* a break-point state, not on every subsequent
  15–40 / 30–40 tick.
- Empty `tours` / `surfaces` / `watchlist` = no filter.
- Edit the file while the worker is running; it reloads on change.

## FAQ

**Is this a Betfair betting bot?** No. It is a **read-only alerter**. It never
places bets.

**Do I need an API key?** Yes — a
**[Live Tennis API Ultra](https://affiliates.livetennisapi.com/r/botblog)** key
(use code `botblog`; the push feed is Ultra-only) plus a Telegram bot token.
See [Why Ultra is required](#why-an-ultra-key-is-required-for-real-time-push).

**Why not just poll every few seconds?** Polling misses the exact moment a
point lands and burns rate-limited quota. The Ultra WebSocket pushes **every
point** with no delay.

**Is my API key safe?** Yes. Keys are read from the environment server-side.
`.env` is git-ignored. Nothing is committed.

## Affiliate disclosure

Links to Live Tennis API on this page are affiliate links: if you subscribe
through them (optionally with code `botblog`), this project may earn a
commission at no extra cost to you. You can also sign up directly at
[livetennisapi.com](https://livetennisapi.com).

## License

Released under the [MIT License](LICENSE) — free to use, modify, and self-host.

## Disclaimer

Not financial advice. Live scores are informational only. They are not tips and
do not place bets for you.

**18+ only. Please gamble responsibly** — see
[BeGambleAware](https://www.begambleaware.org/). Trading on betting exchanges
carries risk; only stake what you can afford to lose.
