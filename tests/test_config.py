"""Tests for .env loading (setdefault, no override of real env)."""

import os
from pathlib import Path

from app.config import load_dotenv


def test_load_dotenv_sets_missing_and_does_not_override(tmp_path: Path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text(
        "LIVE_TENNIS_API_KEY=from-file\n"
        "TELEGRAM_BOT_TOKEN=file-token\n"
        "# comment\n"
        "LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LIVE_TENNIS_API_KEY", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "already-set")
    load_dotenv(envfile)
    assert os.environ["LIVE_TENNIS_API_KEY"] == "from-file"
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "already-set"
    assert os.environ["LOG_LEVEL"] == "DEBUG"
