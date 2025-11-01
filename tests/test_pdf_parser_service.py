"""
Integration tests for PDF parser service using Docling.

This test suite validates the PDFParserService class that wraps
the docling-parse library for PDF parsing functionality.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Conditional imports based on availability
try:
    from api.pdf_parser_service import (
        PDFPage,
        PDFParseResult,
        PDFParserService,
        TextCell,
        get_pdf_parser_service,
    )
    from docling_parse.pdf_parser import DoclingPdfParser
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    # Create dummy classes for type checking
    if TYPE_CHECKING:
        from api.pdf_parser_service import (
            PDFPage,
            PDFParseResult,
            PDFParserService,
            TextCell,
        )
    else:
        PDFPage = None
        PDFParseResult = None
        PDFParserService = None
        TextCell = None


# ============================================================================
# TEST SUITE: PDF Parser Service Integration Tests
# ============================================================================


@pytest.mark.skipif(not DOCLING_AVAILABLE, reason="docling-parse not installed")
class TestPDFParserService:
    """Integration tests for PDF parser service."""

    @pytest.fixture
    def test_pdf_path(self) -> Path:
        """Fixture providing path to test PDF file."""
        test_dir = Path(__file__).parent
        pdf_path = test_dir / "assets" / "i1065sk1.pdf"

        if not pdf_path.exists():
            pytest.skip(f"Test PDF not found at {pdf_path}")

        return pdf_path

    @pytest.fixture
    def parser_service(self) -> PDFParserService:
        """Fixture providing a PDF parser service instance."""
        return PDFParserService()

    def test_service_initialization(self, parser_service: PDFParserService):
        """Test that the parser service initializes correctly."""
        assert parser_service is not None
        assert parser_service._parser is not None

    def test_singleton_service(self):
        """Test that get_pdf_parser_service returns a singleton."""
        service1 = get_pdf_parser_service()
        service2 = get_pdf_parser_service()
        assert service1 is service2

    def test_parse_pdf_basic(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test basic PDF parsing functionality."""
        result = parser_service.parse_pdf(test_pdf_path)

        # Validate result structure
        assert isinstance(result, PDFParseResult)
        assert result.total_pages > 0
        assert len(result.pages) == result.total_pages
        assert result.file_path == str(test_pdf_path)

    def test_parse_pdf_pages(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test that PDF pages are correctly parsed."""
        result = parser_service.parse_pdf(test_pdf_path)

        # Check pages
        assert len(result.pages) > 0

        for page in result.pages:
            assert isinstance(page, PDFPage)
            assert page.page_number >= 0
            assert len(page.text_cells) > 0

            # Check text cells
            for cell in page.text_cells:
                assert isinstance(cell, TextCell)
                assert isinstance(cell.text, str)
                assert len(cell.text) > 0
                assert cell.x >= 0
                assert cell.y >= 0
                assert cell.width >= 0
                assert cell.height >= 0

    def test_parse_pdf_text_content(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test that text content is extracted correctly."""
        result = parser_service.parse_pdf(test_pdf_path)

        # Check full text
        full_text = result.full_text
        assert isinstance(full_text, str)
        assert len(full_text) > 100

        # IRS PDF should contain certain keywords
        full_text_lower = full_text.lower()
        expected_keywords = ["schedule", "partnership", "k-1", "1065"]

        found_keywords = [
            kw for kw in expected_keywords if kw in full_text_lower
        ]
        assert len(found_keywords) > 0, (
            f"Expected to find at least one of {expected_keywords} "
            f"in PDF content"
        )

    def test_parse_pdf_word_level(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test PDF parsing at word level."""
        result = parser_service.parse_pdf(test_pdf_path, extract_level="word")

        assert result.total_pages > 0
        assert len(result.full_text) > 100

        # Word level should produce many small cells
        first_page = result.pages[0]
        assert len(first_page.text_cells) > 50  # Words are granular

    def test_parse_pdf_line_level(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test PDF parsing at line level."""
        result = parser_service.parse_pdf(test_pdf_path, extract_level="line")

        assert result.total_pages > 0
        assert len(result.full_text) > 100

        # Line level should produce fewer, larger cells than word level
        first_page = result.pages[0]
        assert len(first_page.text_cells) > 0

    def test_parse_pdf_char_level(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test PDF parsing at character level."""
        result = parser_service.parse_pdf(test_pdf_path, extract_level="char")

        assert result.total_pages > 0
        assert len(result.full_text) > 100

        # Character level should produce many cells
        first_page = result.pages[0]
        assert len(first_page.text_cells) > 100  # Characters are very granular

    def test_parse_pdf_to_text(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test convenience method for extracting text only."""
        text = parser_service.parse_pdf_to_text(test_pdf_path)

        assert isinstance(text, str)
        assert len(text) > 100

        # Check for expected content
        text_lower = text.lower()
        assert any(
            keyword in text_lower
            for keyword in ["schedule", "partnership", "k-1", "1065"]
        )

    def test_parse_pdf_to_markdown(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test conversion to markdown format."""
        markdown = parser_service.parse_pdf_to_markdown(test_pdf_path)

        assert isinstance(markdown, str)
        assert len(markdown) > 100

        # Should contain markdown page headers
        assert "## Page" in markdown
        assert "---" in markdown  # Page separator

        # Should contain expected content
        markdown_lower = markdown.lower()
        assert any(
            keyword in markdown_lower
            for keyword in ["schedule", "partnership", "k-1", "1065"]
        )

    def test_parse_pdf_file_not_found(self, parser_service: PDFParserService):
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            parser_service.parse_pdf("/nonexistent/file.pdf")

    def test_parse_pdf_invalid_file_type(
        self,
        parser_service: PDFParserService,
        tmp_path: Path
    ):
        """Test that ValueError is raised for non-PDF files."""
        # Create a temporary non-PDF file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not a PDF")

        with pytest.raises(ValueError, match="File must be a PDF"):
            parser_service.parse_pdf(txt_file)

    def test_parse_pdf_invalid_extract_level(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test that ValueError is raised for invalid extract level."""
        with pytest.raises(ValueError, match="Invalid extract_level"):
            parser_service.parse_pdf(test_pdf_path, extract_level="invalid")

    def test_page_text_property(
        self,
        parser_service: PDFParserService,
        test_pdf_path: Path
    ):
        """Test the PDFPage.text property."""
        result = parser_service.parse_pdf(test_pdf_path)

        first_page = result.pages[0]
        page_text = first_page.text

        assert isinstance(page_text, str)
        assert len(page_text) > 0

        # Text should be composed of all cell texts
        for cell in first_page.text_cells[:5]:  # Check first few cells
            assert cell.text in page_text or cell.text.strip() in page_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
