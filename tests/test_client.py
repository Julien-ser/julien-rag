"""
Tests for the Julien RAG client library.

This module contains unit tests for RAGClient, covering:
- Client initialization and configuration
- Search, RAG query, and metadata endpoint methods
- Error handling and exceptions
- Authentication and admin operations
- Network error handling
"""

import pytest
from unittest.mock import Mock, patch
import httpx

from julien_rag import RAGClient
from julien_rag.models import (
    SearchResponse,
    RAGResponse,
    StatsResponse,
    SourcesResponse,
    HealthResponse,
)
from julien_rag.exceptions import (
    RAGAPIError,
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)


@pytest.fixture
def client():
    """Create a RAGClient instance for testing."""
    return RAGClient(base_url="http://test.example.com")


def test_client_initialization():
    """Test client can be initialized with custom parameters."""
    client = RAGClient(
        base_url="http://localhost:8000",
        api_key="testkey",
        admin_token="admintoken",
        timeout=60.0,
    )
    assert client.base_url == "http://localhost:8000"
    assert client.api_key == "testkey"
    assert client.admin_token == "admintoken"
    assert client.timeout == 60.0
    client.close()


def test_context_manager():
    """Test client works as a context manager."""
    with RAGClient(base_url="http://test.example.com") as client:
        assert client.base_url == "http://test.example.com"
    # After exit, client should be closed (no further action needed)


def test_get_headers_no_auth(client):
    """Test headers without API key."""
    headers = client._get_headers()
    assert headers == {"Accept": "application/json"}


def test_get_headers_with_api_key(client):
    """Test headers with API key."""
    client.api_key = "mykey"
    headers = client._get_headers()
    assert headers == {"Accept": "application/json", "Authorization": "Bearer mykey"}


def test_handle_response_success(client):
    """Test successful response handling."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_results": 1, "documents": ["doc1"]}
    result = client._handle_response(mock_response, SearchResponse)
    assert isinstance(result, SearchResponse)
    assert result.total_results == 1


def test_handle_response_errors(client):
    """Test error responses raise appropriate exceptions."""
    # 401 Unauthorized
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    with pytest.raises(AuthenticationError):
        client._handle_response(mock_response, SearchResponse)

    # 403 Forbidden
    mock_response.status_code = 403
    with pytest.raises(RAGAPIError):
        client._handle_response(mock_response, SearchResponse)

    # 404 Not Found
    mock_response.status_code = 404
    with pytest.raises(NotFoundError):
        client._handle_response(mock_response, SearchResponse)

    # 400 Bad Request
    mock_response.status_code = 400
    with pytest.raises(ValidationError):
        client._handle_response(mock_response, SearchResponse)

    # 500 Server Error
    mock_response.status_code = 500
    with pytest.raises(ServerError):
        client._handle_response(mock_response, SearchResponse)


def test_search_success(client):
    """Test successful search call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        # Recreate client to use patched http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documents": ["doc1 text"],
            "metadatas": [{"source": "github"}],
            "scores": [0.95],
            "collection": "github_docs",
            "query_time": 0.123,
            "total_results": 1,
        }
        mock_http.post.return_value = mock_response

        result = client.search("test query", k=5)

        assert result.total_results == 1
        assert result.documents[0] == "doc1 text"
        assert result.scores[0] == 0.95
        assert result.collection == "github_docs"

        # Verify request was made correctly
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "http://test.example.com/query"
        request_data = call_args[1]["json"]
        assert request_data["query"] == "test query"
        assert request_data["k"] == 5

        client.close()


def test_rag_query_success(client):
    """Test successful RAG query call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "This is a test answer",
            "confidence": 0.9,
            "sources": [{"source": "github"}],
            "query_time": 0.5,
            "context_chunks": 3,
            "context_length": 150,
            "context": None,
        }
        mock_http.post.return_value = mock_response

        result = client.rag_query("test question", k=5, return_context=True)

        assert result.answer == "This is a test answer"
        assert result.confidence == 0.9
        assert result.context_chunks == 3

        # Verify it was posted to /rag-query
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert "rag-query" in call_args[0][0]

        client.close()


def test_get_sources_success(client):
    """Test get_sources call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sources": ["github_repos", "web_content"],
            "description": "Test sources",
            "count": 2,
        }
        mock_http.get.return_value = mock_response

        result = client.get_sources()

        assert result.count == 2
        assert "github_repos" in result.sources
        mock_http.get.assert_called_once_with(
            "http://test.example.com/sources", headers={}
        )
        client.close()


def test_get_stats_success(client):
    """Test get_stats call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "initialized",
            "persist_directory": "./data/vector_db",
            "collections": {"github_docs": {"document_count": 100}},
            "timestamp": "2024-01-01T00:00:00",
        }
        mock_http.get.return_value = mock_response

        result = client.get_stats()

        assert result.status == "initialized"
        assert result.collections["github_docs"]["document_count"] == 100
        client.close()


def test_health_check_success(client):
    """Test health_check call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00",
        }
        mock_http.get.return_value = mock_response

        result = client.health_check()

        assert result.status == "healthy"
        client.close()


def test_refresh_without_admin_token(client):
    """Test refresh raises error if no admin token."""
    client.admin_token = None
    with pytest.raises(AuthenticationError):
        client.refresh()


def test_refresh_with_admin_token(client):
    """Test refresh includes admin token header."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com", admin_token="secret")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "message": "Refreshed"}
        mock_http.post.return_value = mock_response

        result = client.refresh()

        assert result["status"] == "success"

        # Verify X-Admin-Token header was set
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[1]["headers"]["X-Admin-Token"] == "secret"
        client.close()


def test_list_collections_success(client):
    """Test list_collections call."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collections": ["col1", "col2"],
            "stats": {
                "col1": {"document_count": 10},
                "col2": {"document_count": 20},
            },
            "count": 2,
        }
        mock_http.get.return_value = mock_response

        result = client.list_collections()

        assert result["count"] == 2
        assert "col1" in result["collections"]
        client.close()


def test_network_error(client):
    """Test network error raises RAGAPIError."""
    with patch("httpx.Client") as MockClient:
        mock_http = Mock()
        MockClient.return_value = mock_http
        client = RAGClient(base_url="http://test.example.com")
        mock_http.post.side_effect = httpx.RequestError("Network error")

        with pytest.raises(RAGAPIError):
            client.search("test")

        client.close()
