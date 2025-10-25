"""
SQLite Repository Implementation

This module provides a SQLite implementation of the repository interface
that mirrors the SurrealDB repository in repository.py.

Environment Variables:
    SQLITE_URL: Connection string for SQLite database (e.g., "sqlite:///./data/notebook.db")
"""

import asyncio
import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger


def get_sqlite_url() -> str:
    """Get SQLite database URL from environment variable"""
    sqlite_url = os.getenv("SQLITE_URL", "sqlite:///./data/notebook.db")
    # Remove sqlite:// or sqlite:/// prefix to get file path
    if sqlite_url.startswith("sqlite:///"):
        return sqlite_url[10:]  # Remove sqlite:///
    elif sqlite_url.startswith("sqlite://"):
        return sqlite_url[9:]  # Remove sqlite://
    return sqlite_url


def parse_record_ids(obj: Any) -> Any:
    """
    Recursively parse and convert RecordIDs into strings.
    In SQLite, we just ensure consistent string format.
    """
    if isinstance(obj, dict):
        return {k: parse_record_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [parse_record_ids(item) for item in obj]
    return obj


def ensure_record_id(value: Union[str, Any]) -> str:
    """
    Ensure a value is a valid record ID string.
    For SQLite, we just ensure it's a string format: "table:id"
    """
    if isinstance(value, str):
        return value
    return str(value)


def generate_id(table: str) -> str:
    """Generate a unique ID in SurrealDB format: table:uuid"""
    return f"{table}:{uuid.uuid4().hex[:16]}"


def parse_surreal_query(query_str: str, vars: Optional[Dict[str, Any]] = None) -> tuple[str, Dict[str, Any]]:
    """
    Parse a SurrealQL query and convert it to SQL.
    This is a simplified parser that handles common patterns.
    For complex queries, we'll need to extend this.
    """
    # This is a basic implementation - you may need to extend based on actual queries used
    vars = vars or {}

    # Handle simple SELECT queries
    if query_str.strip().upper().startswith("SELECT"):
        # Replace SurrealDB syntax with SQLite syntax
        sql = query_str

        # Replace $variable references with ? placeholders
        # We'll need to track the order for positional parameters
        # For now, we'll use named parameters (:varname)
        for var_name in vars.keys():
            sql = sql.replace(f"${var_name}", f":{var_name}")

        return sql, vars

    return query_str, vars


@asynccontextmanager
async def db_connection():
    """
    Async context manager for SQLite database connections.
    SQLite doesn't have native async support, so we use asyncio.to_thread for I/O.
    """
    db_path = get_sqlite_url()

    # Ensure directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Connect to database
    # Set check_same_thread=False to allow usage across threads with asyncio.to_thread
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    # Enforce foreign keys and improve busy handling
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")

    try:
        # Initialize schema if needed
        await _initialize_schema(conn)
        yield conn
    finally:
        conn.close()


async def _initialize_schema(conn: sqlite3.Connection):
    """Initialize database schema if not exists"""
    schema_path = Path(__file__).parent / "sqlite_schema.sql"

    if schema_path.exists():
        schema_sql = schema_path.read_text()
        await asyncio.to_thread(conn.executescript, schema_sql)
        await asyncio.to_thread(conn.commit)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert SQLite Row to dictionary"""
    result = {}
    for key in row.keys():
        value = row[key]
        # Parse JSON fields
        if key in ['topics', 'embedding'] and value:
            try:
                result[key] = json.loads(value) if isinstance(value, str) else value
            except (json.JSONDecodeError, TypeError):
                result[key] = value
        # Handle asset object reconstruction
        elif key in ['asset_file_path', 'asset_url']:
            if 'asset' not in result:
                result['asset'] = {}
            if key == 'asset_file_path' and value:
                result['asset']['file_path'] = value
            elif key == 'asset_url' and value:
                result['asset']['url'] = value
        else:
            result[key] = value

    # Remove asset fields that were merged into asset object
    result.pop('asset_file_path', None)
    result.pop('asset_url', None)

    # If asset is empty, set to None
    if 'asset' in result and not result['asset']:
        result['asset'] = None

    return result


async def repo_query(
    query_str: str, vars: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Execute a SQL query and return the results"""

    async with db_connection() as conn:
        try:
            # For simple queries, execute directly
            # For complex SurrealQL, we may need translation

            cursor = await asyncio.to_thread(
                conn.execute,
                query_str,
                vars or {}
            )
            rows = await asyncio.to_thread(cursor.fetchall)

            return parse_record_ids([_row_to_dict(row) for row in rows])
        except Exception as e:
            logger.error(f"Query: {query_str[:200]} vars: {vars}")
            logger.exception(e)
            raise


async def repo_create(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new record in the specified table"""
    data = data.copy()
    data.pop("id", None)  # Remove id if present

    # Generate ID
    record_id = generate_id(table)
    data["id"] = record_id

    # Add timestamps
    now = datetime.now(timezone.utc).isoformat()
    data["created"] = now
    data["updated"] = now

    try:
        async with db_connection() as conn:
            # Handle special fields
            insert_data = _prepare_data_for_insert(table, data)

            # Build INSERT query
            columns = list(insert_data.keys())
            placeholders = [f":{col}" for col in columns]

            sql = f"""
                INSERT INTO {table} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
            """

            await asyncio.to_thread(conn.execute, sql, insert_data)
            await asyncio.to_thread(conn.commit)

            # Fetch and return the created record
            cursor = await asyncio.to_thread(
                conn.execute,
                f"SELECT * FROM {table} WHERE id = :id",
                {"id": record_id}
            )
            row = await asyncio.to_thread(cursor.fetchone)

            if row:
                return parse_record_ids(_row_to_dict(row))
            else:
                raise RuntimeError("Failed to retrieve created record")

    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to create record: {str(e)}")


def _prepare_data_for_insert(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare data for insertion by handling special types"""
    prepared = {}

    for key, value in data.items():
        # Handle JSON fields
        if key in ['topics', 'embedding', 'speakers'] and value is not None:
            if isinstance(value, (list, dict)):
                prepared[key] = json.dumps(value)
            else:
                prepared[key] = value
        # Handle nested asset object
        elif key == 'asset' and value is not None:
            if isinstance(value, dict):
                prepared['asset_file_path'] = value.get('file_path')
                prepared['asset_url'] = value.get('url')
        # Handle boolean fields
        elif key in ['archived', 'is_built_in'] and value is not None:
            prepared[key] = 1 if value else 0
        else:
            prepared[key] = value

    return prepared


async def repo_relate(
    source: str, relationship: str, target: str, data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Create a relationship between two records with optional data"""
    if data is None:
        data = {}

    relation_id = generate_id(relationship)
    now = datetime.now(timezone.utc).isoformat()

    # Prepare relationship record
    rel_data = {
        "id": relation_id,
        "in": source,
        "out": target,
        "created": now,
        "updated": now,
        **data
    }

    try:
        async with db_connection() as conn:
            # Build INSERT query for relationship table
            # Need to quote 'in' and 'out' as they are SQL keywords
            columns = [f'"{col}"' if col in ['in', 'out'] else col for col in rel_data.keys()]
            placeholders = [f":{col}" for col in rel_data.keys()]

            sql = f"""
                INSERT OR REPLACE INTO {relationship} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
            """

            await asyncio.to_thread(conn.execute, sql, rel_data)
            await asyncio.to_thread(conn.commit)

            # Return the relationship record
            cursor = await asyncio.to_thread(
                conn.execute,
                f"SELECT * FROM {relationship} WHERE id = :id",
                {"id": relation_id}
            )
            row = await asyncio.to_thread(cursor.fetchone)

            if row:
                return [parse_record_ids(_row_to_dict(row))]
            return []

    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to create relationship: {str(e)}")


async def repo_upsert(
    table: str, id: Optional[str], data: Dict[str, Any], add_timestamp: bool = False
) -> List[Dict[str, Any]]:
    """Create or update a record in the specified table"""
    data = data.copy()
    data.pop("id", None)

    if add_timestamp:
        data["updated"] = datetime.now(timezone.utc).isoformat()

    record_id = id if id else generate_id(table)
    data["id"] = record_id

    try:
        async with db_connection() as conn:
            # Check if record exists
            cursor = await asyncio.to_thread(
                conn.execute,
                f"SELECT id FROM {table} WHERE id = :id",
                {"id": record_id}
            )
            exists = await asyncio.to_thread(cursor.fetchone)

            if exists:
                # Update
                return await repo_update(table, record_id, data)
            else:
                # Create
                if "created" not in data:
                    data["created"] = datetime.now(timezone.utc).isoformat()
                if "updated" not in data:
                    data["updated"] = datetime.now(timezone.utc).isoformat()

                result = await repo_create(table, data)
                return [result]

    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to upsert record: {str(e)}")


async def repo_update(
    table: str, id: str, data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Update an existing record by table and id"""
    try:
        # Parse record ID
        if ":" in id and not id.startswith(f"{table}:"):
            # ID contains table prefix but for different table
            table_from_id = id.split(":")[0]
            record_id = id
            table = table_from_id
        elif ":" in id:
            record_id = id
        else:
            record_id = f"{table}:{id}"

        data = data.copy()
        data.pop("id", None)

        # Handle created field
        if "created" in data and isinstance(data["created"], str):
            # Keep as is
            pass

        # Update timestamp
        data["updated"] = datetime.now(timezone.utc).isoformat()

        async with db_connection() as conn:
            # Prepare data
            update_data = _prepare_data_for_insert(table, data)

            # Build UPDATE query
            set_clauses = [f"{col} = :{col}" for col in update_data.keys()]
            sql = f"""
                UPDATE {table}
                SET {', '.join(set_clauses)}
                WHERE id = :record_id
            """

            update_data["record_id"] = record_id

            await asyncio.to_thread(conn.execute, sql, update_data)
            await asyncio.to_thread(conn.commit)

            # Fetch and return updated record
            cursor = await asyncio.to_thread(
                conn.execute,
                f"SELECT * FROM {table} WHERE id = :id",
                {"id": record_id}
            )
            row = await asyncio.to_thread(cursor.fetchone)

            if row:
                return [parse_record_ids(_row_to_dict(row))]
            return []

    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to update record: {str(e)}")


async def repo_delete(record_id: Union[str, Any]):
    """Delete a record by record id"""
    try:
        record_id = ensure_record_id(record_id)

        # Parse table name from record_id
        if ":" not in record_id:
            raise ValueError(f"Invalid record ID format: {record_id}")

        table, _ = record_id.split(":", 1)

        async with db_connection() as conn:
            sql = f"DELETE FROM {table} WHERE id = :id"
            await asyncio.to_thread(conn.execute, sql, {"id": record_id})
            await asyncio.to_thread(conn.commit)

            return True

    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to delete record: {str(e)}")


async def repo_insert(
    table: str, data: List[Dict[str, Any]], ignore_duplicates: bool = False
) -> List[Dict[str, Any]]:
    """Insert multiple records into the specified table"""
    try:
        results = []

        for item in data:
            try:
                result = await repo_create(table, item)
                results.append(result)
            except sqlite3.IntegrityError:
                if ignore_duplicates:
                    continue
                raise

        return parse_record_ids(results)

    except Exception as e:
        if ignore_duplicates:
            return []
        logger.exception(e)
        raise RuntimeError(f"Failed to insert records: {str(e)}")


async def repo_get_news_by_jota_id(jota_id: str) -> Dict[str, Any]:
    """Specialized query for news by jota_id"""
    try:
        results = await repo_query(
            "SELECT * FROM news WHERE jota_id = :jota_id",
            {"jota_id": jota_id},
        )
        return parse_record_ids(results)
    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to fetch record: {str(e)}")
