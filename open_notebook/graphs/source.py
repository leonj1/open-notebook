import operator
from pathlib import Path
from typing import Any, Dict, List, Optional

from content_core import extract_content
from content_core.common import ProcessSourceState
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger
from typing_extensions import Annotated, TypedDict

from api.pdf_parser_service import get_pdf_parser_service
from open_notebook.domain.content_settings import ContentSettings
from open_notebook.domain.notebook import Asset, Source
from open_notebook.domain.transformation import Transformation
from open_notebook.graphs.transformation import graph as transform_graph


class SourceState(TypedDict):
    content_state: ProcessSourceState
    apply_transformations: List[Transformation]
    source_id: str
    notebook_ids: List[str]
    source: Source
    transformation: Annotated[list, operator.add]
    embed: bool


class TransformationState(TypedDict):
    source: Source
    transformation: Transformation


async def content_process(state: SourceState) -> dict:
    content_settings = ContentSettings(
        default_content_processing_engine_doc="auto",
        default_content_processing_engine_url="auto",
        default_embedding_option="ask",
        auto_delete_files="yes",
        youtube_preferred_languages=["en", "pt", "es", "de", "nl", "en-GB", "fr", "hi", "ja"]
    )
    content_state: Dict[str, Any] = state["content_state"]  # type: ignore[assignment]

    # Check if this is a PDF file - if so, use our dedicated PDFParserService
    file_path = content_state.get("file_path")
    if file_path and Path(file_path).suffix.lower() == ".pdf":
        logger.info(f"Using PDFParserService (docling-parse) for PDF: {file_path}")

        try:
            # Use our dedicated PDF parser service (docling-only)
            pdf_service = get_pdf_parser_service()
            markdown_content = pdf_service.parse_pdf_to_markdown(
                file_path=file_path,
                extract_level="line"  # Use line-level extraction for better formatting
            )

            # Extract title from filename if not provided
            title = content_state.get("title") or Path(file_path).stem

            # Create ProcessSourceState compatible with content-core format
            processed_state: ProcessSourceState = {
                "url": content_state.get("url", ""),
                "file_path": file_path,
                "content": markdown_content,
                "title": title,
            }

            logger.info(
                f"Successfully parsed PDF with docling-parse: "
                f"{len(markdown_content)} characters extracted"
            )

            return {"content_state": processed_state}

        except Exception as e:
            logger.error(f"PDFParserService failed for {file_path}: {e}")
            logger.info("Falling back to content-core for PDF processing")
            # Fall through to content-core on error

    # For non-PDF files or if PDF parsing failed, use content-core
    content_state["url_engine"] = (
        content_settings.default_content_processing_engine_url or "auto"
    )
    content_state["document_engine"] = (
        content_settings.default_content_processing_engine_doc or "auto"
    )
    content_state["output_format"] = "markdown"

    processed_state = await extract_content(content_state)
    return {"content_state": processed_state}


async def save_source(state: SourceState) -> dict:
    content_state = state["content_state"]

    # Get existing source using the provided source_id
    source = await Source.get(state["source_id"])
    if not source:
        raise ValueError(f"Source with ID {state['source_id']} not found")

    # Update the source with processed content
    source.asset = Asset(url=content_state.url, file_path=content_state.file_path)
    source.full_text = content_state.content
    
    # Preserve existing title if none provided in processed content
    if content_state.title:
        source.title = content_state.title
    
    await source.save()

    # NOTE: Notebook associations are created by the API immediately for UI responsiveness
    # No need to create them here to avoid duplicate edges

    if state["embed"]:
        logger.debug("Embedding content for vector search")
        await source.vectorize()

    return {"source": source}


def trigger_transformations(state: SourceState, config: RunnableConfig) -> List[Send]:
    if len(state["apply_transformations"]) == 0:
        return []

    to_apply = state["apply_transformations"]
    logger.debug(f"Applying transformations {to_apply}")

    return [
        Send(
            "transform_content",
            {
                "source": state["source"],
                "transformation": t,
            },
        )
        for t in to_apply
    ]


async def transform_content(state: TransformationState) -> Optional[dict]:
    source = state["source"]
    content = source.full_text
    if not content:
        return None
    transformation: Transformation = state["transformation"]

    logger.debug(f"Applying transformation {transformation.name}")
    result = await transform_graph.ainvoke(
        dict(input_text=content, transformation=transformation)  # type: ignore[arg-type]
    )
    await source.add_insight(transformation.title, result["output"])
    return {
        "transformation": [
            {
                "output": result["output"],
                "transformation_name": transformation.name,
            }
        ]
    }


# Create and compile the workflow
workflow = StateGraph(SourceState)

# Add nodes
workflow.add_node("content_process", content_process)
workflow.add_node("save_source", save_source)
workflow.add_node("transform_content", transform_content)
# Define the graph edges
workflow.add_edge(START, "content_process")
workflow.add_edge("content_process", "save_source")
workflow.add_conditional_edges(
    "save_source", trigger_transformations, ["transform_content"]
)
workflow.add_edge("transform_content", END)

# Compile the graph
source_graph = workflow.compile()
