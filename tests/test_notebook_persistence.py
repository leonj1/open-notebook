"""
Integration tests for Notebook persistence with SQLite database.

This test suite validates that Notebook domain objects properly persist to
and retrieve from an actual SQLite database using the repository layer.
"""

import os

import pytest

# Import domain models
from open_notebook.domain.notebook import Notebook

# Ensure we're using SQLite for these tests
os.environ["DB_TYPE"] = "sqlite"


@pytest.mark.asyncio
class TestNotebookPersistence:
    """Test suite for Notebook database persistence operations."""

    async def test_notebook_save_creates_new_record(self):
        """Test that Notebook.save() creates a new record in SQLite database."""
        # Create a new notebook instance
        notebook = Notebook(
            name="Test Notebook",
            description="This is a test notebook for persistence validation"
        )

        # Verify it doesn't have an ID yet
        assert notebook.id is None

        # Save to database
        await notebook.save()

        # Verify it now has an ID assigned
        assert notebook.id is not None
        assert notebook.id.startswith("notebook:")

        # Verify timestamps were set
        assert notebook.created is not None
        assert notebook.updated is not None

    async def test_notebook_save_and_retrieve(self):
        """Test that saved Notebook can be retrieved from database."""
        # Create and save notebook
        original_notebook = Notebook(
            name="Retrievable Notebook",
            description="Testing retrieval functionality"
        )
        await original_notebook.save()

        # Store the ID
        notebook_id = original_notebook.id
        assert notebook_id is not None

        # Retrieve the notebook from database
        retrieved_notebook = await Notebook.get(notebook_id)

        # Verify all fields match
        assert retrieved_notebook.id == original_notebook.id
        assert retrieved_notebook.name == "Retrievable Notebook"
        assert retrieved_notebook.description == "Testing retrieval functionality"
        assert retrieved_notebook.archived == False
        assert retrieved_notebook.created is not None
        assert retrieved_notebook.updated is not None

    async def test_notebook_update_persists_changes(self):
        """Test that updating a Notebook persists changes to database."""
        # Create and save initial notebook
        notebook = Notebook(
            name="Original Name",
            description="Original Description"
        )
        await notebook.save()

        original_id = notebook.id
        original_created = notebook.created

        # Update fields
        notebook.name = "Updated Name"
        notebook.description = "Updated Description"
        notebook.archived = True

        # Save updates
        await notebook.save()

        # Verify ID didn't change
        assert notebook.id == original_id

        # Verify created timestamp didn't change
        assert notebook.created == original_created

        # Retrieve from database to verify persistence
        retrieved = await Notebook.get(original_id)

        assert retrieved.name == "Updated Name"
        assert retrieved.description == "Updated Description"
        assert retrieved.archived == True

    async def test_notebook_get_all(self):
        """Test retrieving all notebooks from database."""
        # Create and save multiple notebooks
        notebook1 = Notebook(name="First", description="First notebook")
        notebook2 = Notebook(name="Second", description="Second notebook")
        notebook3 = Notebook(name="Third", description="Third notebook")

        await notebook1.save()
        await notebook2.save()
        await notebook3.save()

        # Retrieve all notebooks
        all_notebooks = await Notebook.get_all()

        # Verify we have at least the 3 we created
        assert len(all_notebooks) >= 3

        # Verify they're all Notebook instances
        for nb in all_notebooks:
            assert isinstance(nb, Notebook)
            assert nb.id is not None
            assert nb.name is not None

    async def test_notebook_delete_removes_from_database(self):
        """Test that deleting a Notebook removes it from database."""
        # Create and save notebook
        notebook = Notebook(
            name="To Be Deleted",
            description="This notebook will be deleted"
        )
        await notebook.save()

        notebook_id = notebook.id
        assert notebook_id is not None

        # Verify it exists
        retrieved = await Notebook.get(notebook_id)
        assert retrieved is not None

        # Delete the notebook
        delete_result = await notebook.delete()
        assert delete_result is True

        # Verify it no longer exists in database
        from open_notebook.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await Notebook.get(notebook_id)

    async def test_notebook_archived_default_false(self):
        """Test that archived flag defaults to False when persisted."""
        notebook = Notebook(name="Test", description="Test")
        await notebook.save()

        # Retrieve and verify
        retrieved = await Notebook.get(notebook.id)
        assert retrieved.archived is False

    async def test_notebook_archived_true_persists(self):
        """Test that archived=True is properly persisted."""
        notebook = Notebook(
            name="Archived Test",
            description="Test",
            archived=True
        )
        await notebook.save()

        # Retrieve and verify
        retrieved = await Notebook.get(notebook.id)
        assert retrieved.archived is True

    async def test_multiple_notebooks_isolated(self):
        """Test that multiple notebooks are independently stored and retrieved."""
        # Create multiple distinct notebooks
        notebooks_data = [
            {"name": "Work", "description": "Work related notes"},
            {"name": "Personal", "description": "Personal projects"},
            {"name": "Research", "description": "Research materials"}
        ]

        saved_notebooks = []
        for data in notebooks_data:
            nb = Notebook(**data)
            await nb.save()
            saved_notebooks.append(nb)

        # Retrieve each one and verify isolation
        for original in saved_notebooks:
            retrieved = await Notebook.get(original.id)
            assert retrieved.id == original.id
            assert retrieved.name == original.name
            assert retrieved.description == original.description

    async def test_notebook_timestamps_update_on_save(self):
        """Test that updated timestamp changes when notebook is modified."""
        import asyncio

        # Create and save notebook
        notebook = Notebook(name="Timestamp Test", description="Test")
        await notebook.save()

        original_updated = notebook.updated

        # Wait a moment to ensure timestamp will be different
        await asyncio.sleep(0.1)

        # Update and save again
        notebook.description = "Modified description"
        await notebook.save()

        # Updated timestamp should have changed
        assert notebook.updated != original_updated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
