# Test Assets

This directory contains assets used for testing Open Notebook functionality.

## PDF Test Asset

### i1065sk1.pdf

- **Source**: https://www.irs.gov/pub/irs-pdf/i1065sk1.pdf
- **Description**: IRS Schedule K-1 (Form 1065) instructions PDF document
- **Size**: ~438 KB
- **Purpose**: Integration testing for PDF parsing functionality using PyMuPDF and content-core
- **Added**: 2025-11-01

This PDF is used to validate that the Open Notebook can successfully:
- Parse PDF documents using the content-core library
- Extract text content from PDFs
- Support both PyMuPDF and Docling engines
- Convert PDF content to markdown format

### Running PDF Parsing Tests

To run the PDF parsing integration tests:

```bash
# Using pytest (requires dev dependencies)
uv run pytest tests/test_pdf_parsing.py -v

# Or using the manual test script (standalone)
python3 tests/manual_test_pdf.py
```

Note: Tests require the following dependencies:
- `content-core>=1.0.2`
- `pymupdf>=1.26.5`
- `pytest>=8.0.0` (for pytest tests)
- `pytest-asyncio>=1.2.0` (for pytest tests)
