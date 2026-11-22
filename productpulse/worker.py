import logging

from productpulse.logging_config import configure_logging


def main() -> int:
    """Expose the separate worker process entry point before job handlers exist."""

    configure_logging()
    logging.getLogger(__name__).info("worker_entrypoint_ready; no job handlers registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

