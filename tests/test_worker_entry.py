import os
import subprocess
import sys

from alembic import command
from alembic.config import Config


def test_worker_entry_uses_configured_database_without_provider_key(tmp_path):
    data_dir = tmp_path / "shared-data"
    data_dir.mkdir()
    environment = os.environ.copy()
    environment.pop("PRODUCTPULSE_OPENAI_API_KEY", None)
    environment["PRODUCTPULSE_DATA_DIR"] = str(data_dir)
    environment["PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS"] = "5000"

    previous_data_dir = os.environ.get("PRODUCTPULSE_DATA_DIR")
    previous_timeout = os.environ.get("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS")
    os.environ["PRODUCTPULSE_DATA_DIR"] = str(data_dir)
    os.environ["PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS"] = "5000"
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_data_dir is None:
            os.environ.pop("PRODUCTPULSE_DATA_DIR", None)
        else:
            os.environ["PRODUCTPULSE_DATA_DIR"] = previous_data_dir
        if previous_timeout is None:
            os.environ.pop("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", None)
        else:
            os.environ["PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS"] = previous_timeout

    result = subprocess.run(
        [sys.executable, "-m", "productpulse.worker", "--once"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )

    assert result.returncode == 0
    assert "worker_poll_complete; reconciliation handlers registered" in result.stderr
    assert "worker_configuration_invalid" not in result.stderr
    assert "Traceback" not in result.stderr
