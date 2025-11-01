"""
Command Table Service

This service class handles database schema initialization and CRUD operations
for the command table. It provides a clean interface for managing command records
used in background task processing.
"""

import json
from datetime import datetime
from typing import Any, Dict

from loguru import logger

from open_notebook.database.repository_factory import (
    get_database_type,
    repo_create,
    repo_ensure_table,
    repo_query,
    repo_update,
)


class CommandTableService:
    """
    Service for managing the command table schema and operations.

    This service provides a complete interface for:
    - Ensuring the command table exists in the database
    - Creating command records for tracking background tasks
    - Updating command status and progress
    - Retrieving command status from the database

    Works across different database backends (SQLite, SurrealDB) by
    delegating to the repository layer and handling database-specific
    serialization (e.g., JSON serialization for SQLite).
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

    @classmethod
    async def create_command_record(
        cls,
        app: str,
        command_name: str,
        input_data: Dict[str, Any],
    ) -> str:
        """
        Create a command record in the database for tracking.

        Args:
            app: Application name (e.g., "open_notebook")
            command_name: Command being executed (e.g., "process_source")
            input_data: Input parameters for the command

        Returns:
            str: The created command ID

        Note:
            - Automatically ensures the command table exists before creating
            - For SQLite: serializes dict fields to JSON strings
            - For SurrealDB: stores dict fields as native objects
        """
        # Ensure command table exists (SQLite only)
        await cls.ensure_table()

        # For SQLite, serialize dict fields to JSON strings
        db_type = get_database_type()
        if db_type == "sqlite":
            input_json = json.dumps(input_data)
            result_json = None
            error_message_json = None
        else:
            input_json = input_data
            result_json = None
            error_message_json = None

        command_record = {
            # Don't set 'id' here - repo_create will generate it
            "app": app,
            "command": command_name,
            "status": "queued",
            "input": input_json,
            "result": result_json,
            "error_message": error_message_json,
            "progress": 0,
            "created": datetime.utcnow().isoformat(),
            "updated": datetime.utcnow().isoformat(),
        }

        # repo_create returns the created record with its generated id
        created_record = await repo_create("command", command_record)
        command_id = created_record["id"]
        logger.info(f"Created command record: {command_id}")
        return command_id

    @classmethod
    async def update_command_status(
        cls,
        command_id: str,
        status: str,
        progress: int = None,
        result: Dict[str, Any] = None,
        error_message: str = None,
    ) -> None:
        """
        Update command status in the database.

        Args:
            command_id: ID of the command to update
            status: New status (e.g., "queued", "running", "completed", "failed")
            progress: Optional progress percentage (0-100)
            result: Optional result data dict
            error_message: Optional error message string

        Note:
            - For SQLite: serializes result dict to JSON string
            - For SurrealDB: stores result as native object
        """
        update_data = {
            "status": status,
            "updated": datetime.utcnow().isoformat(),
        }

        # For SQLite, serialize dict fields to JSON
        db_type = get_database_type()

        if progress is not None:
            update_data["progress"] = progress
        if result is not None:
            update_data["result"] = json.dumps(result) if db_type == "sqlite" else result
        if error_message is not None:
            update_data["error_message"] = error_message

        # repo_update requires: table, id, data
        await repo_update("command", command_id, update_data)
        logger.debug(f"Updated command {command_id}: status={status}")

    @classmethod
    async def get_command_status(cls, command_id: str) -> Dict[str, Any]:
        """
        Get command status from database.

        Args:
            command_id: ID of the command to retrieve

        Returns:
            Dict containing:
                - job_id: The command ID
                - status: Current status
                - result: Result data (deserialized from JSON if SQLite)
                - error_message: Error message if failed
                - created: Creation timestamp
                - updated: Last update timestamp
                - progress: Progress percentage

        Raises:
            ValueError: If command not found
        """
        query = "SELECT * FROM command WHERE id = $command_id"
        results = await repo_query(query, {"command_id": command_id})

        if not results or len(results) == 0:
            raise ValueError(f"Command {command_id} not found")

        command = results[0]

        # For SQLite, deserialize JSON fields
        db_type = get_database_type()
        result_data = command.get("result")
        if db_type == "sqlite" and result_data and isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except json.JSONDecodeError:
                pass

        return {
            "job_id": command["id"],
            "status": command.get("status", "unknown"),
            "result": result_data,
            "error_message": command.get("error_message"),
            "created": command.get("created"),
            "updated": command.get("updated"),
            "progress": command.get("progress"),
        }
