"""
Background Task Processing for SQLite Mode

This module provides background task processing capabilities when using SQLite.
Since SQLite doesn't support the surreal-commands worker, we use FastAPI's
BackgroundTasks to process jobs within the API server process.
"""

from typing import Any, Dict, List

from open_notebook.domain.transformation import Transformation
from open_notebook.graphs.source import source_graph
from open_notebook.services import CommandTableService, SourceProcessorService


# Create a singleton instance of the processor with its dependencies
_source_processor = SourceProcessorService(
    command_service=CommandTableService,
    transformation_loader=Transformation,
    source_graph=source_graph,
)


async def process_source_background(
    command_id: str,
    source_id: str,
    content_state: Dict[str, Any],
    notebook_ids: List[str],
    transformation_ids: List[str],
    embed: bool,
):
    """
    Background task to process a source using the source_graph.

    This is a convenience wrapper around SourceProcessorService.process_source()
    that uses the module-level singleton instance with pre-configured dependencies.

    This runs in a FastAPI background task thread, updating the command
    record as it progresses so clients can poll for status.

    Args:
        command_id: Command ID for tracking this processing job
        source_id: ID of the source being processed
        content_state: Content state dict containing file path or text content
        notebook_ids: List of notebook IDs to associate with the source
        transformation_ids: List of transformation IDs to apply
        embed: Whether to create embeddings for the source
    """
    await _source_processor.process_source(
        command_id=command_id,
        source_id=source_id,
        content_state=content_state,
        notebook_ids=notebook_ids,
        transformation_ids=transformation_ids,
        embed=embed,
    )
