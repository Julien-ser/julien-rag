"""
Tests for API module.

Tests cover:
- Health check endpoint
- Sources listing
- Statistics retrieval
- Query search functionality
- Refresh endpoint (with admin auth)
- Error handling and edge cases
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api import (
    app,
    QueryRequest,
    QueryResponse,
    SourcesResponse,
    StatsResponse,
    RefreshResponse,
    HealthResponse,
)


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_retriever():
    """Create mock retriever with predictable behavior."""
    mock = Mock()
    mock.db = Mock()
    mock.db.persist_directory = Path("data/vector_db")

    # Mock search result
    mock_search_result = Mock()
    mock_search_result.documents = ["Test document 1", "Test document 2"]
    mock_search_result.metadatas = [
        {"source": "github", "type": "repo", "url": "https://github.com/test/repo"},
        {"source": "web", "type": "blog", "url": "https://example.com/blog"},
    ]
    mock_search_result.scores = [0.95, 0.87]
    mock_search_result.collection = "github_docs"
    mock_search_result.query_time = 0.234
    mock_search_result.__len__ = lambda self: len(self.documents)
    mock_search_result.to_dict.return_value = {
        "documents": mock_search_result.documents,
        "metadatas": mock_search_result.metadatas,
        "scores": mock_search_result.scores,
        "collection": mock_search_result.collection,
        "query_time": mock_search_result.query_time,
        "total_results": len(mock_search_result.documents),
    }

    mock.search.return_value = mock_search_result

    # Mock collection stats
    mock.get_collection_stats.return_value = {
        "github_docs": {"document_count": 1500},
        "web_content": {"document_count": 300},
    }

    # Mock list_collections
    mock.db.list_collections.return_value = ["github_docs", "web_content"]
    mock.db.get_collection.return_value = Mock(count=lambda: 1500)

    return mock


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_healthy(self, client, mock_retriever):
        """Test health check when service is healthy."""
        with patch("api.retriever", mock_retriever):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data

    def test_health_unhealthy(self, client):
        """Test health check when service not initialized."""
        with patch("api.retriever", None):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "reason" in data
            assert data["reason"] == "retriever not initialized"


class TestSourcesEndpoint:
    """Tests for /sources endpoint."""

    def test_sources_list(self, client):
        """Test sources listing returns known sources."""
        response = client.get("/sources")
        assert response.status_code == 200
        data = response.json()

        assert "sources" in data
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) > 0

        expected_sources = [
            "github_repos",
            "github_commits",
            "github_issues",
            "github_gists",
            "github_starred",
            "web_content",
        ]
        for source in expected_sources:
            assert source in data["sources"]

        assert "description" in data
        assert "count" in data
        assert data["count"] == len(data["sources"])


class TestStatsEndpoint:
    """Tests for /stats endpoint."""

    def test_stats_success(self, client, mock_retriever):
        """Test stats retrieval when retriever is available."""
        with patch("api.retriever", mock_retriever):
            response = client.get("/stats")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "initialized"
            assert "persist_directory" in data
            assert "collections" in data
            assert "timestamp" in data

            collections = data["collections"]
            assert "github_docs" in collections
            assert "web_content" in collections

    def test_stats_unavailable(self, client):
        """Test stats when service not initialized."""
        with patch("api.retriever", None):
            response = client.get("/stats")
            assert response.status_code == 503


class TestQueryEndpoint:
    """Tests for /query endpoint."""

    def test_query_success(self, client, mock_retriever):
        """Test successful query with valid request."""
        with patch("api.retriever", mock_retriever):
            request_data = {
                "query": "machine learning",
                "k": 5,
                "collection": "github_docs",
            }
            response = client.post("/query", json=request_data)
            assert response.status_code == 200
            data = response.json()

            assert "documents" in data
            assert "metadatas" in data
            assert "scores" in data
            assert "collection" in data
            assert "query_time" in data
            assert "total_results" in data

            # Verify retriever was called correctly
            mock_retriever.search.assert_called_once_with(
                query_text="machine learning",
                k=5,
                collection_name="github_docs",
                filters=None,
            )

    def test_query_with_filters(self, client, mock_retriever):
        """Test query with metadata filters."""
        with patch("api.retriever", mock_retriever):
            request_data = {
                "query": "python project",
                "k": 10,
                "filters": {"source": "github_repos", "type": "repo"},
            }
            response = client.post("/query", json=request_data)
            assert response.status_code == 200

            # Check filters were passed
            call_kwargs = mock_retriever.search.call_args[1]
            assert call_kwargs["filters"] == {"source": "github_repos", "type": "repo"}

    def test_query_empty_query(self, client, mock_retriever):
        """Test query with empty string returns 422 (Pydantic validation)."""
        with patch("api.retriever", mock_retriever):
            request_data = {"query": "", "k": 5}
            response = client.post("/query", json=request_data)
            assert response.status_code == 422

    def test_query_invalid_k(self, client, mock_retriever):
        """Test query with invalid k returns 422 (Pydantic validation)."""
        with patch("api.retriever", mock_retriever):
            request_data = {"query": "test", "k": 0}
            response = client.post("/query", json=request_data)
            assert response.status_code == 422

    def test_query_service_unavailable(self, client):
        """Test query when retriever not initialized."""
        with patch("api.retriever", None):
            request_data = {"query": "test", "k": 5}
            response = client.post("/query", json=request_data)
            assert response.status_code == 503

    def test_query_search_error(self, client, mock_retriever):
        """Test query when search raises exception."""
        with patch("api.retriever", mock_retriever):
            mock_retriever.search.side_effect = RuntimeError("Database error")

            request_data = {"query": "test", "k": 5}
            response = client.post("/query", json=request_data)
            assert response.status_code == 500
            assert "Search operation failed" in response.json()["detail"]


class TestRefreshEndpoint:
    """Tests for /refresh endpoint."""

    def test_refresh_success_no_auth(self, client):
        """Test refresh succeeds when ADMIN_TOKEN not set (dev mode)."""
        with patch.dict(os.environ, {}, clear=True):  # No ADMIN_TOKEN
            with patch("api.run_pipeline") as mock_pipeline:
                mock_stats = Mock()
                mock_stats.duration.return_value.total_seconds.return_value = 330
                mock_stats.github_files_collected = 3
                mock_stats.web_files_collected = 1
                mock_stats.files_processed = 4
                mock_stats.chunks_generated = 1500
                mock_stats.collection_errors = 0
                mock_stats.processing_errors = 0
                mock_pipeline.return_value = mock_stats

                response = client.post("/refresh")
                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "success"
                assert "stats" in data
                mock_pipeline.assert_called_once()

    def test_refresh_with_valid_token(self, client):
        """Test refresh with valid admin token."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "secret123"}):
            with patch("api.run_pipeline") as mock_pipeline:
                mock_stats = Mock()
                mock_stats.duration.return_value.total_seconds.return_value = 330
                mock_stats.github_files_collected = 2
                mock_stats.web_files_collected = 1
                mock_stats.files_processed = 3
                mock_stats.chunks_generated = 1000
                mock_stats.collection_errors = 0
                mock_stats.processing_errors = 0
                mock_pipeline.return_value = mock_stats

                response = client.post(
                    "/refresh", headers={"X-Admin-Token": "secret123"}
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                mock_pipeline.assert_called_once()

    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token returns 403."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "secret123"}):
            response = client.post("/refresh", headers={"X-Admin-Token": "wrong"})
            assert response.status_code == 403
            assert "Invalid admin token" in response.json()["detail"]

    def test_refresh_missing_token(self, client):
        """Test refresh without token returns 403."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "secret123"}):
            response = client.post("/refresh")
            assert response.status_code == 403
            assert "Admin token required" in response.json()["detail"]

    def test_refresh_pipeline_error(self, client):
        """Test refresh when pipeline fails."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("api.run_pipeline") as mock_pipeline:
                mock_pipeline.side_effect = Exception("Pipeline failed")

                response = client.post("/refresh")
                assert response.status_code == 500
                assert "Refresh operation failed" in response.json()["detail"]


class TestCollectionsEndpoint:
    """Tests for /collections endpoint."""

    def test_list_collections_success(self, client, mock_retriever):
        """Test listing collections."""
        with patch("api.retriever", mock_retriever):
            response = client.get("/collections")
            assert response.status_code == 200
            data = response.json()

            assert "collections" in data
            assert "stats" in data
            assert "count" in data
            assert data["count"] == 2

    def test_list_collections_unavailable(self, client):
        """Test listing collections when service unavailable."""
        with patch("api.retriever", None):
            response = client.get("/collections")
            assert response.status_code == 503


class TestAPIDocumentation:
    """Tests for API documentation availability."""

    def test_docs_endpoint(self, client):
        """Test /docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_redoc_endpoint(self, client):
        """Test /redoc endpoint is accessible."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()


class TestRequestValidation:
    """Tests for request validation errors."""

    def test_query_missing_required_field(self, client, mock_retriever):
        """Test query with missing required query field."""
        with patch("api.retriever", mock_retriever):
            request_data = {"k": 5}  # Missing 'query'
            response = client.post("/query", json=request_data)
            assert response.status_code == 422

    def test_query_invalid_collection_name(self, client, mock_retriever):
        """Test query with invalid collection name still works (validation at retriever level)."""
        with patch("api.retriever", mock_retriever):
            # The retriever should handle invalid collection by searching appropriate collections
            request_data = {"query": "test", "collection": "nonexistent"}
            response = client.post("/query", json=request_data)
            # Should return 200 as validation happens in retriever, not at API level
            assert response.status_code == 200
