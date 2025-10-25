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
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger


# Regex for valid SQL identifiers (letters, digits, underscores)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """
    Validate and return a SQL identifier to prevent SQL injection.

    Args:
        name: The identifier to validate (table name, column name, etc.)

    Returns:
        The validated identifier

    Raises:
        ValueError: If the identifier is invalid
    """
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


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
    Parse a SurrealQL query and convert it to SQLite.

    Handles common SurrealQL patterns:
    - SELECT * FROM $id / SELECT * FROM ONLY $id
    - omit field.subfield (excludes fields from results)
    - fetch field (resolves record IDs - handled at application layer)
    - CREATE table CONTENT {...} (converts to INSERT)
    - DELETE table WHERE condition
    - fn::text_search/vector_search (converts to SQLite equivalents)
    - $variable substitution (converts to :variable)
    """
    import re

    vars = vars or {}
    sql = query_str.strip()

    # Replace $variable references with :variable for named parameters
    for var_name in vars.keys():
        sql = re.sub(rf'\${re.escape(var_name)}\b', f':{var_name}', sql)

    # Handle CREATE table CONTENT {...}
    if re.match(r'CREATE\s+\w+\s+CONTENT\s*\{', sql, re.IGNORECASE):
        # This pattern is used for inserts with JSON content
        # We'll delegate to the repo_create function instead
        # Return a marker that the caller should use repo_create
        return "__USE_REPO_CREATE__", vars

    # Handle DELETE table WHERE condition
    delete_match = re.match(r'DELETE\s+(\w+)\s+WHERE\s+(.+)', sql, re.IGNORECASE)
    if delete_match:
        table = delete_match.group(1)
        condition = delete_match.group(2)
        sql = f"DELETE FROM {table} WHERE {condition}"
        return sql, vars

    # Handle SELECT * FROM ONLY $record_id
    # ONLY keyword means: if $record_id is a single record, return it; if it's an array, return error
    # For SQLite, we'll just treat it as a regular SELECT since we're always selecting single records
    sql = re.sub(r'\bFROM\s+ONLY\s+', 'FROM ', sql, flags=re.IGNORECASE)

    # Handle SELECT * FROM $id (where $id is a record ID like "table:uuid")
    # In SurrealDB, this queries the record by ID directly
    # In SQLite, we need to extract table and use WHERE id = :id
    # This is handled at runtime in repo_query

    # Handle omit clause: "select * omit field1, field2.subfield from ..."
    # SurrealDB omit excludes fields from results
    # For SQLite, we need to either:
    # 1. Select all fields except omitted ones (complex for nested fields)
    # 2. Return all fields and filter at application layer (simpler)
    # We'll use approach #2 - mark omitted fields for post-processing
    omit_pattern = r'\s+omit\s+([\w.,\s]+?)(?=\s+from\s+|\s+$)'
    omit_match = re.search(omit_pattern, sql, re.IGNORECASE)
    omit_fields = []
    if omit_match:
        omit_fields_str = omit_match.group(1)
        omit_fields = [f.strip() for f in omit_fields_str.split(',')]
        # Remove omit clause from SQL
        sql = re.sub(omit_pattern, '', sql, flags=re.IGNORECASE)

    # Handle fetch clause: "fetch field1, field2"
    # SurrealDB fetch resolves record IDs to their full records
    # This requires JOINs in SQLite, which is complex for nested queries
    # We'll mark fetch fields for post-processing at application layer
    fetch_pattern = r'\s+fetch\s+([\w.,\s]+?)(?=\s+from\s+|\s+order\s+|\s+limit\s+|\s+$|\))'
    fetch_match = re.search(fetch_pattern, sql, re.IGNORECASE)
    fetch_fields = []
    if fetch_match:
        fetch_fields_str = fetch_match.group(1)
        fetch_fields = [f.strip() for f in fetch_fields_str.split(',')]
        # Remove fetch clause from SQL for now
        # TODO: Implement proper JOIN logic for fetch
        sql = re.sub(fetch_pattern, '', sql, flags=re.IGNORECASE)

    # Handle fn::text_search(keyword, results, source, note)
    # This is a custom SurrealDB function - needs SQLite FTS equivalent
    fts_pattern = r'fn::text_search\s*\((.*?)\)'
    if re.search(fts_pattern, sql, re.IGNORECASE):
        # For now, mark this as requiring special handling
        # Full-text search in SQLite requires FTS5 virtual tables
        return "__USE_FTS__", vars

    # Handle fn::vector_search(embedding, results, source, note, min_score)
    # This is a custom SurrealDB function - needs vector search equivalent
    vs_pattern = r'fn::vector_search\s*\((.*?)\)'
    if re.search(vs_pattern, sql, re.IGNORECASE):
        # Vector search in SQLite requires an extension like sqlite-vss
        # For now, mark this as requiring special handling
        return "__USE_VECTOR_SEARCH__", vars

    # Store omit and fetch metadata for post-processing
    if omit_fields or fetch_fields:
        # Store in vars with special keys
        if omit_fields:
            vars['__omit_fields__'] = omit_fields
        if fetch_fields:
            vars['__fetch_fields__'] = fetch_fields

    return sql, vars


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
        if key in ['topics', 'embedding', 'youtube_preferred_languages'] and value:
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


