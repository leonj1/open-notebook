# SQLite Repository - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  (FastAPI Routes, CLI, Domain Logic)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Models Layer                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Notebook │  │  Source  │  │   Note   │  ...              │
│  └──────────┘  └──────────┘  └──────────┘                  │
│         │             │             │                        │
│         └─────────────┴─────────────┘                        │
│                       │                                       │
│                       │ Imports from                         │
│                       ▼                                       │
│         ┌─────────────────────────────┐                     │
│         │  open_notebook.domain.base  │                     │
│         │  (ObjectModel, RecordModel) │                     │
│         └─────────────┬───────────────┘                     │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        │ Imports from
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Repository Factory Layer                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   open_notebook.database.repository_factory           │  │
│  │                                                         │  │
│  │   • Reads DB_TYPE environment variable                │  │
│  │   • Returns appropriate repository module             │  │
│  │   • Re-exports all repository functions               │  │
│  └────────────┬──────────────────────────┬─────────────────┘  │
└───────────────┼──────────────────────────┼─────────────────┘
                │                          │
    DB_TYPE=sqlite                  DB_TYPE=surrealdb
                │                          │
                ▼                          ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│  SQLite Repository        │  │  SurrealDB Repository     │
│  (NEW IMPLEMENTATION)     │  │  (EXISTING)               │
├───────────────────────────┤  ├───────────────────────────┤
│ sqlite_repository.py      │  │ repository.py             │
│                           │  │                           │
│ Functions:                │  │ Functions:                │
│  • repo_query()           │  │  • repo_query()           │
│  • repo_create()          │  │  • repo_create()          │
│  • repo_update()          │  │  • repo_update()          │
│  • repo_delete()          │  │  • repo_delete()          │
│  • repo_relate()          │  │  • repo_relate()          │
│  • repo_insert()          │  │  • repo_insert()          │
│  • repo_upsert()          │  │  • repo_upsert()          │
│  • ensure_record_id()     │  │  • ensure_record_id()     │
│  • parse_record_ids()     │  │  • parse_record_ids()     │
│  • db_connection()        │  │  • db_connection()        │
└─────────────┬─────────────┘  └─────────────┬─────────────┘
              │                              │
              ▼                              ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│  SQLite Database          │  │  SurrealDB Server         │
│                           │  │                           │
│  • Single file            │  │  • Client-Server          │
│  • sqlite_schema.sql      │  │  • Graph database         │
│  • FTS5 search            │  │  • SurrealQL              │
│  • No dependencies        │  │  • WebSocket/HTTP         │
└───────────────────────────┘  └───────────────────────────┘
```

## Request Flow Example

### Creating a Notebook

```
User Code:
┌─────────────────────────────────────────┐
│ from open_notebook.domain.notebook      │
│     import Notebook                     │
│                                         │
│ nb = Notebook(name="Research",          │
│               description="AI")         │
│ await nb.save()                         │
└─────────────────┬───────────────────────┘
                  │
                  ▼
Domain Model (notebook.py):
┌─────────────────────────────────────────┐
│ class Notebook(ObjectModel):            │
│     async def save(self):               │
│         await repo_create(...)          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
Base Model (base.py):
┌─────────────────────────────────────────┐
│ from repository_factory import          │
│     repo_create                         │
└─────────────────┬───────────────────────┘
                  │
                  ▼
Repository Factory:
┌─────────────────────────────────────────┐
│ DB_TYPE = os.getenv("DB_TYPE")          │
│                                         │
│ if DB_TYPE == "sqlite":                 │
│     return sqlite_repository            │
│ else:                                   │
│     return repository                   │
└─────────────────┬───────────────────────┘
                  │
                  ▼
SQLite Repository:
┌─────────────────────────────────────────┐
│ async def repo_create(table, data):     │
│     async with db_connection() as conn: │
│         await asyncio.to_thread(        │
│             conn.execute, sql, data)    │
└─────────────────┬───────────────────────┘
                  │
                  ▼
SQLite Database:
┌─────────────────────────────────────────┐
│ INSERT INTO notebook (id, name, ...)    │
│ VALUES (?, ?, ...)                      │
│                                         │
│ ✓ Record stored in notebook.db         │
└─────────────────────────────────────────┘
```

## Data Flow: Query with Relationships

```
Query: "Get all sources for a notebook"

┌──────────────────────────────────────┐
│ notebook.get_sources()               │
└───────────┬──────────────────────────┘
            │
            ▼
┌──────────────────────────────────────┐
│ await repo_query("""                 │
│   SELECT s.* FROM source s           │
│   INNER JOIN reference r             │
│     ON r."in" = s.id                 │
│   WHERE r."out" = :notebook_id       │
│ """, {"notebook_id": self.id})       │
└───────────┬──────────────────────────┘
            │
            ▼
┌──────────────────────────────────────┐
│ SQLite executes JOIN query:          │
│                                      │
│ notebook         reference   source  │
│ ┌─────────┐     ┌────┬────┐ ┌─────┐ │
│ │ id      │◄────┤out │in  ├─►│ id  │ │
│ │ name    │     └────┴────┘ │title│ │
│ └─────────┘                 └─────┘ │
└───────────┬──────────────────────────┘
            │
            ▼
┌──────────────────────────────────────┐
│ Returns list of Source dicts:        │
│ [                                    │
│   {id: "source:123",                 │
│    title: "Paper 1", ...},           │
│   {id: "source:456",                 │
│    title: "Paper 2", ...}            │
│ ]                                    │
└──────────────────────────────────────┘
```

## Database Schema Mapping

### SurrealDB → SQLite Translation

```
SurrealDB:                        SQLite:
═══════════                       ═══════

