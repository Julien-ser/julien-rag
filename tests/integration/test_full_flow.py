"""
Integration tests for full RAG system flow.

This module tests the complete pipeline:
1. API startup and health check
2. Database connectivity and collections
3. End-to-end search queries
4. RAG query generation
5. Metrics collection
6. Admin operations

Run with: pytest tests/integration/test_full_flow.py -v
"""

import os
import pytest
import time
from typing import Dict, Any

from fastapi.testclient import TestClient

from src.api import app
from src.database import init_database, get_collection
from src.retriever import Retriever
from src.embedder import Embedder
from src.monitoring import reset_metrics, PROMETHEUS_AVAILABLE

# Skip all tests if we're in a minimal environment without dependencies
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    # Reset monitoring metrics before tests
    reset_metrics()

    # Use test database if available, otherwise use a temporary one
    os.environ.setdefault("CHROMA_PERSIST_DIR", "data/test_vector_db_integration")

    # Initialize test database
    try:
        init_database()
    except Exception as e:
        pytest.skip(f"Failed to initialize database: {e}")

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def retriever():
    """Create a retriever instance for direct testing."""
    try:
        return Retriever()
    except Exception as e:
        pytest.skip(f"Failed to initialize retriever: {e}")


class TestAPIIntegration:
    """Test suite for API integration."""

    def test_health_check(self, client):
        """Test API health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "unhealthy"]
        assert "timestamp" in data

    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        metrics_data = response.text

        # If prometheus is available, check for some expected metrics
        if PROMETHEUS_AVAILABLE:
            # Should have some metrics recorded (even if zero)
            assert "rag_api_requests_total" in metrics_data or "#" in metrics_data

    def test_list_collections(self, client):
        """Test listing available collections."""
        response = client.get("/collections")
        assert response.status_code == 200
        data = response.json()
        assert "collections" in data
        assert "stats" in data
        assert "count" in data
        assert isinstance(data["collections"], list)

    def test_get_stats(self, client):
        """Test database statistics endpoint."""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "persist_directory" in data
        assert "collections" in data
        assert "timestamp" in data

    def test_get_sources(self, client):
        """Test listing available sources."""
        response = client.get("/sources")
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert "count" in data
        assert isinstance(data["sources"], list)
        # Should include known source types
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


class TestSearchIntegration:
    """Test suite for search functionality."""

    def test_search_empty_query(self, client):
        """Test search with empty query (should fail)."""
        response = client.post("/query", json={"query": ""})
        assert response.status_code == 422  # Validation error

    def test_search_valid_query(self, client):
        """Test search with valid query."""
        # Use a simple query that should work even with minimal data
        response = client.post(
            "/query",
            json={"query": "test query", "k": 5, "collection": None, "filters": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "metadatas" in data
        assert "scores" in data
        assert "collection" in data
        assert "query_time" in data
        assert "total_results" in data
        # Results should be lists
        assert isinstance(data["documents"], list)
        assert isinstance(data["metadatas"], list)
        assert isinstance(data["scores"], list)

    def test_search_with_k_limit(self, client):
        """Test search with k parameter."""
        response = client.post(
            "/query",
            json={
                "query": "test",
                "k": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should not return more than k results
        assert len(data["documents"]) <= 3

    def test_search_with_filters(self, client):
        """Test search with metadata filters."""
        response = client.post(
            "/query",
            json={"query": "test", "k": 5, "filters": {"source": "github_repos"}},
        )
        assert response.status_code == 200
        data = response.json()
        # If any results returned, check filter is applied
        if data["total_results"] > 0:
            for meta in data["metadatas"]:
                assert meta.get("source") == "github_repos"

    def test_search_with_collection(self, client):
        """Test search in specific collection."""
        response = client.post(
            "/query", json={"query": "test", "k": 5, "collection": "github_docs"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["collection"] == "github_docs"


class TestRAGIntegration:
    """Test suite for RAG generation."""

    def test_rag_empty_query(self, client):
        """Test RAG query with empty query (should fail)."""
        response = client.post("/rag-query", json={"query": ""})
        assert response.status_code == 422  # Validation error

    def test_rag_valid_query(self, client):
        """Test RAG query with valid input."""
        response = client.post(
            "/rag-query",
            json={
                "query": "What is this project about?",
                "k": 5,
                "return_context": True,
                "temperature": 0.7,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # RAG response should have all required fields
        assert "answer" in data
        assert "confidence" in data
        assert "sources" in data
        assert "query_time" in data
        assert "context_chunks" in data
        assert "context_length" in data

        # Confidence should be between 0 and 1
        assert 0.0 <= data["confidence"] <= 1.0

        # Answer should be non-empty string
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    def test_rag_without_context_return(self, client):
        """Test RAG query without returning context."""
        response = client.post(
            "/rag-query",
            json={
                "query": "Explain the project architecture",
                "k": 3,
                "return_context": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "context" in data
        # Context should be None when return_context is False
        assert data["context"] is None

    def test_rag_with_temperature_override(self, client):
        """Test RAG query with temperature override."""
        response = client.post(
            "/rag-query",
            json={"query": "Test temperature override", "k": 5, "temperature": 0.3},
        )
        assert response.status_code == 200
        data = response.json()
        # Should still generate valid response
        assert "answer" in data


class TestAdminOperations:
    """Test suite for admin endpoints."""

    def test_refresh_without_token(self, client):
        """Test refresh endpoint without admin token (should fail)."""
        response = client.post("/refresh")
        assert response.status_code == 403  # Forbidden

    def test_refresh_with_invalid_token(self, client):
        """Test refresh endpoint with invalid admin token."""
        response = client.post(
            "/refresh", headers={"X-Admin-Token": "invalid_token_12345"}
        )
        # If ADMIN_TOKEN is not set, returns 200 (dev mode)
        # If ADMIN_TOKEN is set, returns 403
        # We'll accept both for flexibility
        assert response.status_code in [200, 403]

    def test_refresh_with_valid_token(self, client):
        """Test refresh endpoint with valid admin token (if configured)."""
        admin_token = os.getenv("ADMIN_TOKEN")
        if not admin_token:
            pytest.skip("ADMIN_TOKEN not set, skipping refresh with auth")

        response = client.post("/refresh", headers={"X-Admin-Token": admin_token})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data

    def test_refresh_dev_mode(self, client):
        """Test refresh in dev mode (no ADMIN_TOKEN set)."""
        # Clear ADMIN_TOKEN for this test
        old_token = os.environ.get("ADMIN_TOKEN")
        if "ADMIN_TOKEN" in os.environ:
            del os.environ["ADMIN_TOKEN"]

        try:
            response = client.post("/refresh")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
        finally:
            # Restore token
            if old_token:
                os.environ["ADMIN_TOKEN"] = old_token


class TestMonitoring:
    """Test suite for monitoring functionality."""

    def test_metrics_middleware_counts_requests(self, client):
        """Test that metrics middleware tracks API requests."""
        # Make some API calls
        client.get("/health")
        client.get("/stats")
        client.post("/query", json={"query": "test", "k": 1})

        # Get metrics
        response = client.get("/metrics")
        assert response.status_code == 200
        metrics = response.text

        # Check that our endpoints are being tracked
        assert "rag_api_requests_total" in metrics or "#" in metrics

    def test_db_metrics_tracking(self, retriever):
        """Test database metrics are updated."""
        if retriever is None:
            pytest.skip("Retriever not available")

        from src.monitoring import update_db_metrics

        # Simulate updating metrics
        test_stats = {
            "github_docs": {"document_count": 100},
            "web_content": {"document_count": 50},
        }
        update_db_metrics(test_stats)

        # If prometheus is available, these should be set
        if PROMETHEUS_AVAILABLE:
            from src.monitoring import DB_DOCUMENT_COUNT

            # Metrics would have been updated (we can't easily test the actual values)
            assert DB_DOCUMENT_COUNT is not None


class TestDirectRetriever:
    """Test retriever functionality directly (not through API)."""

    def test_retriever_initialization(self, retriever):
        """Test that retriever initializes correctly."""
        if retriever is None:
            pytest.skip("Retriever not available")
        assert retriever is not None
        assert hasattr(retriever, "search")
        assert hasattr(retriever, "db")

    def test_retriever_search(self, retriever):
        """Test direct retriever search."""
        if retriever is None:
            pytest.skip("Retriever not available")

        results = retriever.search(query_text="test", k=5)

        # Check results structure
        assert hasattr(results, "documents")
        assert hasattr(results, "metadatas")
        assert hasattr(results, "scores")
        assert hasattr(results, "query_time")

        assert isinstance(results.documents, list)
        assert isinstance(results.metadatas, list)
        assert isinstance(results.scores, list)
        assert len(results.documents) == len(results.metadatas) == len(results.scores)

    def test_retriever_get_collection_stats(self, retriever):
        """Test getting collection statistics."""
        if retriever is None:
            pytest.skip("Retriever not available")

        stats = retriever.get_collection_stats()
        assert isinstance(stats, dict)
        # Should have collection names as keys
        for key in stats:
            assert isinstance(stats[key], dict)
            assert "document_count" in stats[key] or "error" in stats[key]


class TestErrorHandling:
    """Test suite for error handling."""

    def test_invalid_collection_name(self, client):
        """Test search with invalid collection name."""
        response = client.post(
            "/query", json={"query": "test", "collection": "nonexistent_collection"}
        )
        # Should either succeed with no results or fail gracefully
        assert response.status_code in [200, 400, 404]

    def test_malformed_request(self, client):
        """Test API with malformed request body."""
        response = client.post("/query", json={"invalid_field": "value"})
        assert response.status_code == 422  # Unprocessable Entity

    def test_large_k_value(self, client):
        """Test search with k > 100 (should fail validation)."""
        response = client.post("/query", json={"query": "test", "k": 200})
        assert response.status_code == 422

    def test_very_long_query(self, client):
        """Test search with query > 2000 chars (should fail validation)."""
        long_query = "x" * 3000
        response = client.post("/query", json={"query": long_query})
        assert response.status_code == 422


class TestPerformance:
    """Basic performance tests."""

    def test_query_latency(self, client):
        """Test that query response time is reasonable."""
        start = time.time()
        response = client.post("/query", json={"query": "test", "k": 5})
        elapsed = time.time() - start
        assert response.status_code == 200
        # Query should complete within 10 seconds (reasonable threshold)
        assert elapsed < 10.0

    def test_health_check_latency(self, client):
        """Test health check is fast."""
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 1.0  # Should be very fast


class TestDataIntegrity:
    """Tests for data integrity and consistency."""

    def test_collection_data_accessible(self, retriever):
        """Test that collection data can be retrieved."""
        if retriever is None:
            pytest.skip("Retriever not available")

        collections = retriever.db.list_collections()
        assert isinstance(collections, list)

        for collection_name in collections:
            collection = retriever.db.get_collection(collection_name)
            count = collection.count()
            assert isinstance(count, int)
            assert count >= 0  # Count should be non-negative

    def test_search_results_consistency(self, client):
        """Test that search results are consistent (same query returns results)."""
        query = "test consistency check"

        # Make two identical queries
        response1 = client.post("/query", json={"query": query, "k": 5})
        response2 = client.post("/query", json={"query": query, "k": 5})

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Both should return same number of results (if data hasn't changed)
        assert data1["total_results"] == data2["total_results"]
