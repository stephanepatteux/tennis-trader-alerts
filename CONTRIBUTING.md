# Contributing

Thanks for your interest in improving Tennis Trader Alerts.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Guidelines

- **Never commit secrets.** No API keys — not real, not placeholder. Keep them
  in an untracked `.env`; document new variables in `.env.example`.
- Alert codes (`0-40`, `15-40`, `30-40`, `break-point`, `deuce`, `tiebreak`)
  must stay in lockstep with `app/scoring/alerts.py` (ported from the Tennis
  Trader Board).
- Add or update tests for alert detection, rising-edge de-dup, rules filters,
  and notifier formatting.
- Update the README / `docs/OPERATIONS.md` if you change env vars or data flow.

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