def _apply_omit_fields(data: Dict[str, Any], omit_fields: List[str]) -> Dict[str, Any]:
    """Remove omitted fields from result data"""
    result = data.copy()
    for field_path in omit_fields:
        # Handle nested fields like "source.full_text"
        parts = field_path.split('.')
        if len(parts) == 1:
            # Simple field
            result.pop(parts[0], None)
        else:
            # Nested field
            current = result
            for i, part in enumerate(parts[:-1]):
                if part in current and isinstance(current[part], dict):
                    current = current[part]
                else:
                    break
            else:
                # Successfully navigated to parent, remove final field
                current.pop(parts[-1], None)
    return result


async def _apply_fetch_fields(data: Dict[str, Any], fetch_fields: List[str]) -> Dict[str, Any]:
    """Resolve record ID references in fetch fields"""
    result = data.copy()
    for field in fetch_fields:
        if field in result:
            field_value = result[field]
            # Check if it's a record ID (format: "table:id")
            if isinstance(field_value, str) and ':' in field_value:
                # Fetch the referenced record
                try:
                    table = field_value.split(':')[0]
                    fetched = await repo_query(
                        f"SELECT * FROM {table} WHERE id = :id",
                        {"id": field_value}
                    )
                    if fetched:
                        result[field] = fetched[0]
                except Exception as e:
                    logger.warning(f"Failed to fetch {field}={field_value}: {e}")
    return result


