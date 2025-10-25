"""
Standalone test script for SQLite repository.
This tests the basic CRUD operations without requiring the full test suite.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure to use SQLite
os.environ["DB_TYPE"] = "sqlite"
test_db_fd, test_db = tempfile.mkstemp(suffix=".db", prefix="test_")
os.close(test_db_fd)  # Close the file descriptor, we only need the path
os.environ["SQLITE_URL"] = f"sqlite:///{test_db}"

print(f"Using test database: {test_db}")

from open_notebook.database import sqlite_repository


async def test_basic_operations():
    """Test basic CRUD operations"""
    print("\n" + "="*60)
    print("Testing SQLite Repository")
    print("="*60)

    try:
        # Test 1: Create a notebook
        print("\n[TEST 1] Creating a notebook...")
        notebook_data = {
            "name": "Test Notebook",
            "description": "A test notebook",
            "archived": False
        }
        notebook = await sqlite_repository.repo_create("notebook", notebook_data)
        print(f"✓ Created notebook: {notebook['id']}")
        print(f"  Name: {notebook['name']}")
        print(f"  Created: {notebook['created']}")

        # Test 2: Query the notebook
        print("\n[TEST 2] Querying the notebook...")
        results = await sqlite_repository.repo_query(
            "SELECT * FROM notebook WHERE id = :id",
            {"id": notebook["id"]}
        )
        print(f"✓ Found {len(results)} notebook(s)")
        print(f"  Name: {results[0]['name']}")

        # Test 3: Update the notebook
        print("\n[TEST 3] Updating the notebook...")
        updated = await sqlite_repository.repo_update(
            "notebook",
            notebook["id"],
            {"name": "Updated Notebook", "description": "Updated description"}
        )
        print(f"✓ Updated notebook")
        print(f"  New name: {updated[0]['name']}")

        # Test 4: Create a source
        print("\n[TEST 4] Creating a source...")
        source_data = {
            "title": "Test Source",
            "full_text": "This is test content",
            "topics": ["test", "demo"]
        }
        source = await sqlite_repository.repo_create("source", source_data)
        print(f"✓ Created source: {source['id']}")
        print(f"  Title: {source['title']}")
        print(f"  Topics: {source.get('topics', [])}")

        # Test 5: Create a relationship
        print("\n[TEST 5] Creating a relationship (source -> notebook)...")
        relation = await sqlite_repository.repo_relate(
            source=source["id"],
            relationship="reference",
            target=notebook["id"]
        )
        print(f"✓ Created relationship: {relation[0]['id']}")
        print(f"  From: {relation[0]['in']}")
        print(f"  To: {relation[0]['out']}")

        # Test 6: Query with relationship
        print("\n[TEST 6] Querying sources for notebook...")
        results = await sqlite_repository.repo_query(
            """
            SELECT s.* FROM source s
            INNER JOIN reference r ON r."in" = s.id
            WHERE r."out" = :notebook_id
            """,
            {"notebook_id": notebook["id"]}
        )
        print(f"✓ Found {len(results)} source(s) for notebook")
        if results:
            print(f"  Source title: {results[0]['title']}")

        # Test 7: Create a note
        print("\n[TEST 7] Creating a note...")
        note_data = {
            "title": "Test Note",
            "content": "This is a test note",
            "note_type": "human"
        }
        note = await sqlite_repository.repo_create("note", note_data)
        print(f"✓ Created note: {note['id']}")
        print(f"  Title: {note['title']}")

        # Test 8: Relate note to notebook
        print("\n[TEST 8] Relating note to notebook...")
        await sqlite_repository.repo_relate(
            source=note["id"],
            relationship="artifact",
            target=notebook["id"]
        )
        print(f"✓ Created artifact relationship")

        # Test 9: Delete operations
        print("\n[TEST 9] Testing delete...")
        await sqlite_repository.repo_delete(note["id"])
        print(f"✓ Deleted note")

        # Verify deletion
        results = await sqlite_repository.repo_query(
            "SELECT * FROM note WHERE id = :id",
            {"id": note["id"]}
        )
        assert len(results) == 0, "Note should be deleted"
        print(f"✓ Verified note was deleted")

        # Test 10: Upsert operation
        print("\n[TEST 10] Testing upsert...")
        upsert_data = {"name": "Upserted Notebook", "description": "Test upsert"}
        result = await sqlite_repository.repo_upsert(
            "notebook",
            notebook["id"],
            upsert_data,
            add_timestamp=True
        )
        print(f"✓ Upserted notebook")
        print(f"  Name: {result[0]['name']}")

        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60)

        return True

    except Exception as e:
        print(f"\n✗ Test failed with error:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup
        if os.path.exists(test_db):
            os.remove(test_db)
            print(f"\nCleaned up test database: {test_db}")


if __name__ == "__main__":
    success = asyncio.run(test_basic_operations())
    sys.exit(0 if success else 1)
