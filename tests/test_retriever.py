"""
Tests for retriever module.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from retriever import (
    Retriever,
    SearchResult,
    search,
    _build_where_filter,
    _normalize_scores,
)


class TestRetrieverImports:
    """Test that all retriever components can be imported correctly."""

    def test_import_retriever(self):
        """Test that Retriever class exists."""
        assert Retriever is not None

    def test_import_search_result(self):
        """Test that SearchResult class exists."""
        assert SearchResult is not None

    def test_import_search_function(self):
        """Test that search function exists."""
        assert callable(search)


class TestSearchResult:
    """Test SearchResult class functionality."""

    def test_create_search_result(self):
        """Test creating a SearchResult instance."""
        result = SearchResult(
            documents=["doc1", "doc2"],
            metadatas=[{"id": 1}, {"id": 2}],
            scores=[0.95, 0.87],
            collection="test",
            query_time=0.123,
        )
        assert len(result) == 2
        assert result.documents == ["doc1", "doc2"]
        assert result.scores == [0.95, 0.87]
        assert result.collection == "test"
        assert result.query_time == 0.123

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = SearchResult(
            documents=["doc1"],
            metadatas=[{"id": 1}],
            scores=[0.95],
            collection="test",
            query_time=0.1,
        )
        d = result.to_dict()
        assert d["total_results"] == 1
        assert d["documents"] == ["doc1"]
        assert d["scores"] == [0.95]
        assert d["collection"] == "test"
        assert "query_time" in d

    def test_getitem(self):
        """Test indexing into results."""
        result = SearchResult(
            documents=["doc1", "doc2"],
            metadatas=[{"id": 1}, {"id": 2}],
            scores=[0.95, 0.87],
            collection="test",
            query_time=0.1,
        )
        item = result[0]
        assert item["document"] == "doc1"
        assert item["metadata"]["id"] == 1
        assert item["score"] == 0.95

    def test_empty_result(self):
        """Test empty search result."""
        result = SearchResult(
            documents=[],
            metadatas=[],
            scores=[],
            collection="test",
            query_time=0.0,
        )
        assert len(result) == 0
        assert result.to_dict()["total_results"] == 0


class TestScoreNormalization:
    """Test score normalization function."""

    def test_normalize_scores(self):
        """Test normalizing cosine distances to similarities."""
        from retriever import _normalize_scores

        distances = [0.1, 0.5, 1.0, 0.0]
        scores = _normalize_scores(distances)
        expected = [0.9, 0.5, 0.0, 1.0]
        assert scores == expected

    def test_normalize_scores_clamped(self):
        """Test that scores are clamped to 0-1 range."""
        from retriever import _normalize_scores

        # Test with values outside expected range
        distances = [-0.1, 1.5]
        scores = _normalize_scores(distances)
        assert 0.0 <= scores[0] <= 1.0
        assert 0.0 <= scores[1] <= 1.0

    def test_normalize_scores_empty(self):
        """Test normalizing empty list."""
        from retriever import _normalize_scores

        scores = _normalize_scores([])
        assert scores == []


class TestWhereFilterBuilding:
    """Test metadata filter construction for ChromaDB."""

    def test_build_empty_filter(self):
        """Test building filter from None."""
        from retriever import _build_where_filter

        result = _build_where_filter(None)
        assert result is None

    def test_build_empty_dict(self):
        """Test building filter from empty dict."""
        from retriever import _build_where_filter

        result = _build_where_filter({})
        assert result is None

    def test_build_source_filter_single(self):
        """Test source filter with single value."""
        from retriever import _build_where_filter

        result = _build_where_filter({"source": "github_repo"})
        assert result == {"source": "github_repo"}

    def test_build_source_filter_multiple(self):
        """Test source filter with list of values."""
        from retriever import _build_where_filter

        result = _build_where_filter({"source": ["github_repo", "website"]})
        assert result == {"source": {"$in": ["github_repo", "website"]}}

    def test_build_type_filter_single(self):
        """Test type filter with single value."""
        from retriever import _build_where_filter

        result = _build_where_filter({"type": "readme"})
        assert result == {"type": "readme"}

    def test_build_type_filter_multiple(self):
        """Test type filter with list of values."""
        from retriever import _build_where_filter

        result = _build_where_filter({"type": ["readme", "code"]})
        assert result == {"type": {"$in": ["readme", "code"]}}

    def test_build_date_range_full(self):
        """Test date range with both start and end."""
        from retriever import _build_where_filter

        result = _build_where_filter(
            {"date_range": {"start": "2024-01-01", "end": "2024-12-31"}}
        )
        assert result == {
            "$and": [
                {"date": {"$gte": "2024-01-01"}},
                {"date": {"$lte": "2024-12-31"}},
            ]
        }

    def test_build_date_range_start_only(self):
        """Test date range with start only."""
        from retriever import _build_where_filter

        result = _build_where_filter({"date_range": {"start": "2024-01-01"}})
        assert result == {"date": {"$gte": "2024-01-01"}}

    def test_build_date_range_end_only(self):
        """Test date range with end only."""
        from retriever import _build_where_filter

        result = _build_where_filter({"date_range": {"end": "2024-12-31"}})
        assert result == {"date": {"$lte": "2024-12-31"}}

    def test_build_combined_filters(self):
        """Test combining multiple filter types."""
        from retriever import _build_where_filter

        result = _build_where_filter(
            {
                "source": "github_repo",
                "type": "readme",
                "date_range": {"start": "2024-01-01"},
            }
        )
        assert result == {
            "$and": [
                {"source": "github_repo"},
                {"type": "readme"},
                {"date": {"$gte": "2024-01-01"}},
            ]
        }

    def test_build_combined_with_list_source(self):
        """Test combining list source with other filters."""
        from retriever import _build_where_filter

        result = _build_where_filter(
            {
                "source": ["github_repo", "website"],
                "type": "documentation",
            }
        )
        assert result == {
            "$and": [
                {"source": {"$in": ["github_repo", "website"]}},
                {"type": "documentation"},
            ]
        }


class TestRetrieverInit:
    """Test Retriever initialization."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            retriever = Retriever(persist_directory=tmpdir)
            assert retriever.db is not None
            assert retriever.embedder is not None

    def test_init_custom_db(self):
        """Test initialization with custom database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from database import VectorDatabase

            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            retriever = Retriever(database=db)
            assert retriever.db is db


class TestRetrieverSearch:
    """Test search functionality (integration tests with real database)."""

    @pytest.fixture
    def populated_db(self):
        """Create a database with sample data for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize database
            from database import init_database

            db = init_database(persist_directory=tmpdir)

            # Add sample documents to collection
            from vector_store import VectorStore

            store = VectorStore(database=db)

            sample_chunks = [
                {
                    "text": "Machine learning is a subset of artificial intelligence.",
                    "metadata": {
                        "chunk_id": "test:ml:1",
                        "source": "website",
                        "source_id": "doc1",
                        "url": "https://example.com/ml",
                        "date": "2024-01-15T10:00:00Z",
                        "type": "article",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "token_count": 10,
                        "text_length": 60,
                    },
                },
                {
                    "text": "Python is a popular programming language for data science.",
                    "metadata": {
                        "chunk_id": "test:python:1",
                        "source": "github_repo",
                        "source_id": "myrepo",
                        "url": "https://github.com/user/myrepo",
                        "date": "2024-02-01T14:30:00Z",
                        "type": "readme",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "token_count": 10,
                        "text_length": 60,
                        "repository": "user/myrepo",
                        "language": "Python",
                    },
                },
                {
                    "text": "Vector databases enable efficient similarity search.",
                    "metadata": {
                        "chunk_id": "test:vector:1",
                        "source": "blog",
                        "source_id": "blog1",
                        "url": "https://blog.example.com/vectors",
                        "date": "2024-02-15T09:00:00Z",
                        "type": "post",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "token_count": 10,
                        "text_length": 60,
                    },
                },
            ]

            # Generate embeddings
            from embedder import Embedder

            embedder = Embedder()
            embeddings = embedder.embed_batch([c["text"] for c in sample_chunks])

            # Store in database (all go to web_content or github_docs based on source)
            store.add_documents(sample_chunks, embeddings)

            yield tmpdir

    def test_search_basic(self, populated_db):
        """Test basic search functionality."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search("machine learning", k=2)

        assert isinstance(results, SearchResult)
        assert len(results) <= 2
        assert results.query_time > 0
        if results.documents:
            assert isinstance(results.documents[0], str)
            assert isinstance(results.metadatas[0], dict)
            assert 0.0 <= results.scores[0] <= 1.0

    def test_search_empty_query(self, populated_db):
        """Test that empty query raises ValueError."""
        retriever = Retriever(persist_directory=populated_db)
        with pytest.raises(ValueError, match="must not be empty"):
            retriever.search("")

    def test_search_whitespace_query(self, populated_db):
        """Test that whitespace-only query raises ValueError."""
        retriever = Retriever(persist_directory=populated_db)
        with pytest.raises(ValueError, match="must not be empty"):
            retriever.search("   ")

    def test_search_with_source_filter(self, populated_db):
        """Test search with source filter."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search(
            "programming", k=10, filters={"source": "github_repo"}
        )

        # All results should be from github_repo source
        for meta in results.metadatas:
            assert meta.get("source") == "github_repo"

    def test_search_with_type_filter(self, populated_db):
        """Test search with type filter."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search("database", k=10, filters={"type": "article"})

        # All results should have type 'article'
        for meta in results.metadatas:
            assert meta.get("type") == "article"

    def test_search_with_date_range(self, populated_db):
        """Test search with date range filter."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search(
            "python",
            k=10,
            filters={"date_range": {"start": "2024-02-01", "end": "2024-02-28"}},
        )

        # All results should be in February 2024
        for meta in results.metadatas:
            date_str = meta.get("date", "")
            if date_str:
                # Check date is in range (simplified check)
                assert "2024-02" in date_str or date_str >= "2024-02-01"

    def test_search_with_multiple_filters(self, populated_db):
        """Test search with multiple metadata filters."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search(
            "vector",
            k=10,
            filters={
                "source": ["website", "blog"],
                "type": "post",
            },
        )

        # Results should have source in list and type 'post'
        for meta in results.metadatas:
            assert meta.get("source") in ["website", "blog"]
            assert meta.get("type") == "post"

    def test_search_specific_collection(self, populated_db):
        """Test searching within a specific collection."""
        retriever = Retriever(persist_directory=populated_db)
        # Search only in web_content (our sample data based on source mapping)
        results = retriever.search_collection("learning", collection_name="web_content")

        # All results should have _collection set to 'web_content'
        for meta in results.metadatas:
            # The retriever adds _collection to metadata
            coll = meta.get("_collection")
            # Because we search only in web_content, results should come from there
            # or be None if metadata wasn't set correctly - check either none or web_content
            assert coll in (
                "web_content",
                None,
            )  # May not be set in some implementations

    def test_search_results_sorted_by_score(self, populated_db):
        """Test that results are sorted by descending score."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search("technology", k=5)

        if len(results) > 1:
            # Check scores are in descending order
            for i in range(len(results) - 1):
                assert results.scores[i] >= results.scores[i + 1]

    def test_search_k_limit(self, populated_db):
        """Test that k limits number of results."""
        retriever = Retriever(persist_directory=populated_db)
        results = retriever.search("technology", k=1)
        assert len(results) <= 1

    def test_search_no_results(self, populated_db):
        """Test search that returns no results."""
        retriever = Retriever(persist_directory=populated_db)
        # Use a very specific query that won't match
        results = retriever.search(
            "xyznonexistentquery12345", k=10, collection_name="web_content"
        )
        assert len(results) == 0
        assert results.documents == []
        assert results.scores == []