async def repo_query(
    query_str: str, vars: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Execute a SQL query and return the results"""

    # Parse SurrealQL to SQLite
    sql, parsed_vars = parse_surreal_query(query_str, vars)

    # Extract post-processing metadata
    omit_fields = parsed_vars.pop('__omit_fields__', [])
    fetch_fields = parsed_vars.pop('__fetch_fields__', [])

    # Handle special markers
    if sql == "__USE_REPO_CREATE__":
        raise RuntimeError(
            "CREATE CONTENT queries should use repo_create() instead of repo_query(). "
            "Parse the query content and call repo_create(table, data)."
        )

    if sql == "__USE_FTS__":
        raise NotImplementedError(
            "Full-text search (fn::text_search) requires SQLite FTS5 virtual tables. "
            "This will be implemented in a future update."
        )

    if sql == "__USE_VECTOR_SEARCH__":
        raise NotImplementedError(
            "Vector search (fn::vector_search) requires a vector extension like sqlite-vss. "
            "This will be implemented in a future update."
        )

    async with db_connection() as conn:
        try:
            # Handle SELECT * FROM $id pattern (direct record lookup by ID)
            # Check if this is a simple "SELECT * FROM :var" pattern
            import re
            select_from_id = re.match(r'SELECT\s+\*\s+FROM\s+:(\w+)', sql, re.IGNORECASE)
            if select_from_id:
                var_name = select_from_id.group(1)
                record_id = parsed_vars.get(var_name)
                if record_id and isinstance(record_id, str) and ':' in record_id:
                    # Extract table from record ID
                    table = record_id.split(':')[0]
                    sql = f"SELECT * FROM {table} WHERE id = :{var_name}"

            cursor = await asyncio.to_thread(
                conn.execute,
                sql,
                parsed_vars
            )
            rows = await asyncio.to_thread(cursor.fetchall)

            results = parse_record_ids([_row_to_dict(row) for row in rows])

            # Apply post-processing
            if omit_fields:
                results = [_apply_omit_fields(row, omit_fields) for row in results]

            if fetch_fields:
                results = [await _apply_fetch_fields(row, fetch_fields) for row in results]

            return results
        except sqlite3.OperationalError as e:
            logger.exception("SQL operational error during query execution")
            logger.error(f"Query: {sql[:200]} vars: {parsed_vars}")
            raise RuntimeError("Failed to execute query (operational error)") from e
        except sqlite3.ProgrammingError as e:
            logger.exception("SQL programming error during query execution")
            logger.error(f"Query: {sql[:200]} vars: {parsed_vars}")
            raise RuntimeError("Failed to execute query (invalid SQL)") from e
        except Exception as e:
            logger.exception("Unexpected error during query execution")
            logger.error(f"Query: {sql[:200]} vars: {parsed_vars}")
            raise RuntimeError("Failed to execute query") from e


async def repo_create(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new record in the specified table"""
    # Validate table name to prevent SQL injection
    table = _validate_identifier(table)

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

            # Build INSERT query with validated identifiers
            # Validate column names to prevent SQL injection
            columns = [_validate_identifier(col) for col in insert_data.keys()]
            placeholders = [f":{col}" for col in insert_data.keys()]

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

    except sqlite3.IntegrityError as e:
        logger.exception("Integrity error creating record")
        raise RuntimeError("Failed to create record (integrity error)") from e
    except sqlite3.OperationalError as e:
        logger.exception("Operational error creating record")
        raise RuntimeError("Failed to create record (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error creating record")
        raise RuntimeError("Failed to create record") from e


def _prepare_data_for_insert(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare data for insertion by handling special types"""
    prepared = {}

    for key, value in data.items():
        # Handle JSON fields
        if key in ['topics', 'embedding', 'speakers', 'youtube_preferred_languages'] and value is not None:
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
    # Validate relationship table name to prevent SQL injection
    relationship = _validate_identifier(relationship)

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
            # Validate column names and quote 'in' and 'out' as they are SQL keywords
            columns = []
            for col in rel_data.keys():
                _validate_identifier(col)  # Validate first
                if col in ['in', 'out']:
                    columns.append(f'"{col}"')  # Quote SQL keywords
                else:
                    columns.append(col)

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

    except sqlite3.IntegrityError as e:
        logger.exception("Integrity error creating relationship")
        raise RuntimeError("Failed to create relationship (integrity error)") from e
    except sqlite3.OperationalError as e:
        logger.exception("Operational error creating relationship")
        raise RuntimeError("Failed to create relationship (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error creating relationship")
        raise RuntimeError("Failed to create relationship") from e


async def repo_upsert(
    table: str, id: Optional[str], data: Dict[str, Any], add_timestamp: bool = False
) -> List[Dict[str, Any]]:
    """Create or update a record in the specified table"""
    # Validate table name to prevent SQL injection
    table = _validate_identifier(table)

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

    except sqlite3.OperationalError as e:
        logger.exception("Operational error upserting record")
        raise RuntimeError("Failed to upsert record (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error upserting record")
        raise RuntimeError("Failed to upsert record") from e


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

        # Validate table name to prevent SQL injection
        table = _validate_identifier(table)

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

            # Build UPDATE query with validated column names
            set_clauses = [f"{_validate_identifier(col)} = :{col}" for col in update_data.keys()]
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

    except sqlite3.IntegrityError as e:
        logger.exception("Integrity error updating record")
        raise RuntimeError("Failed to update record (integrity error)") from e
    except sqlite3.OperationalError as e:
        logger.exception("Operational error updating record")
        raise RuntimeError("Failed to update record (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error updating record")
        raise RuntimeError("Failed to update record") from e


async def repo_delete(record_id: Union[str, Any]):
    """Delete a record by record id"""
    try:
        record_id = ensure_record_id(record_id)

        # Parse table name from record_id
        if ":" not in record_id:
            raise ValueError(f"Invalid record ID format: {record_id}")

        table, _ = record_id.split(":", 1)

        # Validate table name to prevent SQL injection
        table = _validate_identifier(table)

        async with db_connection() as conn:
            sql = f"DELETE FROM {table} WHERE id = :id"
            await asyncio.to_thread(conn.execute, sql, {"id": record_id})
            await asyncio.to_thread(conn.commit)

            return True

    except ValueError as e:
        logger.exception("Invalid record ID format for deletion")
        raise RuntimeError("Failed to delete record (invalid ID format)") from e
    except sqlite3.OperationalError as e:
        logger.exception("Operational error deleting record")
        raise RuntimeError("Failed to delete record (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error deleting record")
        raise RuntimeError("Failed to delete record") from e


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
            except sqlite3.IntegrityError as e:
                if ignore_duplicates:
                    continue
                raise
            except Exception as e:
                raise

        return parse_record_ids(results)

    except sqlite3.IntegrityError as e:
        if ignore_duplicates:
            return []
        logger.exception("Integrity error inserting records")
        raise RuntimeError("Failed to insert records (integrity error)") from e
    except Exception as e:
        if ignore_duplicates:
            return []
        logger.exception("Unexpected error inserting records")
        raise RuntimeError("Failed to insert records") from e


async def repo_get_news_by_jota_id(jota_id: str) -> Dict[str, Any]:
    """Specialized query for news by jota_id"""
    try:
        results = await repo_query(
            "SELECT * FROM news WHERE jota_id = :jota_id",
            {"jota_id": jota_id},
        )
        return parse_record_ids(results)
    except sqlite3.OperationalError as e:
        logger.exception("Operational error fetching news by jota_id")
        raise RuntimeError("Failed to fetch record (operational error)") from e
    except Exception as e:
        logger.exception("Unexpected error fetching news by jota_id")
        raise RuntimeError("Failed to fetch record") from e
