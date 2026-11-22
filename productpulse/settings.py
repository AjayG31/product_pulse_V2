import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from sqlalchemy import URL


class SettingsError(ValueError):
    """Raised when required server configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Server-side settings. Operational values have no implicit defaults."""

    data_dir: Path
    sqlite_busy_timeout_ms: int
    openai_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environment is None else environment
        data_dir_value = source.get("PRODUCTPULSE_DATA_DIR", "").strip()
        timeout_value = source.get("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "").strip()
        missing = []
        if not data_dir_value:
            missing.append("PRODUCTPULSE_DATA_DIR")
        if not timeout_value:
            missing.append("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS")
        if missing:
            raise SettingsError("Required server settings are missing: " + ", ".join(missing))

        try:
            timeout_ms = int(timeout_value)
        except ValueError as error:
            raise SettingsError("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS must be a positive integer") from error
        if timeout_ms <= 0:
            raise SettingsError("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS must be a positive integer")

        return cls(
            data_dir=Path(data_dir_value).expanduser(),
            sqlite_busy_timeout_ms=timeout_ms,
            openai_api_key=source.get("PRODUCTPULSE_OPENAI_API_KEY") or None,
        )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "productpulse.sqlite3"

    @property
    def database_url(self) -> URL:
        return URL.create("sqlite", database=str(self.database_path))


def get_settings() -> Settings:
    return Settings.from_environment()