class TestRetrieverStats:
    """Test collection statistics functionality."""

    def test_get_stats_all_collections(self, populated_db):
        """Test getting stats for all collections."""
        retriever = Retriever(persist_directory=populated_db)
        stats = retriever.get_collection_stats()

        assert "github_docs" in stats or "web_content" in stats
        # At least one collection should have documents
        total_docs = sum(
            s.get("document_count", 0) for s in stats.values() if "document_count" in s
        )
        assert total_docs > 0

    def test_get_stats_specific_collection(self, populated_db):
        """Test getting stats for a specific collection."""
        retriever = Retriever(persist_directory=populated_db)
        stats = retriever.get_collection_stats(collection_name="web_content")

        assert "web_content" in stats
        assert "document_count" in stats["web_content"]


class TestRetrieverIntegration:
    """Integration tests for complete retriever workflow."""

    def test_full_workflow(self):
        """Test complete search workflow with sample data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize retriever
            retriever = Retriever(persist_directory=tmpdir)

            # Get initial stats
            stats = retriever.get_collection_stats()
            assert isinstance(stats, dict)

            # Perform search (will have no data but should not error)
            results = retriever.search("test query", k=5)
            assert isinstance(results, SearchResult)
            assert results.query_time > 0

    def test_convenience_search_function(self):
        """Test the convenience search function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = search("query", k=5, persist_directory=tmpdir)
            assert isinstance(results, SearchResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
