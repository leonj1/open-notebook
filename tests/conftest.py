"""
Pytest configuration file.

This file ensures that the project root is in the Python path,
allowing tests to import from the api and open_notebook modules.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Ensure password auth is disabled for tests
# The PasswordAuthMiddleware skips auth when this env var is not set
if "OPEN_NOTEBOOK_PASSWORD" in os.environ:
    del os.environ["OPEN_NOTEBOOK_PASSWORD"]


@pytest_asyncio.fixture(autouse=True)
async def cleanup_connection_pool():
    """
    Cleanup fixture that ensures the SQLite connection pool is properly
    closed after each test to prevent event loop issues.

    This fixture runs automatically after every test (autouse=True).
    It ensures that background tasks and connections from the previous
    test don't interfere with the next test's event loop.
    """
    yield  # Let the test run

    # After the test completes, clean up all connection pools
    try:
        from open_notebook.database.sqlite_repository import close_connection_pool
        await close_connection_pool()
    except Exception:
        # If cleanup fails, continue anyway - the next test will reinitialize
        pass
