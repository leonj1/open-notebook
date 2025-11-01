"""
PDF parsing service using Docling.

This service provides functionality to parse PDF documents using the docling-parse library,
extracting text content with coordinate information at various granularity levels.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger


@dataclass
class TextCell:
    """Represents a text cell extracted from a PDF with its coordinates."""
    text: str
    x: float
    y: float
    width: float
    height: float
    page_number: int


@dataclass
class PDFPage:
    """Represents a parsed PDF page with extracted text cells."""
    page_number: int
    text_cells: List[TextCell]

    @property
    def text(self) -> str:
        """Get all text from the page as a single string."""
        return " ".join(cell.text for cell in self.text_cells)


@dataclass
class PDFParseResult:
    """Result of PDF parsing operation."""
    pages: List[PDFPage]
    total_pages: int
    file_path: str

    @property
    def full_text(self) -> str:
        """Get all text from the PDF as a single string."""
        return "\n\n".join(page.text for page in self.pages)


class PDFParserService:
    """
    Service for parsing PDF documents using Docling.

    This service uses the docling-parse library to extract text content
    from PDF files with coordinate information.
    """

    def __init__(self):
        """Initialize the PDF parser service."""
        self._parser = None
        self._ensure_dependencies()

    def _ensure_dependencies(self):
        """Ensure required dependencies are available."""
        try:
            from docling_parse.pdf_parser import DoclingPdfParser
            self._parser = DoclingPdfParser()
            logger.info("DoclingPdfParser initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import docling-parse: {e}")
            raise ImportError(
                "docling-parse is required for PDF parsing. "
                "Install it with: pip install docling-parse"
            ) from e

    def parse_pdf(
        self,
        file_path: Union[str, Path],
        extract_level: str = "word"
    ) -> PDFParseResult:
        """
        Parse a PDF file and extract text content.

        Args:
            file_path: Path to the PDF file to parse
            extract_level: Granularity level for text extraction.
                          Options: "char", "word", "line" (default: "word")

        Returns:
            PDFParseResult containing parsed pages and text content

        Raises:
            FileNotFoundError: If the PDF file doesn't exist
            ValueError: If extract_level is invalid
            Exception: If parsing fails
        """
        from docling_core.types.doc.page import TextCellUnit

        # Validate inputs
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if not file_path.suffix.lower() == ".pdf":
            raise ValueError(f"File must be a PDF: {file_path}")

        # Map extract_level to TextCellUnit
        level_map = {
            "char": TextCellUnit.CHAR,
            "word": TextCellUnit.WORD,
            "line": TextCellUnit.LINE,
        }

        if extract_level not in level_map:
            raise ValueError(
                f"Invalid extract_level: {extract_level}. "
                f"Must be one of: {list(level_map.keys())}"
            )

        unit_type = level_map[extract_level]

        try:
            logger.info(f"Parsing PDF: {file_path} at {extract_level} level")

            # Load the PDF document
            pdf_doc = self._parser.load(path_or_stream=str(file_path))

            pages: List[PDFPage] = []

            # Iterate through pages and extract text
            for page_no, pred_page in pdf_doc.iterate_pages():
                text_cells: List[TextCell] = []

                # Extract cells at the specified granularity
                for cell in pred_page.iterate_cells(unit_type=unit_type):
                    text_cell = TextCell(
                        text=cell.text,
                        x=cell.rect.r_x0,  # Left edge x-coordinate
                        y=cell.rect.r_y0,  # Bottom edge y-coordinate
                        width=cell.rect.width,
                        height=cell.rect.height,
                        page_number=page_no
                    )
                    text_cells.append(text_cell)

                pdf_page = PDFPage(
                    page_number=page_no,
                    text_cells=text_cells
                )
                pages.append(pdf_page)

                logger.debug(
                    f"Extracted {len(text_cells)} {extract_level}s from page {page_no}"
                )

            result = PDFParseResult(
                pages=pages,
                total_pages=len(pages),
                file_path=str(file_path)
            )

            logger.info(
                f"Successfully parsed PDF: {len(pages)} pages, "
                f"{len(result.full_text)} characters"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to parse PDF {file_path}: {e}")
            raise

    def parse_pdf_to_text(
        self,
        file_path: Union[str, Path],
        extract_level: str = "word"
    ) -> str:
        """
        Parse a PDF file and return the text content as a string.

        This is a convenience method that returns just the text content
        without coordinate information.

        Args:
            file_path: Path to the PDF file to parse
            extract_level: Granularity level for text extraction.
                          Options: "char", "word", "line" (default: "word")

        Returns:
            Extracted text content as a string
        """
        result = self.parse_pdf(file_path, extract_level)
        return result.full_text

    def parse_pdf_to_markdown(
        self,
        file_path: Union[str, Path],
        extract_level: str = "line"
    ) -> str:
        """
        Parse a PDF file and return the text content formatted as markdown.

        Args:
            file_path: Path to the PDF file to parse
            extract_level: Granularity level for text extraction.
                          Options: "char", "word", "line" (default: "line")

        Returns:
            Extracted text content formatted as markdown
        """
        result = self.parse_pdf(file_path, extract_level)

        # Format as markdown with page breaks
        markdown_parts = []
        for page in result.pages:
            markdown_parts.append(f"## Page {page.page_number}\n\n{page.text}")

        return "\n\n---\n\n".join(markdown_parts)


# Singleton instance for easy access
_pdf_parser_service: Optional[PDFParserService] = None


def get_pdf_parser_service() -> PDFParserService:
    """
    Get or create the singleton PDF parser service instance.

    Returns:
        PDFParserService instance
    """
    global _pdf_parser_service
    if _pdf_parser_service is None:
        _pdf_parser_service = PDFParserService()
    return _pdf_parser_service
