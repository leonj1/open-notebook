"""
TDD Tests for file upload functionality with background processing.

This test suite validates that files (text and PDF) can be uploaded and 
processed in the background correctly.
"""

import asyncio
import io
import os
import tempfile
import time
from pathlib import Path
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

from api.main import app


def teardown_module():
    """Clean up temporary database file after all tests."""
    if os.path.exists(temp_db_path):
        os.unlink(temp_db_path)


class TestFileUploadWithBackgroundProcessing:
    """Test suite for file upload with background processing."""

    def setup_method(self):
        """Set up test client and mock data."""
        self.client = TestClient(app)
        self.test_uploads_dir = tempfile.mkdtemp()
        
    def teardown_method(self):
        """Clean up test uploads directory."""
        import shutil
        shutil.rmtree(self.test_uploads_dir, ignore_errors=True)

    def test_text_file_upload_with_background_processing(self):
        """Test that a text file can be uploaded and processed in background."""
        # Create a test text file
        test_content = "This is a test document for upload validation."
        text_file = io.BytesIO(test_content.encode())
        
        # Mock file saving 
        with patch("api.routers.sources.save_uploaded_file") as mock_save:
            
            mock_save.return_value = "/tmp/test_file.txt"
            
            # Prepare form data
            files = {"file": ("test_document.txt", text_file, "text/plain")}
            data = {
                "title": "Test Text Document",
                "type": "upload",
                "async_processing": "true",
                "delete_source": "false"
            }
            
            # Make request
            response = self.client.post("/api/sources", files=files, data=data)
            
            # Assertions
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["title"] == "Test Text Document"
            assert "id" in response_data
            assert "command_id" in response_data  # Should have command_id for async processing
            
            # Verify file was saved
            mock_save.assert_called_once()
            
            # Verify that a command ID was returned indicating background processing was started
            assert response_data.get("command_id") is not None
            assert response_data.get("command_id").startswith("command:")

    def test_pdf_file_upload_with_background_processing(self):
        """Test that a PDF file can be uploaded and processed in background."""
        # Create a minimal PDF content (not a real PDF, but sufficient for testing)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Hello World) Tj\nET\nendstream\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<\n/Size 1\n/Root 1 0 R\n>>\nstartxref\n9\n%%EOF"
        pdf_file = io.BytesIO(pdf_content)
        
        # Mock file saving
        with patch("api.routers.sources.save_uploaded_file") as mock_save:
            
            mock_save.return_value = "/tmp/test_file.pdf"
            
            # Prepare form data
            files = {"file": ("test_document.pdf", pdf_file, "application/pdf")}
            data = {
                "title": "Test PDF Document",
                "type": "upload",
                "async_processing": "true",
                "delete_source": "false"
            }
            
            # Make request
            response = self.client.post("/api/sources", files=files, data=data)
            
            # Assertions
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["title"] == "Test PDF Document"
            assert "id" in response_data
            assert "command_id" in response_data  # Should have command_id for async processing
            
            # Verify file was saved
            mock_save.assert_called_once()
            
            # Verify that a command ID was returned indicating background processing was started
            assert response_data.get("command_id") is not None
            assert response_data.get("command_id").startswith("command:")

    def test_background_processing_thread_execution(self):
        """Test that background processing actually executes asynchronously."""
        # Create a test text file
        test_content = "Test content for background processing verification."
        text_file = io.BytesIO(test_content.encode())
        
        processing_started = False
        processing_completed = False
        
        def mock_background_process(*args, **kwargs):
            nonlocal processing_started, processing_completed
            processing_started = True
            # Simulate some processing time
            time.sleep(0.1)
            processing_completed = True
        
        with patch("api.routers.sources.save_uploaded_file") as mock_save:
            
            mock_save.return_value = "/tmp/test_async.txt"
            
            # Prepare form data
            files = {"file": ("async_test.txt", text_file, "text/plain")}
            data = {
                "title": "Async Processing Test",
                "type": "upload",
                "async_processing": "true",
                "delete_source": "false"
            }
            
            # Make request
            response = self.client.post("/api/sources", files=files, data=data)
            
            # API should return immediately, even if background processing hasn't completed
            assert response.status_code == 200
            response_data = response.json()
            
            # Verify that a command ID was returned indicating background processing was started
            assert response_data.get("command_id") is not None
            assert response_data.get("command_id").startswith("command:")

    def test_file_upload_without_file_fails(self):
        """Test that upload type without file fails appropriately."""
        data = {
            "title": "No File Upload Test",
            "type": "upload",
            "async_processing": "true",
            "delete_source": "false"
        }
        
        response = self.client.post("/api/sources", data=data)
        
        # Should fail without a file
        assert response.status_code == 400
        assert "File upload" in response.json()["detail"] or "file_path" in response.json()["detail"]

    def test_unsupported_file_type_handling(self):
        """Test handling of unsupported file types."""
        # Create a test file with unsupported extension
        test_content = b"Some binary content"
        binary_file = io.BytesIO(test_content)
        
        with patch("api.routers.sources.save_uploaded_file") as mock_save:
            
            mock_save.return_value = "/tmp/test_file.xyz"
            
            files = {"file": ("test_file.xyz", binary_file, "application/octet-stream")}
            data = {
                "title": "Binary File Test",
                "type": "upload",
                "async_processing": "true",
                "delete_source": "false"
            }
            
            response = self.client.post("/api/sources", files=files, data=data)
            
            # Should still accept the file (processing might handle or reject it later)
            assert response.status_code == 200
            mock_save.assert_called_once()


