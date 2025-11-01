# Tests

This directory contains the test suite for Open Notebook.

## Test Structure

- `test_domain.py` - Domain model validation and business logic tests
- `test_graphs.py` - Graph workflow and transformation tests
- `test_models_api.py` - Model API integration tests
- `test_notebook_persistence.py` - Notebook persistence tests
- `test_utils.py` - Utility function tests
- `test_pdf_parsing.py` - PDF parsing integration tests
- `manual_test_pdf.py` - Standalone PDF parsing test script

## Test Assets

The `assets/` directory contains test files:
- `i1065sk1.pdf` - IRS PDF document for testing PDF parsing functionality

See [assets/README.md](assets/README.md) for more details.

## Running Tests

### Using uv (recommended)

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_pdf_parsing.py -v

# Run specific test
uv run pytest tests/test_pdf_parsing.py::TestPDFParsing::test_pdf_content_extraction -v
```

### Manual Testing

Some tests can be run standalone without pytest:

```bash
# Test PDF parsing directly
python3 tests/manual_test_pdf.py
```

## Test Dependencies

Dev dependencies (defined in `pyproject.toml`):
- pytest>=8.0.0
- pytest-asyncio>=1.2.0
- mypy>=1.11.1
- ruff>=0.5.5

Install with:
```bash
uv pip install -e ".[dev]"
```
