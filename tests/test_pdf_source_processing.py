"""
Integration tests for PDF source processing using PDFParserService.

This test suite validates that the source processing workflow correctly
uses PDFParserService (docling-parse) for PDF files instead of content-core.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Conditional imports based on availability
try:
    from api.pdf_parser_service import PDFParserService, get_pdf_parser_service
    from open_notebook.graphs.source import content_process, SourceState
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


@pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="Required dependencies not available"
)
class TestPDFSourceProcessing:
    """Integration tests for PDF source processing workflow."""

    @pytest.fixture
    def test_pdf_path(self) -> Path:
        """Fixture providing path to test PDF file."""
        test_dir = Path(__file__).parent
        pdf_path = test_dir / "assets" / "i1065sk1.pdf"

        if not pdf_path.exists():
            pytest.skip(f"Test PDF not found at {pdf_path}")

        return pdf_path

    @pytest.mark.asyncio
    async def test_content_process_detects_pdf(self, test_pdf_path: Path):
        """Test that content_process detects PDF files and routes to PDFParserService."""

        # Create a mock state with PDF file path
        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        # Call content_process
        result = await content_process(state)

        # Verify the result
        assert "content_state" in result
        content_state = result["content_state"]

        assert content_state["file_path"] == str(test_pdf_path)
        assert "content" in content_state
        assert len(content_state["content"]) > 100
        assert "title" in content_state

        # Check for expected PDF content
        content_lower = content_state["content"].lower()
        assert any(
            keyword in content_lower
            for keyword in ["schedule", "partnership", "k-1", "1065"]
        ), "Expected IRS form keywords in PDF content"

    @pytest.mark.asyncio
    async def test_content_process_uses_docling_parser(self, test_pdf_path: Path):
        """Test that PDFParserService is actually called for PDF files."""

        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        # Mock the PDFParserService to verify it's called
        with patch('open_notebook.graphs.source.get_pdf_parser_service') as mock_get_service:
            mock_service = MagicMock(spec=PDFParserService)
            mock_service.parse_pdf_to_markdown.return_value = "# Test PDF Content\n\nMocked content"
            mock_get_service.return_value = mock_service

            result = await content_process(state)

            # Verify PDFParserService was called
            mock_get_service.assert_called_once()
            mock_service.parse_pdf_to_markdown.assert_called_once_with(
                file_path=str(test_pdf_path),
                extract_level="line"
            )

            # Verify result contains mocked content
            assert result["content_state"]["content"] == "# Test PDF Content\n\nMocked content"

    @pytest.mark.asyncio
    async def test_content_process_extracts_title_from_filename(self, test_pdf_path: Path):
        """Test that title is extracted from PDF filename when not provided."""

        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
                # No title provided
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        result = await content_process(state)

        # Title should be extracted from filename
        assert result["content_state"]["title"] == "i1065sk1"

    @pytest.mark.asyncio
    async def test_content_process_preserves_provided_title(self, test_pdf_path: Path):
        """Test that provided title is preserved."""

        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
                "title": "Custom Title for PDF",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        result = await content_process(state)

        # Custom title should be preserved
        assert result["content_state"]["title"] == "Custom Title for PDF"

    @pytest.mark.asyncio
    async def test_content_process_non_pdf_file_uses_content_core(self, tmp_path: Path):
        """Test that non-PDF files are still processed by content-core."""

        # Create a dummy text file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is a test text file")

        state: SourceState = {
            "content_state": {
                "file_path": str(txt_file),
                "url": "",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        # Mock content-core's extract_content and PDFParserService
        with patch('open_notebook.graphs.source.extract_content', new_callable=AsyncMock) as mock_extract, \
             patch('open_notebook.graphs.source.get_pdf_parser_service') as mock_pdf:

            mock_extract.return_value = {
                "file_path": str(txt_file),
                "content": "Processed by content-core",
                "title": "test",
                "url": "",
            }

            result = await content_process(state)

            # Verify content-core was called
            mock_extract.assert_called_once()

            # Verify PDFParserService was NOT called
            mock_pdf.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_process_pdf_fallback_on_error(self, test_pdf_path: Path):
        """Test that content_process falls back to content-core if PDFParserService fails."""

        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        # Mock PDFParserService to raise an exception and content-core fallback
        with patch('open_notebook.graphs.source.get_pdf_parser_service') as mock_get_service, \
             patch('open_notebook.graphs.source.extract_content', new_callable=AsyncMock) as mock_extract:

            mock_service = MagicMock(spec=PDFParserService)
            mock_service.parse_pdf_to_markdown.side_effect = Exception("Parsing failed")
            mock_get_service.return_value = mock_service

            mock_extract.return_value = {
                "file_path": str(test_pdf_path),
                "content": "Fallback content from content-core",
                "title": "Fallback Title",
                "url": "",
            }

            result = await content_process(state)

            # Verify PDFParserService was attempted
            mock_get_service.assert_called_once()

            # Verify fallback to content-core
            mock_extract.assert_called_once()

            # Verify result is from content-core
            assert result["content_state"]["content"] == "Fallback content from content-core"

    @pytest.mark.asyncio
    async def test_content_process_markdown_format(self, test_pdf_path: Path):
        """Test that PDF content is properly formatted as markdown."""

        state: SourceState = {
            "content_state": {
                "file_path": str(test_pdf_path),
                "url": "",
            },
            "apply_transformations": [],
            "source_id": "test:123",
            "notebook_ids": [],
            "source": None,  # type: ignore
            "transformation": [],
            "embed": False,
        }

        result = await content_process(state)

        content = result["content_state"]["content"]

        # Verify markdown formatting
        assert "## Page" in content  # Should have page headers
        assert "---" in content  # Should have page separators


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
