from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from productpulse.database import create_database_engine
from productpulse.models import Base
from productpulse.settings import Settings, get_settings


def get_engine(request: Request):
    engine = getattr(request.app.state, "database_engine", None)
    if engine is not None:
        return engine

    lock = request.app.state.database_lock
    with lock:
        engine = getattr(request.app.state, "database_engine", None)
        if engine is None:
            settings: Settings = request.app.state.settings or get_settings()
            engine = create_database_engine(settings)
            request.app.state.database_engine = engine
    return engine


def get_db(request: Request) -> Generator[Session, None, None]:
    engine = get_engine(request)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def create_schema_for_tests(request: Request) -> None:
    """Create tables only for isolated tests; production schema changes use Alembic."""

    Base.metadata.create_all(get_engine(request))

