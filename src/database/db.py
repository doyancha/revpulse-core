"""
SQLModel database connection and session management for RevPulse.
Supports PostgreSQL with automatic, resilient fallback to SQLite.
"""

import logging
from typing import Generator
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.exc import OperationalError

from config.settings import DATABASE_URL

logger = logging.getLogger("revpulse.database")


def get_db_engine(db_url: str):
    """
    Creates SQLModel engine.
    If PostgreSQL connection fails, falls back safely to local SQLite.
    """
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    try:
        engine = create_engine(db_url, echo=False, connect_args=connect_args)
        # Test connection
        with engine.connect() as conn:
            pass
        return engine
    except (OperationalError, Exception) as e:
        logger.warning(
            f"Unable to connect to primary database '{db_url}': {e}. Falling back to SQLite ('sqlite:///./revpulse.db')."
        )
        fallback_url = "sqlite:///./revpulse.db"
        return create_engine(
            fallback_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )


engine = get_db_engine(DATABASE_URL)


def init_db() -> None:
    """Initializes database schema, creating all tables defined in SQLModel metadata."""
    import src.database.models  # Ensure models are imported so metadata is populated
    SQLModel.metadata.create_all(engine)

    # Resilient migration check for existing SQLite table schemas
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(audit_logs);")).fetchall()
            if res:
                col_names = [row[1] for row in res]
                if "doc_number" not in col_names:
                    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN doc_number VARCHAR;"))
                    conn.commit()
    except Exception as e:
        logger.debug(f"Schema migration check bypassed: {e}")

    logger.info("RevPulse SQLModel tables initialized successfully.")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions."""
    with Session(engine) as session:
        yield session
