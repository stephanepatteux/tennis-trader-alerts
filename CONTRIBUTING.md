# Contributing

Thanks for your interest in improving Tennis Trader Alerts.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

There is no demo feed — unit tests mock Ultra frames and Telegram HTTP. A real
run needs `LIVE_TENNIS_API_KEY` (Ultra) and `TELEGRAM_BOT_TOKEN`. See
[`docs/OPERATIONS.md`](docs/OPERATIONS.md) for the architecture.

## Tests

Please run the suite before opening a PR:

```bash
pytest
```

Add or update tests for any behaviour you change — alert detection, frame
mapping, rising-edge de-dup, rules filters, notifier formatting, or the bot
menu. CI runs `pytest` on every pull request.

## Guidelines

- **Never commit secrets.** No API keys — not real, not placeholder. Keep them
  in an untracked `.env`; document new variables in `.env.example`.
- Alert codes (`0-40`, `15-40`, `30-40`, `break-point`, `deuce`, `tiebreak`)
  must stay in lockstep with `app/scoring/alerts.py` (ported from the Tennis
  Trader Board).
- Do not log `LIVE_TENNIS_API_KEY`, `TELEGRAM_BOT_TOKEN`, or Bot API URLs that
  contain the token.
- Update the README / `docs/OPERATIONS.md` if you change env vars or data flow.

## Pull requests

- Branch off `main`, keep PRs focused, and describe what changed and why.
- Make sure CI is green.

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
