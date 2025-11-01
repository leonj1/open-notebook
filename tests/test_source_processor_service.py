"""
Tests for SourceProcessorService with dependency injection.

This test suite demonstrates how to use SourceProcessorService with custom
dependencies injected via the constructor, enabling testability and flexibility.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from open_notebook.services import SourceProcessorService


class TestSourceProcessorService:
    """Test suite for SourceProcessorService with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_process_source_with_mock_dependencies(self):
        """Test that the service works with fully mocked dependencies."""
        # Create mock dependencies
        mock_command_service = MagicMock()
        mock_command_service.update_command_status = AsyncMock()

        mock_transformation_loader = MagicMock()
        mock_transformation = MagicMock()
        mock_transformation_loader.get = AsyncMock(return_value=mock_transformation)

        mock_source_graph = MagicMock()
        mock_processed_source = MagicMock()
        mock_processed_source.id = "source:test123"
        mock_processed_source.get_embedded_chunks = AsyncMock(return_value=5)
        mock_processed_source.get_insights = AsyncMock(return_value=[1, 2, 3])
        mock_source_graph.ainvoke = AsyncMock(
            return_value={"source": mock_processed_source}
        )

        # Create service with injected dependencies
        service = SourceProcessorService(
            command_service=mock_command_service,
            transformation_loader=mock_transformation_loader,
            source_graph=mock_source_graph,
        )

        # Execute process_source
        await service.process_source(
            command_id="command:test123",
            source_id="source:test456",
            content_state={"content_type": "text", "text": "Test content"},
            notebook_ids=["notebook:1"],
            transformation_ids=["trans:1"],
            embed=True,
        )

        # Verify command status was updated correctly
        assert mock_command_service.update_command_status.call_count == 4

        # Verify first call: running with progress 10
        first_call = mock_command_service.update_command_status.call_args_list[0]
        assert first_call[0][0] == "command:test123"  # command_id
        assert first_call[0][1] == "running"  # status
        assert first_call[1]["progress"] == 10

        # Verify last call: completed with progress 100 and result
        last_call = mock_command_service.update_command_status.call_args_list[3]
        assert last_call[0][0] == "command:test123"
        assert last_call[0][1] == "completed"
        assert last_call[1]["progress"] == 100
        assert last_call[1]["result"]["success"] is True
        assert last_call[1]["result"]["source_id"] == "source:test123"
        assert last_call[1]["result"]["embedded_chunks"] == 5
        assert last_call[1]["result"]["insights_created"] == 3

        # Verify transformation was loaded
        mock_transformation_loader.get.assert_called_once_with("trans:1")

        # Verify source_graph was invoked
        mock_source_graph.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_source_handles_transformation_not_found(self):
        """Test that the service handles missing transformations correctly."""
        # Create mock dependencies
        mock_command_service = MagicMock()
        mock_command_service.update_command_status = AsyncMock()

        mock_transformation_loader = MagicMock()
        mock_transformation_loader.get = AsyncMock(return_value=None)  # Not found

        mock_source_graph = MagicMock()

        # Create service with injected dependencies
        service = SourceProcessorService(
            command_service=mock_command_service,
            transformation_loader=mock_transformation_loader,
            source_graph=mock_source_graph,
        )

        # Execute process_source - should handle error gracefully
        await service.process_source(
            command_id="command:test123",
            source_id="source:test456",
            content_state={"content_type": "text", "text": "Test content"},
            notebook_ids=["notebook:1"],
            transformation_ids=["trans:missing"],
            embed=False,
        )

        # Verify final call was "failed" with error message
        last_call = mock_command_service.update_command_status.call_args_list[-1]
        assert last_call[0][1] == "failed"
        assert "Transformation 'trans:missing' not found" in last_call[1]["error_message"]

    @pytest.mark.asyncio
    async def test_process_source_handles_graph_exception(self):
        """Test that the service handles source_graph exceptions correctly."""
        # Create mock dependencies
        mock_command_service = MagicMock()
        mock_command_service.update_command_status = AsyncMock()

        mock_transformation_loader = MagicMock()

        mock_source_graph = MagicMock()
        mock_source_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("Graph processing failed")
        )

        # Create service with injected dependencies
        service = SourceProcessorService(
            command_service=mock_command_service,
            transformation_loader=mock_transformation_loader,
            source_graph=mock_source_graph,
        )

        # Execute process_source - should handle error gracefully
        await service.process_source(
            command_id="command:test123",
            source_id="source:test456",
            content_state={"content_type": "text", "text": "Test content"},
            notebook_ids=["notebook:1"],
            transformation_ids=[],
            embed=False,
        )

        # Verify final call was "failed" with error message
        last_call = mock_command_service.update_command_status.call_args_list[-1]
        assert last_call[0][1] == "failed"
        assert "Graph processing failed" in last_call[1]["error_message"]
        assert last_call[1]["result"]["success"] is False
