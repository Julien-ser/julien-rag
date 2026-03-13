"""
Custom exceptions for Julien RAG SDK.
"""


class RAGAPIError(Exception):
    """Base exception for RAG API errors."""

    pass


class AuthenticationError(RAGAPIError):
    """Authentication failure."""

    pass


class NotFoundError(RAGAPIError):
    """Resource not found."""

    pass


class ServerError(RAGAPIError):
    """Server error (5xx)."""

    pass


class ValidationError(RAGAPIError):
    """Request validation error."""

    pass
