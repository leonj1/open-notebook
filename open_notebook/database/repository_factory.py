"""
Repository Factory

This module provides a factory for creating repository instances.
It allows switching between SurrealDB and SQLite implementations
based on environment variables.

Environment Variables:
    DB_TYPE: Database type - 'surrealdb' (default) or 'sqlite'
    SQLITE_URL: SQLite database URL (when DB_TYPE=sqlite)
    SURREAL_URL: SurrealDB URL (when DB_TYPE=surrealdb)
"""

import os
from typing import Literal

DatabaseType = Literal["surrealdb", "sqlite"]


def get_database_type() -> DatabaseType:
    """Get the configured database type from environment"""
    db_type = os.getenv("DB_TYPE", "surrealdb").lower()

    if db_type not in ["surrealdb", "sqlite"]:
        raise ValueError(f"Invalid DB_TYPE: {db_type}. Must be 'surrealdb' or 'sqlite'")

    return db_type  # type: ignore


def get_repository_module():
    """
    Get the appropriate repository module based on DB_TYPE environment variable.

    Returns:
        module: Either open_notebook.database.repository (SurrealDB)
                or open_notebook.database.sqlite_repository (SQLite)
    """
    db_type = get_database_type()

    if db_type == "sqlite":
        from open_notebook.database import sqlite_repository
        return sqlite_repository
    else:
        from open_notebook.database import repository
        return repository


# Export all repository functions through the factory
# This allows code to import from repository_factory and get the correct implementation

_repo = get_repository_module()

# Re-export all public functions
repo_query = _repo.repo_query
repo_create = _repo.repo_create
repo_relate = _repo.repo_relate
repo_upsert = _repo.repo_upsert
repo_update = _repo.repo_update
repo_delete = _repo.repo_delete
repo_insert = _repo.repo_insert
repo_ensure_table = _repo.repo_ensure_table
parse_record_ids = _repo.parse_record_ids
ensure_record_id = _repo.ensure_record_id

# Export connection manager
db_connection = _repo.db_connection

# Try to export repo_get_news_by_jota_id if it exists
try:
    repo_get_news_by_jota_id = _repo.repo_get_news_by_jota_id
except AttributeError:
    # Not all repositories may have this function
    pass
