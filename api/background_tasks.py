"""
Background Task Processing for SQLite Mode

This module provides background task processing capabilities when using SQLite.
Since SQLite doesn't support the surreal-commands worker, we use FastAPI's
BackgroundTasks to process jobs within the API server process.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

from open_notebook.database.repository_factory import (
    get_database_type,
    repo_create,
    repo_query,
    repo_update,
)
from open_notebook.domain.transformation import Transformation
from open_notebook.graphs.source import source_graph


async def _ensure_command_table():
    """Ensure the command table exists in SQLite"""
    db_type = get_database_type()
    if db_type != "sqlite":
        return  # Only needed for SQLite

    try:
        # Try to query the command table
        await repo_query("SELECT 1 FROM command LIMIT 1", {})
    except Exception:
        # Table doesn't exist, create it
        logger.info("Creating command table for SQLite")
        from open_notebook.database.repository_factory import db_connection

        async with db_connection() as conn:
            import asyncio

            create_table_sql = """
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
            await asyncio.to_thread(conn.execute, create_table_sql)
            await asyncio.to_thread(conn.commit)
        logger.info("Command table created successfully")


async def create_command_record(
    app: str,
    command_name: str,
    input_data: Dict[str, Any],
) -> str:
    """Create a command record in the database for tracking"""
    # Ensure command table exists (SQLite only)
    await _ensure_command_table()

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


async def update_command_status(
    command_id: str,
    status: str,
    progress: int = None,
    result: Dict[str, Any] = None,
    error_message: str = None,
):
    """Update command status in the database"""
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


async def process_source_background(
    command_id: str,
    source_id: str,
    content_state: Dict[str, Any],
    notebook_ids: List[str],
    transformation_ids: List[str],
    embed: bool,
):
    """
    Background task to process a source using the source_graph.

    This runs in a FastAPI background task thread, updating the command
    record as it progresses so clients can poll for status.
    """
    start_time = time.time()

    try:
        logger.info(f"Starting background processing for source: {source_id}")

        # Update status to running
        await update_command_status(command_id, "running", progress=10)

        # Load transformation objects from IDs
        transformations = []
        for trans_id in transformation_ids:
            transformation = await Transformation.get(trans_id)
            if not transformation:
                raise ValueError(f"Transformation '{trans_id}' not found")
            transformations.append(transformation)

        logger.info(f"Loaded {len(transformations)} transformations")
        await update_command_status(command_id, "running", progress=20)

        # Execute source_graph
        logger.info("Executing source_graph...")
        result = await source_graph.ainvoke(
            {
                "content_state": content_state,
                "notebook_ids": notebook_ids,
                "apply_transformations": transformations,
                "embed": embed,
                "source_id": source_id,
            }
        )

        await update_command_status(command_id, "running", progress=80)

        processed_source = result["source"]

        # Gather results
        embedded_chunks = await processed_source.get_embedded_chunks() if embed else 0
        insights_list = await processed_source.get_insights()
        insights_created = len(insights_list)

        processing_time = time.time() - start_time

        # Update command with success result
        result_data = {
            "success": True,
            "source_id": str(processed_source.id),
            "embedded_chunks": embedded_chunks,
            "insights_created": insights_created,
            "processing_time": processing_time,
            "execution_metadata": {
                "started_at": datetime.fromtimestamp(start_time).isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            },
        }

        await update_command_status(
            command_id,
            "completed",
            progress=100,
            result=result_data,
        )

        logger.info(
            f"✅ Background processing completed for source {source_id} in {processing_time:.2f}s"
        )

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Background processing failed for source {source_id}: {e}")
        logger.exception(e)

        # Update command with error
        result_data = {
            "success": False,
            "source_id": source_id,
            "processing_time": processing_time,
            "error_message": str(e),
            "execution_metadata": {
                "started_at": datetime.fromtimestamp(start_time).isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            },
        }

        await update_command_status(
            command_id,
            "failed",
            result=result_data,
            error_message=str(e),
        )


async def get_command_status_from_db(command_id: str) -> Dict[str, Any]:
    """Get command status from database (for SQLite mode)"""
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
