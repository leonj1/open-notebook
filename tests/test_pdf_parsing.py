"""
Integration tests for PDF parsing functionality.

This test suite validates that the content-core library can successfully
parse PDF documents using PyMuPDF.
"""

import os
from pathlib import Path

import pytest

# Conditional imports based on availability
try:
    from content_core import extract_content
    from content_core.common import ProcessSourceState
    CONTENT_CORE_AVAILABLE = True
except ImportError:
    CONTENT_CORE_AVAILABLE = False


# ============================================================================
# TEST SUITE: PDF Parsing Integration Tests
# ============================================================================


@pytest.mark.skipif(not CONTENT_CORE_AVAILABLE, reason="content-core not installed")
class TestPDFParsing:
    """Integration tests for PDF document parsing."""

    @pytest.fixture
    def test_pdf_path(self) -> Path:
        """Fixture providing path to test PDF file."""
        test_dir = Path(__file__).parent
        pdf_path = test_dir / "assets" / "i1065sk1.pdf"

        if not pdf_path.exists():
            pytest.skip(f"Test PDF not found at {pdf_path}")

        return pdf_path

    @pytest.mark.asyncio
    async def test_pdf_file_exists(self, test_pdf_path: Path):
        """Test that the test PDF file exists and is readable."""
        assert test_pdf_path.exists(), "Test PDF file should exist"
        assert test_pdf_path.is_file(), "Path should point to a file"
        assert test_pdf_path.suffix == ".pdf", "File should have .pdf extension"

        # Check file size (should be around 438KB)
        file_size = test_pdf_path.stat().st_size
        assert file_size > 0, "PDF file should not be empty"
        assert file_size > 100000, "PDF file should be at least 100KB"

    @pytest.mark.asyncio
    async def test_pdf_parsing_basic(self, test_pdf_path: Path):
        """Test basic PDF parsing functionality."""
        # Create a ProcessSourceState for the PDF
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf_path),
            "content": "",
            "title": "",
            "document_engine": "auto",
            "url_engine": "auto",
            "output_format": "markdown"
        }

        # Process the PDF
        result = await extract_content(state)

        # Validate result structure
        assert isinstance(result, dict), "Result should be a dictionary"
        assert "content" in result, "Result should contain 'content' key"
        assert "file_path" in result, "Result should contain 'file_path' key"

    @pytest.mark.asyncio
    async def test_pdf_content_extraction(self, test_pdf_path: Path):
        """Test that PDF content is successfully extracted."""
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf_path),
            "content": "",
            "title": "",
            "document_engine": "auto",
            "url_engine": "auto",
            "output_format": "markdown"
        }

        result = await extract_content(state)

        # Validate content was extracted
        assert result["content"], "Content should not be empty"
        assert len(result["content"]) > 100, "Content should be substantial"

        # IRS PDF should contain certain expected text
        content = result["content"].lower()

        # Check for IRS-related content (these are likely in the document)
        # Note: Adjust these assertions based on actual PDF content
        assert any(keyword in content for keyword in [
            "irs", "schedule", "partnership", "k-1", "1065"
        ]), "Content should contain IRS/tax-related keywords"

    @pytest.mark.asyncio
    async def test_pdf_with_pymupdf_engine(self, test_pdf_path: Path):
        """Test PDF parsing explicitly with PyMuPDF engine."""
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf_path),
            "content": "",
            "title": "",
            "document_engine": "pymupdf",  # Explicitly request PyMuPDF
            "url_engine": "auto",
            "output_format": "markdown"
        }

        result = await extract_content(state)

        # Validate successful processing
        assert result["content"], "PyMuPDF should extract content"
        assert len(result["content"]) > 100, "PyMuPDF should extract substantial content"

    @pytest.mark.asyncio
    async def test_pdf_with_docling_engine(self, test_pdf_path: Path):
        """Test PDF parsing with Docling engine (default)."""
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf_path),
            "content": "",
            "title": "",
            "document_engine": "docling",  # Explicitly request Docling
            "url_engine": "auto",
            "output_format": "markdown"
        }

        try:
            result = await extract_content(state)

            # Validate successful processing
            assert result["content"], "Docling should extract content"
            assert len(result["content"]) > 100, "Docling should extract substantial content"
        except Exception as e:
            # Docling might not be available in all environments
            if "docling" in str(e).lower():
                pytest.skip(f"Docling engine not available: {e}")
            raise

    @pytest.mark.asyncio
    async def test_pdf_markdown_output(self, test_pdf_path: Path):
        """Test that PDF is converted to markdown format."""
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf_path),
            "content": "",
            "title": "",
            "document_engine": "auto",
            "url_engine": "auto",
            "output_format": "markdown"
        }

        result = await extract_content(state)
        content = result["content"]

        # Check for markdown-like formatting
        # This is a basic check - actual markdown formatting depends on the engine
        assert isinstance(content, str), "Content should be a string"
        assert len(content.strip()) > 0, "Content should not be just whitespace"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
