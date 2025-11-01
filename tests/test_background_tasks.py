"""
Tests for background task processing with SQLite mode.

This test suite validates that async source processing works correctly
with FastAPI BackgroundTasks when using SQLite database.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Create a temporary file for SQLite database that persists across connections
temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db_file.name
temp_db_file.close()

# Set DB_TYPE to sqlite for these tests
os.environ["DB_TYPE"] = "sqlite"
os.environ["SQLITE_URL"] = f"sqlite:///{temp_db_path}"

from api.background_tasks import (
    _ensure_command_table,
    create_command_record,
    get_command_status_from_db,
    process_source_background,
    update_command_status,
)
from api.main import app


def teardown_module():
    """Clean up temporary database file after all tests."""
    import os

    if os.path.exists(temp_db_path):
        os.unlink(temp_db_path)


class TestBackgroundTasksSQLite:
    """Test suite for SQLite background task processing."""

    @pytest.mark.asyncio
    async def test_ensure_command_table_creates_table(self):
        """Test that _ensure_command_table creates the command table."""
        # This should not raise an error
        await _ensure_command_table()

        # Verify we can query the table (even if empty)
        from open_notebook.database.repository_factory import repo_query

        result = await repo_query("SELECT COUNT(*) as count FROM command", {})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_create_command_record(self):
        """Test creating a command record in SQLite."""
        await _ensure_command_table()

        command_id = await create_command_record(
            app="test_app",
            command_name="test_command",
            input_data={"key": "value", "number": 42},
        )

        assert command_id.startswith("command:")
        assert len(command_id) > 8  # UUID should be appended

    @pytest.mark.asyncio
    async def test_create_and_retrieve_command_status(self):
        """Test creating a command and retrieving its status."""
        await _ensure_command_table()

        # Create command
        command_id = await create_command_record(
            app="test_app",
            command_name="test_command",
            input_data={"test": "data"},
        )

        # Retrieve status
        status = await get_command_status_from_db(command_id)

        assert status["job_id"] == command_id
        assert status["status"] == "queued"
        assert status["progress"] == 0
        assert status["result"] is None

    @pytest.mark.asyncio
    async def test_update_command_status_progress(self):
        """Test updating command status with progress."""
        await _ensure_command_table()

        # Create command
        command_id = await create_command_record(
            app="test_app", command_name="test_command", input_data={}
        )

        # Update to running with progress
        await update_command_status(command_id, "running", progress=50)

        # Verify update
        status = await get_command_status_from_db(command_id)
        assert status["status"] == "running"
        assert status["progress"] == 50

    @pytest.mark.asyncio
    async def test_update_command_status_with_result(self):
        """Test updating command status with result data."""
        await _ensure_command_table()

        # Create command
        command_id = await create_command_record(
            app="test_app", command_name="test_command", input_data={}
        )

        # Update with result
        result_data = {"success": True, "processed_items": 10}
        await update_command_status(command_id, "completed", progress=100, result=result_data)

        # Verify update
        status = await get_command_status_from_db(command_id)
        assert status["status"] == "completed"
        assert status["progress"] == 100
        assert status["result"]["success"] is True
        assert status["result"]["processed_items"] == 10

    @pytest.mark.asyncio
    async def test_update_command_status_with_error(self):
        """Test updating command status with error message."""
        await _ensure_command_table()

        # Create command
        command_id = await create_command_record(
            app="test_app", command_name="test_command", input_data={}
        )

        # Update with error
        error_msg = "Something went wrong"
        await update_command_status(command_id, "failed", error_message=error_msg)

        # Verify update
        status = await get_command_status_from_db(command_id)
        assert status["status"] == "failed"
        assert status["error_message"] == error_msg


class TestBackgroundThreadWithRealPDF:
    """Unit tests for the background thread using a real PDF and SQLite (minimal mocks)."""

    def create_test_pdf_file(self) -> str:
        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj\n"
            b"<<\n"
            b"/Type /Catalog\n"
            b"/Pages 2 0 R\n"
            b">>\n"
            b"endobj\n"
            b"2 0 obj\n"
            b"<<\n"
            b"/Type /Pages\n"
            b"/Kids [3 0 R]\n"
            b"/Count 1\n"
            b">>\n"
            b"endobj\n"
            b"3 0 obj\n"
            b"<<\n"
            b"/Type /Page\n"
            b"/Parent 2 0 R\n"
            b"/MediaBox [0 0 612 792]\n"
            b"/Contents 4 0 R\n"
            b"/Resources <<\n"
            b"/Font <<\n"
            b"/F1 5 0 R\n"
            b">>\n"
            b">>\n"
            b">>\n"
            b"endobj\n"
            b"4 0 obj\n"
            b"<<\n"
            b"/Length 44\n"
            b">>\n"
            b"stream\n"
            b"BT\n"
            b"/F1 12 Tf\n"
            b"100 700 Td\n"
            b"(Hello World from PDF!) Tj\n"
            b"ET\n"
            b"endstream\n"
            b"endobj\n"
            b"5 0 obj\n"
            b"<<\n"
            b"/Type /Font\n"
            b"/Subtype /Type1\n"
            b"/BaseFont /Helvetica\n"
            b">>\n"
            b"endobj\n"
            b"xref\n"
            b"0 6\n"
            b"0000000000 65535 f \n"
            b"0000000010 00000 n \n"
            b"0000000079 00000 n \n"
            b"0000000173 00000 n \n"
            b"0000000301 00000 n \n"
            b"0000000380 00000 n \n"
            b"trailer\n"
            b"<<\n"
            b"/Size 6\n"
            b"/Root 1 0 R\n"
            b">>\n"
            b"startxref\n"
            b"492\n"
            b"%%EOF\n"
        )

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
            f.write(pdf_content)
            return f.name

    @pytest.mark.asyncio
    async def test_process_source_background_real_pdf_sqlite(self):
        # Ensure command table exists
        await _ensure_command_table()

        # Create minimal notebook and source
        from open_notebook.domain.notebook import Notebook, Source
        from open_notebook.database.repository_factory import repo_query

        nb = Notebook(name="BG Thread Test NB", description="Unit test notebook")
        await nb.save()
        notebook_ids = [str(nb.id)]

        pdf_path = self.create_test_pdf_file()
        try:
            src = Source(title="BG Thread PDF", topics=[])
            await src.save()
            await src.add_to_notebook(str(nb.id))

            # Create command and run background processing with real SQLite
            command_id = await create_command_record(
                app="open_notebook",
                command_name="process_source",
                input_data={
                    "source_id": str(src.id),
                    "notebook_ids": notebook_ids,
                    "embed": False,
                    "transformation_ids": [],
                },
            )

            content_state = {
                "content_type": "file",
                "file_path": pdf_path,
                "title": "BG Thread PDF",
            }

            await process_source_background(
                command_id=command_id,
                source_id=str(src.id),
                content_state=content_state,
                notebook_ids=notebook_ids,
                transformation_ids=[],
                embed=False,
            )

            # Verify outcome: completed or failed but not due to DB corruption
            status = await get_command_status_from_db(command_id)
            assert status["status"] in ["completed", "failed"]
            if status["status"] == "failed":
                err = status.get("error_message") or ""
                assert "database disk image is malformed" not in err

            # Ensure database integrity is OK
            integrity = await repo_query("PRAGMA integrity_check", {})
            assert len(integrity) > 0
            first = integrity[0]
            integrity_status = list(first.values())[0]
            assert integrity_status == "ok"
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)


class TestSourcesAPIAsyncProcessing:
    """Test suite for sources API async processing endpoint."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    @patch("api.routers.sources.Source")
    @patch("api.routers.sources.Notebook")
    @patch("api.routers.sources.create_command_record")
    def test_create_source_with_async_processing_sqlite(
        self, mock_create_command, mock_notebook, mock_source
    ):
        """Test creating a source with async_processing=true in SQLite mode."""
        # Mock notebook exists
        mock_notebook_instance = MagicMock()
        mock_notebook.get = AsyncMock(return_value=mock_notebook_instance)

        # Mock source creation
        mock_source_instance = MagicMock()
        mock_source_instance.id = "source:test123"
        mock_source_instance.title = "Test Source"
        mock_source_instance.topics = []
        mock_source_instance.created = "2025-01-01T00:00:00"
        mock_source_instance.updated = "2025-01-01T00:00:00"
        mock_source_instance.save = AsyncMock()
        mock_source_instance.add_to_notebook = AsyncMock()
        mock_source.return_value = mock_source_instance

        # Mock command creation
        mock_create_command.return_value = "command:abc-123"

        # Make request
        response = self.client.post(
            "/api/sources/json",
            json={
                "type": "text",
                "notebooks": ["notebook:test"],
                "content": "Test content",
                "title": "Test Source",
                "embed": False,
                "async_processing": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["command_id"] == "command:abc-123"
        assert "processing_info" in data
        assert data["processing_info"]["async"] is True
        assert data["processing_info"]["db_type"] == "sqlite"

    @patch("api.routers.sources.get_database_type")
    @patch("api.routers.sources.Source")
    @patch("api.routers.sources.Notebook")
    def test_create_source_with_sync_processing_sqlite(
        self, mock_notebook, mock_source, mock_get_db_type
    ):
        """Test creating a source with async_processing=false falls back to sync."""
        # Mock database type
        mock_get_db_type.return_value = "sqlite"

        # Mock notebook exists
        mock_notebook_instance = MagicMock()
        mock_notebook.get = AsyncMock(return_value=mock_notebook_instance)

        # Mock source creation and processing
        mock_source_instance = MagicMock()
        mock_source_instance.id = "source:test123"
        mock_source_instance.title = "Test Source"
        mock_source_instance.topics = []
        mock_source_instance.asset = None
        mock_source_instance.full_text = "Processed content"
        mock_source_instance.created = "2025-01-01T00:00:00"
        mock_source_instance.updated = "2025-01-01T00:00:00"
        mock_source_instance.save = AsyncMock()
        mock_source_instance.add_to_notebook = AsyncMock()
        mock_source_instance.get_embedded_chunks = AsyncMock(return_value=0)
        mock_source.return_value = mock_source_instance
        mock_source.get = AsyncMock(return_value=mock_source_instance)

        # Mock execute_command_sync
        with patch("api.routers.sources.execute_command_sync") as mock_execute:
            mock_result = MagicMock()
            mock_result.is_success.return_value = True
            mock_execute.return_value = mock_result

            # Make request
            response = self.client.post(
                "/api/sources/json",
                json={
                    "type": "text",
                    "notebooks": ["notebook:test"],
                    "content": "Test content",
                    "title": "Test Source",
                    "embed": False,
                    "async_processing": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            # Sync mode doesn't use commands - command_id should be None or not present
            assert data.get("command_id") is None
            assert data["full_text"] == "Processed content"


class TestCommandsAPIWithSQLite:
    """Test suite for commands API with SQLite mode."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_command_status_sqlite_mode(self):
        """Test retrieving command status in SQLite mode."""
        await _ensure_command_table()

        # Create a test command
        command_id = await create_command_record(
            app="test_app",
            command_name="test_command",
            input_data={"test": "data"},
        )

        # Update it to completed
        await update_command_status(
            command_id,
            "completed",
            progress=100,
            result={"success": True},
        )

        # Retrieve via API
        with patch("api.routers.commands.get_database_type") as mock_db_type:
            mock_db_type.return_value = "sqlite"

            response = self.client.get(f"/api/commands/jobs/{command_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["progress"] == 100
            assert data["result"]["success"] is True
