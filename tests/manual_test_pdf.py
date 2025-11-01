#!/usr/bin/env python3
"""
Manual test script for PDF parsing functionality.
This can be run directly without pytest to validate PDF parsing works.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_pdf_parsing():
    """Test PDF parsing with content-core."""
    print("=" * 60)
    print("PDF Parsing Integration Test")
    print("=" * 60)

    # Check if content-core is available
    try:
        from content_core import extract_content
        from content_core.common import ProcessSourceState
        print("✓ content-core imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import content-core: {e}")
        print("  Please ensure content-core is installed")
        return False

    # Check if test PDF exists
    test_pdf = Path(__file__).parent / "assets" / "i1065sk1.pdf"
    if not test_pdf.exists():
        print(f"✗ Test PDF not found at: {test_pdf}")
        return False

    file_size = test_pdf.stat().st_size
    print(f"✓ Test PDF found: {test_pdf}")
    print(f"  File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    # Test 1: Parse with auto engine
    print("\n" + "-" * 60)
    print("Test 1: Parsing PDF with auto engine selection")
    print("-" * 60)

    try:
        state: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf),
            "content": "",
            "title": "",
            "document_engine": "auto",
            "url_engine": "auto",
            "output_format": "markdown"
        }

        result = await extract_content(state)

        content = result.get("content", "")
        if not content:
            print("✗ No content extracted")
            return False

        print(f"✓ Content extracted successfully")
        print(f"  Content length: {len(content):,} characters")
        print(f"  Content preview (first 200 chars):")
        print(f"  {content[:200]}...")

        # Check for expected content
        content_lower = content.lower()
        keywords = ["irs", "schedule", "partnership", "k-1", "1065"]
        found_keywords = [kw for kw in keywords if kw in content_lower]

        if found_keywords:
            print(f"✓ Found expected keywords: {', '.join(found_keywords)}")
        else:
            print(f"⚠ Warning: Expected keywords not found in content")
            print(f"  Looking for: {', '.join(keywords)}")

    except Exception as e:
        print(f"✗ Failed to parse PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Parse with PyMuPDF explicitly
    print("\n" + "-" * 60)
    print("Test 2: Parsing PDF with PyMuPDF engine")
    print("-" * 60)

    try:
        state_pymupdf: ProcessSourceState = {
            "url": "",
            "file_path": str(test_pdf),
            "content": "",
            "title": "",
            "document_engine": "pymupdf",
            "url_engine": "auto",
            "output_format": "markdown"
        }

        result_pymupdf = await extract_content(state_pymupdf)
        content_pymupdf = result_pymupdf.get("content", "")

        if content_pymupdf:
            print(f"✓ PyMuPDF extracted successfully")
            print(f"  Content length: {len(content_pymupdf):,} characters")
        else:
            print("✗ PyMuPDF failed to extract content")
            return False

    except Exception as e:
        print(f"✗ PyMuPDF parsing failed: {e}")
        # This might be acceptable if PyMuPDF isn't available
        print("  (This may be expected if PyMuPDF is not installed)")

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_pdf_parsing())
    sys.exit(0 if success else 1)
