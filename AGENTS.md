# Agent Development Guidelines

## Request Handling

- Only implement what is asked
- If anything in the request is incomplete or incorrect, ask for clarification or provide 3 options

## Database Usage

### Persistence Requirements

When implementing features that require persistence:

- **Always use the existing database repository interface** - Do not create new database access patterns or direct database connections
- **Constructor injection required** - The database repository interface MUST be passed in via the constructor to ensure testability and loose coupling
- **Follow dependency injection principles** - This ensures components remain decoupled and testable

### Example

```python
class MyService:
    def __init__(self, db_repository: DatabaseRepositoryInterface):
        self.db = db_repository

    def save_data(self, data):
        return self.db.save(data)
```

## Unit Testing Guidelines

### Interface Testing

- **Always use fake concrete implementations of interfaces** in unit tests
- Do not use mocks when a fake implementation can be provided
- Fakes should implement the same interface as the production code

### Database Testing

- **Unit tests that need database access MUST always write to SQLite**
- Never use the production database or other database systems in unit tests
- SQLite provides fast, isolated test execution without external dependencies

### Test Validation

- **When fixing a test, always run just that test to validate it worked**
- Do not run the entire test suite until the specific test passes
- This ensures faster feedback and confirms the fix is effective

### Example

```python
import sqlite3

class FakeDatabaseRepository(DatabaseRepositoryInterface):
    def __init__(self):
        # In-memory SQLite for testing
        self.connection = sqlite3.connect(':memory:')
        self._setup_schema()

    def _setup_schema(self):
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def save(self, data):
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO data (key, value) VALUES (?, ?)",
                       (data.get('key'), data.get('value')))
        self.connection.commit()
        return {"id": cursor.lastrowid}

class TestMyService:
    def setup_method(self):
        self.fake_db = FakeDatabaseRepository()
        self.service = MyService(self.fake_db)

    def test_save_data(self):
        result = self.service.save_data({"key": "value"})
        assert result is not None
```

## Code Structure Guidelines

### Pydantic Models

- **Pydantic models MUST be used for data transfer objects and configuration**
  - Use Pydantic for request/response models
  - Use Pydantic for configuration objects
  - Use Pydantic for any data that needs validation
- **DO NOT use Pydantic models for injected dependencies**
  - Injected dependencies (repositories, services, clients) should use interfaces/protocols
  - This maintains proper separation between data contracts and service dependencies
- **Function arguments and responses**:
  - Data parameters MUST use Pydantic models
  - Injected service/client dependencies use interfaces
  - All function return values MUST use Pydantic models (for data) or appropriate types
- This ensures type safety, validation, and clear contracts

### Function Complexity

- **Functions cannot exceed 50 lines**
- Keep functions focused on a single responsibility
- Break down complex logic into smaller helper functions

### Class Complexity

- **Classes cannot exceed 5 functions**
- This limit includes:
  - Public methods
  - Private methods (prefixed with `_` or `__`)
  - Static methods (`@staticmethod`)
  - Class methods (`@classmethod`)
  - Property methods (`@property`)
- This limit **does NOT include Python magic/dunder methods**:
  - `__init__`, `__str__`, `__repr__`, `__eq__`, `__hash__`, etc. are exempt
  - Magic methods do not count toward the 5-function limit
- If a class needs more functionality, consider splitting it into multiple classes

### Dependency Management

- **Constructors and functions may NEVER read from environment variables**
- All configuration must be passed in via constructor injection
- This ensures testability and explicit dependencies

- **Constructors and functions must NEVER create an object for a client or service class**
- All dependencies must be injected via the constructor
- This follows the Dependency Injection principle and ensures loose coupling

### Example

```python
from pydantic import BaseModel
from typing import Protocol

# Pydantic models for data and configuration
class ServiceConfig(BaseModel):
    max_retries: int
    timeout_seconds: int

class SaveRequest(BaseModel):
    key: str
    value: str

class SaveResponse(BaseModel):
    success: bool
    id: str

# Interface for injected dependency (NOT a Pydantic model)
class DatabaseRepositoryInterface(Protocol):
    def save(self, data: dict) -> dict:
        ...

class MyService:
    def __init__(self, config: ServiceConfig, db_repository: DatabaseRepositoryInterface):
        # config: Pydantic model for configuration data
        # db_repository: Interface for injected dependency
        # No environment variable reading
        # No client/service object creation
        self.config = config
        self.db = db_repository

    def save_data(self, request: SaveRequest) -> SaveResponse:
        # request: Pydantic model for input data
        # returns: Pydantic model for output data
        result = self.db.save(request.model_dump())
        return SaveResponse(success=True, id=result["id"])
```

## Summary

1. Use existing database repository interfaces (constructor injection required)
2. Unit tests use fake concrete implementations, not mocks
3. Database unit tests always use SQLite
4. When fixing tests, run only that specific test to validate
5. Use Pydantic models for data/configuration objects, NOT for injected dependencies
6. Functions cannot exceed 50 lines
7. Classes cannot exceed 5 functions (excluding `__init__`)
8. Never read environment variables in constructors or functions
9. Never create client or service objects in constructors or functions
10. Only implement what is asked
11. If a request is incomplete or incorrect, ask for clarification or provide 3 options

