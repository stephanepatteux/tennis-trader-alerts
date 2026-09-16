# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Instead, report privately via GitHub: open the repository's **Security** tab and
use **"Report a vulnerability"**. Include steps to reproduce and the impact.

## Handling API keys

This project is designed so your keys **never** leave the server:

- `LIVE_TENNIS_API_KEY` is read from the environment at runtime and sent to Live
  Tennis API only as an `Authorization: Bearer` header when minting a WebSocket
  token.
- `TELEGRAM_BOT_TOKEN` is read from the environment and used only in the Telegram
  Bot API URL path (`/bot<token>/sendMessage`). It is never logged.
- No key (real or placeholder) is committed to this repository; `.env` is
  git-ignored. `.env.example` documents every variable with empty values.

If a key of yours is leaked, rotate it immediately (Live Tennis API dashboard
and/or @BotFather).
