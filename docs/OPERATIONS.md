# Operations

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # add LIVE_TENNIS_API_KEY (Ultra) + TELEGRAM_BOT_TOKEN
# either set TELEGRAM_CHAT_ID in .env, or:
cp data/rules.example.json data/rules.json   # then put real chat_id values in it
python -m app
```

`--dry-run` logs formatted Telegram messages instead of calling `sendMessage`
(still needs an Ultra key to consume the live feed).

## Running tests

```bash
pytest
```

## Data flow

```
Live Tennis API Ultra  --WebSocket-->  UltraPushSource  -->  PushHub
                                                          -->  Dispatcher
                                                               (rising-edge de-dup,
                                                                per-user rules,
                                                                rate limit)
                                                          -->  Telegram sendMessage
```

1. `UltraPushSource` (`app/push/sources.py`) mints a token: `GET /ws-token` with
   `Authorization: Bearer <ULTRA key>` → `{token, ws_url, channels}`.
2. It opens `ws_url`, sends `{"connect":{"token":...}}`, subscribes to `slate:all`,
   and receives `{"push":{"pub":{"data": <score frame>}}}` on each score commit.
3. Each frame is mapped (`app/mapping.py`) into the match shape; alerts are
   computed locally (`app/scoring/alerts.py`) — the same codes as the Tennis
   Trader Board.
4. The worker de-duplicates on **rising edge** (a code only fires when it newly
   appears for that match), applies per-user trigger + tour/surface/watchlist
   filters, rate-limits per `chat_id`, and POSTs Telegram `sendMessage`.

Heartbeats (`{}`) are answered promptly; the token is short-lived, so the source
mints a fresh one and re-subscribes on every reconnect.

There is **no REST polling fallback**. Without an Ultra key the worker exits.

## Environment variables

See [`.env.example`](../.env.example). Required for live alerts:

| Variable              | Purpose |
| --------------------- | ------- |
| `LIVE_TENNIS_API_KEY` | Live Tennis API **Ultra** key (server-side only). |
| `TELEGRAM_BOT_TOKEN`  | Telegram Bot API token from @BotFather. |

Optional: `TELEGRAM_CHAT_ID` (single-user bootstrap), `RULES_PATH`,
`ALERT_TRIGGERS` / `ALERT_TOURS` / `ALERT_SURFACES` / `ALERT_WATCHLIST`,
`RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW_S`, `LIVE_TENNIS_API_BASE`,
`TELEGRAM_API_BASE`, `LOG_LEVEL`.

## Rules file

`data/rules.json` (git-ignored) is the per-user store. Copy
`data/rules.example.json` and edit. The worker reloads the file when its mtime
changes — no restart needed to add a chat or tighten triggers.

Each user:

- `triggers` — `0-40`, `15-40`, `30-40`, `break-point` (any BP, including
  advantage-returner), `deuce`, `tiebreak`. Empty / omitted = all of them.
- `tours` — e.g. `["atp"]`. Empty = all tours.
- `surfaces` — e.g. `["clay","hard"]`. Empty = all surfaces.
- `watchlist` — player-name substrings. Empty = all matches.

## Key safety

Keys are read from the environment server-side. They are never committed
(`.env` is git-ignored; `.env.example` documents every variable). The Ultra key
is sent to Live Tennis API as a request header; the Telegram token is used only
to call `sendMessage`. Logs include `chat_id` and `match_id`, not tokens.

## State model

No database. Hub state, rising-edge memory, and rate-limit windows are
in-memory, so restarting the process resets them. No historical backfill is
required (or possible) — alerts are live-only.

## Cloud Agent environment

Defined in [`.cursor/environment.json`](../.cursor/environment.json): idempotent
`install` (`scripts/cloud-install.sh`) creates `.venv` and installs deps; the
`worker` terminal runs `python -m app --dry-run`.
