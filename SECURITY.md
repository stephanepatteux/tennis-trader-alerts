# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Instead, report privately via GitHub: open the repository's **Security** tab and
use **"Report a vulnerability"** (Private vulnerability reporting / security
advisories). Include steps to reproduce and the impact you found.

You can expect an initial response within a few days.

## Handling API keys

This project is designed so your keys **never** leave the server:

- `LIVE_TENNIS_API_KEY` is read from the environment at runtime and sent to Live
  Tennis API only as an `Authorization: Bearer` header when minting a WebSocket
  token. It is never logged.
- `TELEGRAM_BOT_TOKEN` is read from the environment and used only in the Telegram
  Bot API URL path (`/bot<token>/…`). Failures are re-raised **without** that
  URL so a stack trace cannot leak the token. It is never written to
  `data/rules.json` or to logs.
- No key (real or placeholder) is committed to this repository; `.env` is
  git-ignored. `.env.example` documents every variable with empty values.

If you ever find a key in logs, client output, or git history, please report it
using the process above. If a key of yours is leaked, rotate it immediately
(Live Tennis API dashboard and/or @BotFather `/revoke`).

## Telegram bot access

Anyone who can message the bot can `/start` unless you set
`TELEGRAM_ALLOWED_CHATS` (or `TELEGRAM_CHAT_ID`, which is used as the allowlist
when the former is empty). Enrolled chats in `data/rules.json` keep access.
Treat the bot username as a secret if you leave the allowlist open — strangers
would consume *your* Ultra quota.
