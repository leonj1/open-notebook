"""
Pytest configuration file for SQLite testing.

This file configures the test environment to use SQLite instead of SurrealDB.
It patches the repository imports to use SQLite implementation.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set environment variables for SQLite before any imports
os.environ["DB_TYPE"] = "sqlite"

# Use a temporary database for tests
test_db_file = tempfile.mktemp(suffix=".db", prefix="test_notebook_")
os.environ["SQLITE_URL"] = f"sqlite:///{test_db_file}"

# Ensure password auth is disabled for tests
if "OPEN_NOTEBOOK_PASSWORD" in os.environ:
    del os.environ["OPEN_NOTEBOOK_PASSWORD"]


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment before all tests"""
    print(f"\n{'='*60}")
    print("SQLite Test Configuration")
    print(f"{'='*60}")
    print(f"DB_TYPE: {os.getenv('DB_TYPE')}")
    print(f"SQLITE_URL: {os.getenv('SQLITE_URL')}")
    print(f"Test database: {test_db_file}")
    print(f"{'='*60}\n")

    yield

    # Cleanup after all tests
    if os.path.exists(test_db_file):
        try:
            os.remove(test_db_file)
            print(f"\n✓ Cleaned up test database: {test_db_file}")
        except Exception as e:
            print(f"\n✗ Failed to cleanup test database: {e}")


@pytest.fixture(autouse=True)
async def reset_database():
    """Reset database state before each test"""
    # Import here to ensure environment variables are set
    from open_notebook.database import sqlite_repository

    async with sqlite_repository.db_connection() as conn:
        import asyncio
        # Get list of all tables
        cursor = await asyncio.to_thread(
            conn.execute,
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = await asyncio.to_thread(cursor.fetchall)

        # Delete all data from tables (but keep schema)
        for table_row in tables:
            table_name = table_row[0]
            # Skip FTS tables - they'll be cleared when main tables are cleared
            if not table_name.endswith('_fts'):
                await asyncio.to_thread(conn.execute, f"DELETE FROM {table_name}")

        await asyncio.to_thread(conn.commit)

    yield
