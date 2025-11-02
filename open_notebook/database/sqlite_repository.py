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


class SQLiteConnectionPool:
    """
    Thread-safe SQLite connection pool with single-writer pattern.

    This pool manages SQLite connections to prevent database corruption from
    concurrent writes. It uses:
    - A single dedicated connection for all write operations (serialized via queue)
    - Multiple read-only connections for concurrent reads
    - WAL mode for better concurrency support

    The single-writer pattern ensures that all writes are serialized, preventing
    the "database disk image is malformed" error that occurs with concurrent writes.
    """

    def __init__(self, db_path: str, max_readers: int = 5):
        """
        Initialize the connection pool.

        Args:
            db_path: Path to the SQLite database file
            max_readers: Maximum number of concurrent read connections
        """
        self.db_path = db_path
        self.max_readers = max_readers
        self._writer_conn: Optional[sqlite3.Connection] = None
        self._reader_pool: List[sqlite3.Connection] = []
        self._write_lock = asyncio.Lock()
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._initialized = False
        self._closed = False

    async def initialize(self):
        """Initialize the connection pool and start the writer task."""
        current_loop = asyncio.get_running_loop()

        # Check if we're in a different event loop than when we were initialized
        if self._initialized and self._event_loop is not current_loop:
            logger.warning(f"Event loop changed, reinitializing connection pool")
            self._initialized = False
            self._writer_task = None
            # Create new queue for the new event loop
            self._write_queue = asyncio.Queue()

        # Check if we're already initialized and the writer task is still alive
        if self._initialized and self._writer_task and not self._writer_task.done():
            return

        # If we were initialized but the writer task died, mark as not initialized
        if self._initialized and (not self._writer_task or self._writer_task.done()):
            logger.warning("Writer task died, reinitializing connection pool")
            self._initialized = False

        if self._initialized:
            return

        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Create writer connection in a thread to avoid blocking
        def create_writer():
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level="DEFERRED"  # Use DEFERRED for schema init, will switch to None after
            )
            conn.row_factory = sqlite3.Row

            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            # NORMAL synchronous mode is safe and recommended for WAL
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            return conn

        self._writer_conn = await asyncio.to_thread(create_writer)

        # Initialize schema immediately during pool creation
        schema_path = Path(__file__).parent / "sqlite_schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text()
            # executescript handles transactions, which works well with DEFERRED mode
            await asyncio.to_thread(self._writer_conn.executescript, schema_sql)
            logger.info("Database schema initialized")

        # Now switch to autocommit mode for regular operations
        self._writer_conn.isolation_level = None

        # Start writer task and save the current event loop
        self._writer_task = asyncio.create_task(self._process_writes())
        self._event_loop = current_loop
        self._initialized = True
        logger.info(f"SQLite connection pool initialized with WAL mode at {self.db_path}")

    async def _process_writes(self):
        """Background task that processes all write operations sequentially."""
        while not self._closed:
            try:
                # Wait for a write operation (with timeout to check _closed)
                try:
                    operation = await asyncio.wait_for(
                        self._write_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                func, args, kwargs, future = operation

                try:
                    # Execute the write operation
                    result = await asyncio.to_thread(func, *args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    self._write_queue.task_done()

            except Exception as e:
                logger.error(f"Error in write processor: {e}")

    async def execute_write(self, func, *args, **kwargs):
        """
        Execute a write operation through the single writer connection.

        All writes are serialized through a queue to prevent concurrent write conflicts.

        Args:
            func: Callable to execute (e.g., conn.execute, conn.executescript)
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from the write operation
        """
        if not self._initialized:
            await self.initialize()

        # Get the current event loop
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._write_queue.put((func, args, kwargs, future))

        # Wait for the result with a timeout
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Write operation timed out after 30 seconds")
            raise RuntimeError("Database write operation timed out")

    async def get_reader_connection(self) -> sqlite3.Connection:
        """
        Get a read-only connection from the pool.

        Returns:
            A SQLite connection configured for reading
        """
        if not self._initialized:
            await self.initialize()

        # For now, create a new reader each time
        # TODO: Implement actual connection pooling for readers
        def create_reader():
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                uri=True  # Enable URI mode for better options support
            )
            conn.row_factory = sqlite3.Row

            # CRITICAL: Set these PRAGMAs in the correct order for WAL mode
            # 1. Enable WAL mode (must match writer)
            conn.execute("PRAGMA journal_mode=WAL")
            # 2. Set busy timeout to wait for locks
            conn.execute("PRAGMA busy_timeout=30000")
            # 3. Set synchronous mode for better durability with WAL
            conn.execute("PRAGMA synchronous=NORMAL")  # NORMAL is safe with WAL
            # 4. Make connection read-only
            conn.execute("PRAGMA query_only=ON")
            return conn

        return await asyncio.to_thread(create_reader)

    def get_writer_connection(self) -> sqlite3.Connection:
        """Get the dedicated writer connection (for synchronous access)."""
        if not self._initialized:
            raise RuntimeError("Pool not initialized. Call await pool.initialize() first.")
        return self._writer_conn

    async def close(self):
        """Close all connections and shut down the pool."""
        self._closed = True

        # Wait for pending writes to complete
        if self._write_queue:
            await self._write_queue.join()

        # Checkpoint WAL before closing to ensure all data is flushed to main database
        if self._writer_conn:
            try:
                await asyncio.to_thread(self._writer_conn.execute, "PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception as e:
                logger.warning(f"Failed to checkpoint WAL before closing: {e}")

        # Cancel writer task
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass

        # Close writer connection
        if self._writer_conn:
            await asyncio.to_thread(self._writer_conn.close)

        # Close reader connections
        for conn in self._reader_pool:
            await asyncio.to_thread(conn.close)

        logger.info("SQLite connection pool closed")


# Global connection pool instance (keyed by database path)
_connection_pools: Dict[str, SQLiteConnectionPool] = {}


async def get_connection_pool() -> SQLiteConnectionPool:
    """Get or create the connection pool instance for the current database."""
    db_path = get_sqlite_url()

    # Check if we have a pool for this database
    if db_path not in _connection_pools:
        pool = SQLiteConnectionPool(db_path)
        await pool.initialize()
        _connection_pools[db_path] = pool

    return _connection_pools[db_path]


async def close_connection_pool():
    """Close all connection pools."""
    global _connection_pools
    for pool in _connection_pools.values():
        await pool.close()
    _connection_pools.clear()


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
async def db_connection(read_only: bool = False):
    """
    Async context manager for SQLite database connections using the connection pool.

    This now uses the global connection pool with single-writer pattern to prevent
    database corruption from concurrent writes.

    Args:
        read_only: If True, get a read-only connection. If False, get the writer connection.

    Yields:
        A SQLite connection from the pool
    """
    pool = await get_connection_pool()

    if read_only:
        # Get a read-only connection for SELECT queries
        conn = await pool.get_reader_connection()
        try:
            yield conn
        finally:
            await asyncio.to_thread(conn.close)
    else:
        # Use the shared writer connection for all write operations
        # Schema is initialized when the pool is created
        yield pool.get_writer_connection()
        # Don't close the writer connection - it's managed by the pool


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

    async with db_connection(read_only=True) as conn:
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

        # Use connection pool for writes
        pool = await get_connection_pool()
        conn = pool.get_writer_connection()

        # Execute write through the pool's queue to serialize writes
        await pool.execute_write(conn.execute, sql, insert_data)

        # Fetch and return the created record using a read connection
        async with db_connection(read_only=True) as read_conn:
            cursor = await asyncio.to_thread(
                read_conn.execute,
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

        # Use connection pool for writes
        pool = await get_connection_pool()
        conn = pool.get_writer_connection()

        await pool.execute_write(conn.execute, sql, rel_data)

        # Return the relationship record using a read connection
        async with db_connection(read_only=True) as read_conn:
            cursor = await asyncio.to_thread(
                read_conn.execute,
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
        # Check if record exists using a read connection
        async with db_connection(read_only=True) as read_conn:
            cursor = await asyncio.to_thread(
                read_conn.execute,
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

        # Use connection pool for writes
        pool = await get_connection_pool()
        conn = pool.get_writer_connection()

        # Execute write through the pool's queue to serialize writes
        await pool.execute_write(conn.execute, sql, update_data)

        # Fetch and return updated record using a read connection
        async with db_connection(read_only=True) as read_conn:
            cursor = await asyncio.to_thread(
                read_conn.execute,
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

        # Use connection pool for writes
        pool = await get_connection_pool()
        conn = pool.get_writer_connection()

        sql = f"DELETE FROM {table} WHERE id = :id"
        await pool.execute_write(conn.execute, sql, {"id": record_id})

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


async def repo_ensure_table(table: str, schema_sql: str) -> None:
    """
    Ensure a table exists with given schema (idempotent).
    Uses CREATE TABLE IF NOT EXISTS to avoid errors if table already exists.

    Args:
        table: Table name (for validation)
        schema_sql: Complete CREATE TABLE IF NOT EXISTS SQL statement

    Raises:
        RuntimeError: If table creation fails
    """
    try:
        # Validate table name to prevent SQL injection
        _validate_identifier(table)

        # Use connection pool for writes
        pool = await get_connection_pool()
        conn = pool.get_writer_connection()

        await pool.execute_write(conn.execute, schema_sql)

        logger.debug(f"Ensured table '{table}' exists")

    except sqlite3.OperationalError as e:
        logger.exception(f"Operational error ensuring table '{table}'")
        raise RuntimeError(f"Failed to ensure table '{table}' (operational error)") from e
    except Exception as e:
        logger.exception(f"Unexpected error ensuring table '{table}'")
        raise RuntimeError(f"Failed to ensure table '{table}'") from e
