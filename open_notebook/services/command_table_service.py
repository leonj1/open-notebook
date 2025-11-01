"""
Command Table Service

This service class handles database schema initialization for the command table.
It provides a clean interface for ensuring the command table exists before use.
"""

from open_notebook.database.repository_factory import repo_ensure_table


class CommandTableService:
    """
    Service for managing the command table schema.

    This service ensures the command table exists in the database with the correct
    schema. It works across different database backends (SQLite, SurrealDB) by
    delegating to the repository layer.
    """

    # SQL schema definition for the command table
    COMMAND_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS command (
        id TEXT PRIMARY KEY,
        app TEXT NOT NULL,
        command TEXT NOT NULL,
        status TEXT NOT NULL,
        input TEXT,
        result TEXT,
        error_message TEXT,
        progress INTEGER DEFAULT 0,
        created TEXT NOT NULL,
        updated TEXT NOT NULL
    )
    """

    @classmethod
    async def ensure_table(cls) -> None:
        """
        Ensure the command table exists without relying on pre-query.

        Using CREATE TABLE IF NOT EXISTS is idempotent and avoids OperationalError logs
        from querying a non-existent table during startup or first use.

        For SurrealDB, this is a no-op since tables are created automatically.
        For SQLite, this creates the table if it doesn't exist.

        Raises:
            Exception: If the table creation fails
        """
        await repo_ensure_table("command", cls.COMMAND_TABLE_SQL)
