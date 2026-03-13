"""
RAG Client Library

This module provides the main RAGClient class for interacting with
the Julien RAG API.
"""

import logging
from typing import Dict, Any, Optional

import httpx

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

logger = logging.getLogger(__name__)


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


class RAGClient:
    """
    Client for the Julien RAG API.

    Provides methods for:
    - Vector similarity search
    - RAG query (search + generation)
    - Database statistics
    - Health checks
    - Data refresh (admin)

    Example:
        >>> from julien_rag import RAGClient
        >>> client = RAGClient(base_url="http://localhost:8000")
        >>> results = client.search("machine learning projects")
        >>> print(f"Found {len(results)} documents")
        >>> rag_result = client.rag_query("What is this project about?")
        >>> print(rag_result.answer)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        admin_token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize RAG client.

        Args:
            base_url: API base URL (e.g., "http://localhost:8000")
            api_key: Optional API key for authenticated endpoints
            admin_token: Optional admin token for admin operations
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.admin_token = admin_token
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

        logger.info(f"Initialized RAGClient with base_url: {base_url}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, response: httpx.Response, model):
        """Handle API response and convert to model."""
        if response.status_code == 200:
            data = response.json()
            return model(**data)
        elif response.status_code == 401:
            raise AuthenticationError(f"Authentication failed: {response.text}")
        elif response.status_code == 403:
            raise RAGAPIError(f"Forbidden: {response.text}")
        elif response.status_code == 404:
            raise NotFoundError(f"Endpoint not found: {response.text}")
        elif 400 <= response.status_code < 500:
            raise ValidationError(f"Request validation error: {response.text}")
        elif response.status_code >= 500:
            raise ServerError(f"Server error {response.status_code}: {response.text}")
        else:
            raise RAGAPIError(
                f"Unexpected status {response.status_code}: {response.text}"
            )

    def search(
        self,
        query: str,
        k: int = 10,
        collection: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> SearchResponse:
        """
        Search for relevant documents using vector similarity.

        Args:
            query: Search query text
            k: Number of results to return (1-100)
            collection: Optional collection name to search
            filters: Optional metadata filters (e.g., {"source": "github_repos"})

        Returns:
            SearchResponse with documents, scores, and metadata

        Raises:
            RAGAPIError: If API request fails
            ValidationError: If request parameters are invalid
        """
        request = SearchRequest(
            query=query,
            k=k,
            collection=collection,
            filters=filters,
        )

        url = f"{self.base_url}/query"
        headers = self._get_headers()

        try:
            response = self._client.post(
                url,
                json=request.dict(),
                headers=headers,
            )
            return self._handle_response(response, SearchResponse)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def rag_query(
        self,
        query: str,
        k: int = 10,
        collection: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        return_context: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> RAGResponse:
        """
        Generate answer using RAG (Retrieval-Augmented Generation).

        Args:
            query: Question or query
            k: Number of context chunks to retrieve
            collection: Optional collection to search
            filters: Optional metadata filters
            return_context: Include retrieved context in response
            temperature: Override LLM temperature (0.0-2.0)
            max_tokens: Override maximum tokens to generate

        Returns:
            RAGResponse with generated answer, confidence, and sources

        Raises:
            RAGAPIError: If API request fails
            ValidationError: If request parameters are invalid
        """
        request = RAGRequest(
            query=query,
            k=k,
            collection=collection,
            filters=filters,
            return_context=return_context,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        url = f"{self.base_url}/rag-query"
        headers = self._get_headers()

        try:
            response = self._client.post(
                url,
                json=request.dict(),
                headers=headers,
            )
            return self._handle_response(response, RAGResponse)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def get_sources(self) -> SourcesResponse:
        """
        List available source types in the database.

        Returns:
            SourcesResponse with list of source types

        Raises:
            RAGAPIError: If API request fails
        """
        url = f"{self.base_url}/sources"
        headers = self._get_headers()

        try:
            response = self._client.get(url, headers=headers)
            return self._handle_response(response, SourcesResponse)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def get_stats(self) -> StatsResponse:
        """
        Get database statistics.

        Returns:
            StatsResponse with document counts and database info

        Raises:
            RAGAPIError: If API request fails
        """
        url = f"{self.base_url}/stats"
        headers = self._get_headers()

        try:
            response = self._client.get(url, headers=headers)
            return self._handle_response(response, StatsResponse)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def health_check(self) -> HealthResponse:
        """
        Check API health status.

        Returns:
            HealthResponse with service status

        Raises:
            RAGAPIError: If API request fails
        """
        url = f"{self.base_url}/health"
        headers = self._get_headers()

        try:
            response = self._client.get(url, headers=headers)
            return self._handle_response(response, HealthResponse)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def refresh(
        self,
        admin_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Trigger data refresh (reindexing) - admin only.

        Args:
            admin_token: Admin token (uses client admin_token if not provided)

        Returns:
            Dictionary with refresh status and statistics

        Raises:
            AuthenticationError: If admin token is invalid
            RAGAPIError: If API request fails
        """
        token = admin_token or self.admin_token
        if not token:
            raise AuthenticationError("Admin token required for refresh operation")

        url = f"{self.base_url}/refresh"
        headers = self._get_headers()
        headers["X-Admin-Token"] = token

        try:
            response = self._client.post(url, headers=headers)
            return self._handle_response(response, dict)
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e

    def list_collections(self) -> Dict[str, Any]:
        """
        List all available collections in the database.

        Returns:
            Dictionary with collection names and their document counts

        Raises:
            RAGAPIError: If API request fails
        """
        url = f"{self.base_url}/collections"
        headers = self._get_headers()

        try:
            response = self._client.get(url, headers=headers)
            data = response.json()
            if response.status_code != 200:
                raise RAGAPIError(f"Failed to list collections: {data}")
            return data
        except httpx.RequestError as e:
            raise RAGAPIError(f"Request failed: {e}") from e
