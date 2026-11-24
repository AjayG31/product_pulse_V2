"""Separate, single-process entry point for the durable SQLite worker."""

import argparse
import logging
import signal
import threading

from productpulse.database import create_database_engine
from productpulse.logging_config import configure_logging
from productpulse.linkage_reconciliation import reconciliation_registration
from productpulse.settings import SettingsError, get_settings
from productpulse.worker_runtime import WorkerRuntime


LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ProductPulse background worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="perform startup reconciliation and one poll cycle, then exit",
    )
    args = parser.parse_args(argv)

    configure_logging()
    try:
        settings = get_settings()
    except SettingsError:
        LOGGER.error("worker_configuration_invalid; required database settings are unavailable")
        return 2

    engine = create_database_engine(settings)
    runtime = WorkerRuntime(engine, handlers={"RECONCILIATION": reconciliation_registration(engine)})
    stop_event = threading.Event()
    if not args.once:
        signal.signal(signal.SIGINT, lambda _signum, _frame: stop_event.set())
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop_event.set())

    try:
        if args.once:
            runtime.run_once()
            LOGGER.info("worker_poll_complete; reconciliation handlers registered")
        else:
            LOGGER.info("worker_started; reconciliation handler registered; unsupported work remains queued")
            runtime.run_forever(stop_event)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
