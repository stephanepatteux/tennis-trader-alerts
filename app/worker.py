"""Worker: consume the Ultra push feed and dispatch Telegram alerts."""

from __future__ import annotations

import logging
import os
import queue
import signal
import sys

from .config import ConfigError, load_dotenv, require_env
from .dispatch import Dispatcher, RateLimiter
from .notifier import LogNotifier, TelegramNotifier
from .push import PushHub, get_push_source
from .rules import RulesStore

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_notifier(*, dry_run: bool):
    if dry_run:
        log.warning("DRY-RUN: alerts will be logged, not sent to Telegram")
        return LogNotifier()
    token = require_env(
        "TELEGRAM_BOT_TOKEN",
        "Create a bot with @BotFather and put the token in .env — never commit it.",
    )
    return TelegramNotifier(
        token=token,
        api_base=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"),
        timeout=float(os.environ.get("TELEGRAM_TIMEOUT", "10")),
    )


def run(dry_run: bool = False) -> None:
    load_dotenv()
    _configure_logging()

    source = get_push_source()
    rules = RulesStore.load()
    notifier = build_notifier(dry_run=dry_run)
    dispatcher = Dispatcher(
        rules,
        notifier,
        rate_limiter=RateLimiter(
            max_events=int(os.environ.get("RATE_LIMIT_MAX", "20")),
            window_s=float(os.environ.get("RATE_LIMIT_WINDOW_S", "60")),
        ),
    )
    hub = PushHub(source_name=source.name)
    updates = hub.subscribe()
    source.start(hub)
    log.info("Connected source=%s users=%d", source.name, len(rules.users()))

    stopping = False

    def _stop(*_args):
        nonlocal stopping
        stopping = True
        source.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while not stopping:
            try:
                match = updates.get(timeout=1.0)
            except queue.Empty:
                rules.maybe_reload()
                continue
            dispatcher.handle(match)
    finally:
        source.stop()
        hub.unsubscribe(updates)
        log.info("Worker stopped")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    try:
        run(dry_run=dry_run)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    return 0
