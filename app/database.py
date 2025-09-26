from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base


engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, future=True)
db_session = scoped_session(SessionLocal)
Base = declarative_base()


def init_engine(database_url: str) -> None:
    global engine
    if engine is None:
        engine = create_engine(database_url, future=True)
    db_session.configure(bind=engine)


def init_db() -> None:
    from . import models  # noqa: F401  # ensure models are imported

    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_engine first.")

    Base.metadata.create_all(bind=engine)


def get_session() -> scoped_session:
    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_engine first.")
    return db_session