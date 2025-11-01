"""
Source Processor Service

This service handles background processing of sources, including loading transformations,
executing the source graph, and tracking progress via command status updates.
"""

import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Type

from loguru import logger

from open_notebook.domain.transformation import Transformation


class SourceProcessorService:
    """
    Service for processing sources in the background.

    This service orchestrates the source processing workflow including:
    - Loading transformations from IDs
    - Executing the source processing graph
    - Updating command status for progress tracking
    - Gathering and reporting results

    All external dependencies are injected via constructor to enable testing
    and flexibility.
    """

    def __init__(
        self,
        command_service: Any,
        transformation_loader: Type[Transformation],
        source_graph: Any,
    ):
        """
        Initialize the source processor service with required dependencies.

        Args:
            command_service: Service for updating command status (e.g., CommandTableService)
                Must have an async update_command_status(command_id, status, progress, result, error_message) method
            transformation_loader: Class for loading transformation objects (e.g., Transformation)
                Must have an async get(transformation_id) class method
            source_graph: Graph executor for processing sources
                Must have an async ainvoke(input_dict) method that returns a dict with 'source' key
        """
        self.command_service = command_service
        self.transformation_loader = transformation_loader
        self.source_graph = source_graph

    async def process_source(
        self,
        command_id: str,
        source_id: str,
        content_state: Dict[str, Any],
        notebook_ids: List[str],
        transformation_ids: List[str],
        embed: bool,
    ) -> None:
        """
        Process a source in the background, tracking progress via command status.

        This method:
        1. Updates command status to "running" with progress tracking
        2. Loads transformation objects from IDs
        3. Executes the source processing graph
        4. Gathers results (embedded chunks, insights)
        5. Updates command status to "completed" or "failed" with results

        Args:
            command_id: Command ID for tracking this processing job
            source_id: ID of the source being processed
            content_state: Content state dict containing file path or text content
            notebook_ids: List of notebook IDs to associate with the source
            transformation_ids: List of transformation IDs to apply
            embed: Whether to create embeddings for the source

        Note:
            This method catches all exceptions and updates the command status
            with error information rather than raising exceptions.
        """
        start_time = time.time()

        try:
            logger.info(f"Starting background processing for source: {source_id}")

            # Update status to running
            await self.command_service.update_command_status(
                command_id, "running", progress=10
            )

            # Load transformation objects from IDs
            transformations = await self._load_transformations(transformation_ids)

            logger.info(f"Loaded {len(transformations)} transformations")
            await self.command_service.update_command_status(
                command_id, "running", progress=20
            )

            # Execute source_graph
            logger.info("Executing source_graph...")
            result = await self.source_graph.ainvoke(
                {
                    "content_state": content_state,
                    "notebook_ids": notebook_ids,
                    "apply_transformations": transformations,
                    "embed": embed,
                    "source_id": source_id,
                }
            )

            await self.command_service.update_command_status(
                command_id, "running", progress=80
            )

            processed_source = result["source"]

            # Gather results
            embedded_chunks = (
                await processed_source.get_embedded_chunks() if embed else 0
            )
            insights_list = await processed_source.get_insights()
            insights_created = len(insights_list)

            processing_time = time.time() - start_time

            # Update command with success result
            result_data = {
                "success": True,
                "source_id": str(processed_source.id),
                "embedded_chunks": embedded_chunks,
                "insights_created": insights_created,
                "processing_time": processing_time,
                "execution_metadata": {
                    "started_at": datetime.fromtimestamp(start_time).isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

            await self.command_service.update_command_status(
                command_id,
                "completed",
                progress=100,
                result=result_data,
            )

            logger.info(
                f"✅ Background processing completed for source {source_id} in {processing_time:.2f}s"
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Background processing failed for source {source_id}: {e}")
            logger.exception(e)

            # Update command with error
            result_data = {
                "success": False,
                "source_id": source_id,
                "processing_time": processing_time,
                "error_message": str(e),
                "execution_metadata": {
                    "started_at": datetime.fromtimestamp(start_time).isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

            await self.command_service.update_command_status(
                command_id,
                "failed",
                result=result_data,
                error_message=str(e),
            )

    async def _load_transformations(
        self, transformation_ids: List[str]
    ) -> List[Transformation]:
        """
        Load transformation objects from their IDs.

        Args:
            transformation_ids: List of transformation IDs to load

        Returns:
            List of loaded Transformation objects

        Raises:
            ValueError: If any transformation is not found
        """
        transformations = []
        for trans_id in transformation_ids:
            transformation = await self.transformation_loader.get(trans_id)
            if not transformation:
                raise ValueError(f"Transformation '{trans_id}' not found")
            transformations.append(transformation)
        return transformations
