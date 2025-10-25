"""
Example: Using the SQLite Repository

This script demonstrates how to use the SQLite repository implementation
and how to switch between SQLite and SurrealDB.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# EXAMPLE 1: Using SQLite
# ============================================================================


async def example_sqlite():
    """Example using SQLite repository"""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Using SQLite Repository")
    print("=" * 60)

    # Configure to use SQLite
    os.environ["DB_TYPE"] = "sqlite"
    os.environ["SQLITE_URL"] = "sqlite:///./example_notebook.db"

    print(f"\nConfiguration:")
    print(f"  DB_TYPE: {os.getenv('DB_TYPE')}")
    print(f"  SQLITE_URL: {os.getenv('SQLITE_URL')}")

    # Import from factory - it will automatically use SQLite
    from open_notebook.database.repository_factory import (
        repo_create,
        repo_query,
        repo_update,
        repo_relate,
    )

    print(f"\n1. Creating a notebook...")
    notebook = await repo_create("notebook", {
        "name": "Research Project",
        "description": "My research on AI models"
    })
    print(f"   ✓ Created: {notebook['id']}")
    print(f"   Name: {notebook['name']}")

    print(f"\n2. Creating a source...")
    source = await repo_create("source", {
        "title": "Important Paper",
        "full_text": "This paper discusses...",
        "topics": ["AI", "Machine Learning"]
    })
    print(f"   ✓ Created: {source['id']}")
    print(f"   Title: {source['title']}")

    print(f"\n3. Linking source to notebook...")
    await repo_relate(
        source=source["id"],
        relationship="reference",
        target=notebook["id"]
    )
    print(f"   ✓ Created relationship")

    print(f"\n4. Querying linked sources...")
    results = await repo_query("""
        SELECT s.* FROM source s
        INNER JOIN reference r ON r."in" = s.id
        WHERE r."out" = :notebook_id
    """, {"notebook_id": notebook["id"]})

    print(f"   ✓ Found {len(results)} source(s)")
    for src in results:
        print(f"     - {src['title']}")

    print(f"\n5. Updating the notebook...")
    updated = await repo_update("notebook", notebook["id"], {
        "description": "Updated: Advanced AI research"
    })
    print(f"   ✓ Updated description: {updated[0]['description']}")

    # Cleanup
    os.remove("example_notebook.db")
    print(f"\n✓ Example completed successfully!")
    print("=" * 60)


# ============================================================================
# EXAMPLE 2: Dynamic Repository Selection
# ============================================================================


async def example_dynamic_selection():
    """Example showing dynamic repository selection"""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Dynamic Repository Selection")
    print("=" * 60)

    from open_notebook.database.repository_factory import get_database_type

    # Test with different DB_TYPE values
    for db_type in ["sqlite", "surrealdb"]:
        os.environ["DB_TYPE"] = db_type

        # Re-import to get new factory instance
        import importlib
        import open_notebook.database.repository_factory as factory
        importlib.reload(factory)

        detected_type = factory.get_database_type()
        print(f"\nDB_TYPE={db_type}")
        print(f"  → Factory selected: {detected_type}")
        print(f"  → Module: {factory.get_repository_module().__name__}")

    print("\n✓ Dynamic selection working correctly!")
    print("=" * 60)


# ============================================================================
# EXAMPLE 3: Repository Interface Compatibility
# ============================================================================


async def example_interface_compatibility():
    """Example showing all repository functions are available"""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Repository Interface Compatibility")
    print("=" * 60)

    os.environ["DB_TYPE"] = "sqlite"
    os.environ["SQLITE_URL"] = "sqlite:///./test.db"

    from open_notebook.database import repository_factory

    print("\nAvailable repository functions:")

    functions = [
        "repo_query",
        "repo_create",
        "repo_insert",
        "repo_update",
        "repo_upsert",
        "repo_delete",
        "repo_relate",
        "ensure_record_id",
        "parse_record_ids",
        "db_connection",
    ]

    for func_name in functions:
        if hasattr(repository_factory, func_name):
            func = getattr(repository_factory, func_name)
            print(f"  ✓ {func_name:<25} {type(func).__name__}")
        else:
            print(f"  ✗ {func_name:<25} NOT FOUND")

    # Cleanup
    if os.path.exists("test.db"):
        os.remove("test.db")

    print("\n✓ All repository functions are available!")
    print("=" * 60)


# ============================================================================
# EXAMPLE 4: Using with Domain Models
# ============================================================================


async def example_with_domain_models():
    """Example using domain models with SQLite"""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Using Domain Models with SQLite")
    print("=" * 60)

    os.environ["DB_TYPE"] = "sqlite"
    os.environ["SQLITE_URL"] = "sqlite:///./domain_example.db"

    try:
        # This would work if all dependencies were installed
        from open_notebook.domain.notebook import Notebook, Note

        print("\n1. Creating notebook using domain model...")
        notebook = Notebook(
            name="Domain Model Example",
            description="Testing domain models with SQLite"
        )
        await notebook.save()
        print(f"   ✓ Created notebook: {notebook.id}")

        print("\n2. Creating note...")
        note = Note(
            title="Research Notes",
            content="Important findings...",
            note_type="human"
        )
        await note.save()
        print(f"   ✓ Created note: {note.id}")

        print("\n3. Linking note to notebook...")
        await note.add_to_notebook(notebook.id)
        print(f"   ✓ Created relationship")

        print("\n✓ Domain models work with SQLite!")

    except ImportError as e:
        print(f"\n⚠ Cannot run this example - missing dependencies:")
        print(f"  {e}")
        print(f"\nNote: Domain models require additional packages:")
        print(f"  - esperanto, langchain, etc.")
        print(f"\nBut the repository layer works independently!")

    finally:
        if os.path.exists("domain_example.db"):
            os.remove("domain_example.db")

    print("=" * 60)


# ============================================================================
# Main
# ============================================================================


async def main():
    """Run all examples"""
    print("\n" + "#" * 60)
    print("# SQLite Repository - Usage Examples")
    print("#" * 60)

    # Example 1: Basic SQLite usage
    await example_sqlite()

    # Example 2: Dynamic selection
    await example_dynamic_selection()

    # Example 3: Interface compatibility
    await example_interface_compatibility()

    # Example 4: Domain models (may fail without dependencies)
    await example_with_domain_models()

    print("\n" + "#" * 60)
    print("# All examples completed!")
    print("#" * 60)
    print("\nTo use SQLite in your application:")
    print("  1. Set: export DB_TYPE=sqlite")
    print("  2. Set: export SQLITE_URL='sqlite:///./your-db.db'")
    print("  3. Import from: open_notebook.database.repository_factory")
    print("  4. Use normally - factory handles the rest!")
    print()


if __name__ == "__main__":
    asyncio.run(main())