DEFINE TABLE notebook             CREATE TABLE notebook (
  SCHEMAFULL;                        id TEXT PRIMARY KEY,
                                     name TEXT,
DEFINE FIELD name                    description TEXT,
  ON TABLE notebook                  archived INTEGER,
  TYPE option<string>;               created TEXT,
                                     updated TEXT
DEFINE FIELD description           );
  ON TABLE notebook
  TYPE option<string>;

───────────────────────────────────────────────────

DEFINE TABLE reference             CREATE TABLE reference (
  TYPE RELATION                       id TEXT PRIMARY KEY,
  FROM source                         "in" TEXT NOT NULL,
  TO notebook;                        "out" TEXT NOT NULL,
                                      created TEXT,
                                      updated TEXT,
                                      FOREIGN KEY ("in")
                                        REFERENCES source(id)
                                        ON DELETE CASCADE,
                                      FOREIGN KEY ("out")
                                        REFERENCES notebook(id)
                                        ON DELETE CASCADE
                                    );
```

## Environment-Based Switching

```
┌─────────────────────────────────────────────────┐
│  Environment Variables                          │
├─────────────────────────────────────────────────┤
│                                                 │
│  Option A: SQLite                               │
│  ┌─────────────────────────────────────────┐   │
│  │ export DB_TYPE=sqlite                   │   │
│  │ export SQLITE_URL="sqlite:///./data.db" │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  Option B: SurrealDB                            │
│  ┌─────────────────────────────────────────┐   │
│  │ export DB_TYPE=surrealdb                │   │
│  │ export SURREAL_URL="ws://localhost/rpc" │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  repository_factory.py                          │
│                                                 │
│  db_type = os.getenv("DB_TYPE", "surrealdb")   │
│                                                 │
│  if db_type == "sqlite":                        │
│      from . import sqlite_repository            │
│      return sqlite_repository                   │
│  else:                                          │
│      from . import repository                   │
│      return repository                          │
└─────────────────────────────────────────────────┘
```

## File Organization

```
open-notebook/
│
├── open_notebook/
│   ├── database/
│   │   ├── __init__.py
│   │   ├── repository.py              ← Original (SurrealDB)
│   │   ├── sqlite_repository.py       ← ✨ NEW (SQLite)
│   │   ├── sqlite_schema.sql          ← ✨ NEW (Schema)
│   │   └── repository_factory.py      ← ✨ NEW (Switcher)
│   │
│   └── domain/
│       ├── base.py                    ← ✏️ Modified
│       ├── notebook.py                ← ✏️ Modified
│       ├── models.py
│       └── ...
│
├── tests/
│   ├── conftest.py                    ← Original
│   ├── conftest_sqlite.py             ← ✨ NEW
│   ├── test_domain.py
│   ├── test_utils.py
│   └── ...
│
├── test_sqlite_repo.py                ← ✨ NEW (Standalone tests)
├── example_usage.py                   ← ✨ NEW (Examples)
│
├── SQLITE_IMPLEMENTATION.md           ← ✨ NEW (Tech docs)
├── README_SQLITE.md                   ← ✨ NEW (Quick start)
├── IMPLEMENTATION_SUMMARY.md          ← ✨ NEW (Summary)
└── ARCHITECTURE_DIAGRAM.md            ← ✨ NEW (This file)
```

## Async Operation Flow

```
Async Function Call:
┌────────────────────────────────┐
│ await repo_create(             │
│     "notebook",                │
│     {"name": "Test"}           │
│ )                              │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ async def repo_create():       │
│   async with db_connection():  │
│     ...                        │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ @asynccontextmanager           │
│ async def db_connection():     │
│   conn = sqlite3.connect(      │
│       db_path,                 │
│       check_same_thread=False  │
│   )                            │
│   yield conn                   │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ await asyncio.to_thread(       │
│     conn.execute,              │
│     sql,                       │
│     params                     │
│ )                              │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ Thread Pool Executor           │
│ ┌────────────────────────────┐ │
│ │ Worker Thread              │ │
│ │   conn.execute(sql, ...)   │ │
│ │   [SQLite I/O happens]     │ │
│ └────────────────────────────┘ │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ Result returned to async       │
│ context                        │
└────────────────────────────────┘
```

## Key Design Decisions

### 1. Factory Pattern
**Why:** Allows runtime selection of database backend without code changes

**Implementation:**
```python
# repository_factory.py
if get_database_type() == "sqlite":
    from . import sqlite_repository
    return sqlite_repository
else:
    from . import repository
    return repository
```

### 2. Graph → Relational Mapping
**Why:** SQLite doesn't have native graph features

**Solution:** Junction tables with `in`/`out` columns
```sql
CREATE TABLE reference (
    "in" TEXT,   -- source.id
    "out" TEXT   -- notebook.id
)
```

### 3. Async Wrapper
**Why:** SQLite is synchronous, but app uses async/await

**Solution:** `asyncio.to_thread()` for non-blocking I/O
```python
await asyncio.to_thread(conn.execute, sql, params)
```

### 4. ID Format Preservation
**Why:** Maintain compatibility with SurrealDB RecordID format

**Solution:** Use string IDs with format `table:uuid`
```python
def generate_id(table: str) -> str:
    return f"{table}:{uuid.uuid4().hex[:16]}"
```

## Testing Strategy

```
┌─────────────────────────────────────────┐
│  Test Pyramid                           │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   Integration Tests             │   │
│  │   (Full app with SQLite)        │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   Repository Tests              │   │
│  │   ✅ test_sqlite_repo.py        │   │
│  │   (10 comprehensive tests)      │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   Unit Tests                    │   │
│  │   (Function-level tests)        │   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

---

**Legend:**
- ✨ NEW = Newly created file
- ✏️ Modified = Existing file modified
- ✅ = Test passing
- ⚠️ = Limitation/future work
