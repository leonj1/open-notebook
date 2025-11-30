#!/usr/bin/env python3
"""
Startup script for Open Notebook API server.
"""

import os
import sys
from pathlib import Path

import uvicorn

# Add the current directory to Python path so imports work
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

if __name__ == "__main__":
    # Default configuration
    # Use 0.0.0.0 to listen on all interfaces (accessible from LAN)
    # Override with API_HOST=127.0.0.1 to restrict to localhost only
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5055"))
    reload = os.getenv("API_RELOAD", "true").lower() == "true"
    workers = int(os.getenv("API_WORKERS", "1"))

    print(f"Starting Open Notebook API server on {host}:{port}")
    print(f"Reload mode: {reload}")
    print(f"Workers: {workers}")

    if reload and workers > 1:
        print("Warning: Reload mode is not recommended with more than 1 worker.")

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        reload_dirs=[str(current_dir)] if reload else None,
    )
