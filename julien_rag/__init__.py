"""
Julien RAG SDK - Client library for the Julien RAG API.

This package provides a simple Python client for interacting with
the Julien RAG API, enabling vector search and RAG operations.
"""

from .client import RAGClient
from .models import (
    SearchRequest,
    SearchResponse,
    RAGRequest,
    RAGResponse,
    StatsResponse,
    SourcesResponse,
    HealthResponse,
)
from .exceptions import (
    RAGAPIError,
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)

__version__ = "1.0.0"

__all__ = [
    "RAGClient",
    "SearchRequest",
    "SearchResponse",
    "RAGRequest",
    "RAGResponse",
    "StatsResponse",
    "SourcesResponse",
    "HealthResponse",
    "RAGAPIError",
    "AuthenticationError",
    "NotFoundError",
    "ServerError",
    "ValidationError",
]
