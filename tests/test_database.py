from sqlalchemy import text

from productpulse.database import create_database_engine
from productpulse.settings import Settings


def test_sqlite_connection_invariants_are_applied(tmp_path):
    settings = Settings(data_dir=tmp_path / "store", sqlite_busy_timeout_ms=731)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 731
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
    finally:
        engine.dispose()


def test_each_new_connection_enables_foreign_keys(tmp_path):
    settings = Settings(data_dir=tmp_path / "store", sqlite_busy_timeout_ms=250)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as first:
            assert first.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        engine.dispose()
        engine = create_database_engine(settings)
        with engine.connect() as second:
            assert second.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        engine.dispose()

