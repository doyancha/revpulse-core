"""
Pytest configuration and global fixtures for RevPulse test suite.
Ensures clean database state across test executions.
"""

import pytest
from sqlmodel import SQLModel
from src.database.db import engine, init_db


@pytest.fixture(autouse=True)
def clean_database():
    """Ensures database tables are initialized and clean for every test."""
    init_db()
    with engine.connect() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
    yield
    with engine.connect() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
