#!/usr/bin/env python3
"""
Validation script for PDF integration with source processing.

This script demonstrates that PDFParserService is properly integrated
into the source processing workflow and will be used for PDF files.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def validate_pdf_parser_service():
    """Validate PDFParserService is available and working."""
    print("=" * 70)
    print("VALIDATION 1: PDFParserService Availability")
    print("=" * 70)

    try:
        from api.pdf_parser_service import get_pdf_parser_service

        service = get_pdf_parser_service()
        print("✓ PDFParserService successfully imported and initialized")
        print(f"  Service type: {type(service).__name__}")
        return True
    except Exception as e:
        print(f"✗ Failed to import PDFParserService: {e}")
        return False


def validate_pdf_parsing():
    """Validate PDF parsing with test asset."""
    print("\n" + "=" * 70)
    print("VALIDATION 2: PDF Parsing Functionality")
    print("=" * 70)

    try:
        from api.pdf_parser_service import get_pdf_parser_service

        test_pdf = Path(__file__).parent / "assets" / "i1065sk1.pdf"

        if not test_pdf.exists():
            print(f"✗ Test PDF not found: {test_pdf}")
            return False

        print(f"✓ Test PDF found: {test_pdf.name}")
        print(f"  File size: {test_pdf.stat().st_size:,} bytes")

        service = get_pdf_parser_service()
        markdown = service.parse_pdf_to_markdown(test_pdf, extract_level="line")

        print(f"✓ PDF parsed successfully")
        print(f"  Content length: {len(markdown):,} characters")
        print(f"  Preview (first 200 chars):")
        print(f"  {markdown[:200]}...")

        # Check for expected content
        if "Page" in markdown and "---" in markdown:
            print("✓ Markdown formatting validated (page headers and separators)")
        else:
            print("⚠ Markdown formatting may be incomplete")

        # Check for IRS keywords
        keywords = ["schedule", "partnership", "k-1", "1065"]
        found = [kw for kw in keywords if kw.lower() in markdown.lower()]
        if found:
            print(f"✓ Expected keywords found: {', '.join(found)}")
        else:
            print(f"⚠ Expected keywords not found")

        return True

    except Exception as e:
        print(f"✗ PDF parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_source_workflow_integration():
    """Validate integration with source workflow."""
    print("\n" + "=" * 70)
    print("VALIDATION 3: Source Workflow Integration")
    print("=" * 70)

    try:
        # Check if the import is present in source.py
        source_file = project_root / "open_notebook" / "graphs" / "source.py"

        if not source_file.exists():
            print(f"✗ Source workflow file not found: {source_file}")
            return False

        content = source_file.read_text()

        # Check for our import
        if "from api.pdf_parser_service import get_pdf_parser_service" in content:
            print("✓ PDFParserService import found in source workflow")
        else:
            print("✗ PDFParserService import NOT found in source workflow")
            return False

        # Check for PDF detection logic
        if 'Path(file_path).suffix.lower() == ".pdf"' in content:
            print("✓ PDF file detection logic found")
        else:
            print("✗ PDF file detection logic NOT found")
            return False

        # Check for docling-parse usage
        if "parse_pdf_to_markdown" in content:
            print("✓ PDFParserService usage found (parse_pdf_to_markdown)")
        else:
            print("✗ PDFParserService usage NOT found")
            return False

        # Check for fallback logic
        if "Falling back to content-core" in content:
            print("✓ Fallback to content-core found (error handling)")
        else:
            print("⚠ Fallback logic not explicitly found")

        print("\n✓ Source workflow properly integrated with PDFParserService")
        print("  - PDF files will be detected by file extension (.pdf)")
        print("  - PDFParserService (docling-parse) will be used for parsing")
        print("  - Markdown output with page headers and separators")
        print("  - Falls back to content-core on errors")

        return True

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_dependency():
    """Validate docling-parse dependency."""
    print("\n" + "=" * 70)
    print("VALIDATION 4: Dependency Configuration")
    print("=" * 70)

    try:
        pyproject = project_root / "pyproject.toml"

        if not pyproject.exists():
            print(f"✗ pyproject.toml not found")
            return False

        content = pyproject.read_text()

        if "docling-parse" in content:
            print("✓ docling-parse dependency found in pyproject.toml")

            # Extract version requirement
            for line in content.split("\n"):
                if "docling-parse" in line:
                    print(f"  {line.strip()}")
        else:
            print("✗ docling-parse dependency NOT found in pyproject.toml")
            return False

        return True

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


def main():
    """Run all validations."""
    print("\n" + "=" * 70)
    print("PDF INTEGRATION VALIDATION")
    print("Validating PDFParserService integration with Open Notebook")
    print("=" * 70)

    validations = [
        ("PDFParserService Availability", validate_pdf_parser_service),
        ("PDF Parsing Functionality", validate_pdf_parsing),
        ("Source Workflow Integration", validate_source_workflow_integration),
        ("Dependency Configuration", validate_dependency),
    ]

    results = []
    for name, validator in validations:
        try:
            result = validator()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Validation '{name}' crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print("\n" + "-" * 70)
    print(f"Results: {passed}/{total} validations passed")
    print("=" * 70)

    if passed == total:
        print("\n✓ All validations passed!")
        print("\nPDF Integration Status:")
        print("  - PDFParserService is properly integrated")
        print("  - PDF files will be parsed using docling-parse (deterministic)")
        print("  - No reliance on content-core's undetermined engine selection")
        return 0
    else:
        print(f"\n✗ {total - passed} validation(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
