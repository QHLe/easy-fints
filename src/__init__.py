"""Integration package for embedding pyfin into another Python app.

This package intentionally avoids importing submodules at top-level to prevent
circular import issues when submodules import each other. Import submodules
directly, e.g. `from src.client import PyFinIntegrationClient`.
"""

__all__ = []
