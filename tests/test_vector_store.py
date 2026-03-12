"""
Unit tests for vector_store module.

Tests:
- VectorStore initialization
- Document validation
- Collection mapping
- Add documents with embeddings
- Batch operations
- JSONL file ingestion
- Collection statistics
- Document deletion and clearing
- Error handling
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json
from pathlib import Path
import logging

from src.vector_store import VectorStore, VectorDatabase, ingest_chunks_from_file


class MockChromaCollection:
    """Mock ChromaDB collection for testing."""

    def __init__(self, name):
        self.name = name
        self._data = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
        self.count_val = 0

    def upsert(self, ids, embeddings, documents, metadatas):
        """Mock upsert operation."""
        self._data["ids"].extend(ids)
        self._data["embeddings"].extend(embeddings)
        self._data["documents"].extend(documents)
        self._data["metadatas"].extend(metadatas)
        self.count_val = len(self._data["ids"])

    def get(self, include=None, limit=None, offset=None):
        """Mock get operation."""
        if limit is None:
            limit = len(self._data["ids"])
        start = offset or 0
        end = start + limit

        result = {
            "ids": self._data["ids"][start:end],
            "documents": self._data["documents"][start:end],
            "metadatas": self._data["metadatas"][start:end],
        }
        return result

    def count(self):
        """Mock count operation."""
        return self.count_val

    def delete(self, ids=None):
        """Mock delete operation."""
        if ids:
            # Remove specified ids
            new_data = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
            for i, id_val in enumerate(self._data["ids"]):
                if id_val not in ids:
                    new_data["ids"].append(id_val)
                    new_data["embeddings"].append(self._data["embeddings"][i])
                    new_data["documents"].append(self._data["documents"][i])
                    new_data["metadatas"].append(self._data["metadatas"][i])
            self._data = new_data
            self.count_val = len(self._data["ids"])


class MockChromaClient:
    """Mock ChromaDB client for testing."""

    def __init__(self, path, settings=None, **kwargs):
        """Initialize mock client."""
        self.path = path
        self.settings = settings
        self.collections = {}
        self.settings = None

    def list_collections(self):
        """List all collections."""
        # Return list of collection objects with .name attribute
        mocks = []
        for name in self.collections.keys():
            m = Mock()
            m.name = name
            mocks.append(m)
        return mocks

    def get_collection(self, name):
        """Get or create collection."""
        if name not in self.collections:
            raise ValueError(f"Collection {name} not found")
        return self.collections[name]

    def create_collection(self, name, metadata=None):
        """Create collection."""
        if name not in self.collections:
            self.collections[name] = MockChromaCollection(name)
        return self.collections[name]

    def delete_collection(self, name):
        """Delete collection."""
        if name in self.collections:
            del self.collections[name]

    def reset(self):
        """Reset all collections."""
        self.collections.clear()


class TestVectorStore(unittest.TestCase):
    """Test VectorStore class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.persist_dir = Path(self.temp_dir.name) / "vector_db"

        # Mock chromadb at the database module level
        self.patcher_db_chromadb = patch("src.database.chromadb")
        self.mock_db_chromadb = self.patcher_db_chromadb.start()
        self.mock_db_chromadb.PersistentClient = MockChromaClient
        self.mock_db_chromadb.errors = Mock()
        self.mock_db_chromadb.errors.NotFoundError = ValueError

    def tearDown(self):
        """Clean up."""
        self.patcher_db_chromadb.stop()
        self.temp_dir.cleanup()

    def test_init_with_defaults(self):
        """Test VectorStore initialization with defaults."""
        store = VectorStore(persist_directory=self.persist_dir)
        self.assertIsNotNone(store.db)
        self.assertEqual(store.db.persist_directory, self.persist_dir)

    def test_init_with_existing_database(self):
        """Test VectorStore with existing database."""
        db = Mock(spec=VectorDatabase)
        store = VectorStore(database=db)
        self.assertEqual(store.db, db)

    def test_get_collection(self):
        """Test getting collection."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        collection = store._get_collection("github_docs")
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, "github_docs")

    def test_validate_chunk_valid(self):
        """Test chunk validation with valid chunk."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {
            "text": "Sample text content",
            "metadata": {"chunk_id": "test:1", "source": "github_repo"},
        }

        self.assertTrue(store._validate_chunk(chunk))

    def test_validate_chunk_invalid_type(self):
        """Test chunk validation with invalid type."""
        store = VectorStore(persist_directory=self.persist_dir)

        self.assertFalse(store._validate_chunk("not a dict"))

    def test_validate_chunk_missing_text(self):
        """Test chunk validation with missing text."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {"metadata": {"chunk_id": "test:1", "source": "github"}}
        self.assertFalse(store._validate_chunk(chunk))

    def test_validate_chunk_empty_text(self):
        """Test chunk validation with empty text."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {"text": "", "metadata": {"chunk_id": "test:1", "source": "github"}}
        self.assertFalse(store._validate_chunk(chunk))

    def test_validate_chunk_missing_metadata(self):
        """Test chunk validation with missing metadata."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {"text": "Sample text"}
        self.assertFalse(store._validate_chunk(chunk))

    def test_validate_chunk_metadata_not_dict(self):
        """Test chunk validation with metadata not a dict."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {"text": "Sample text", "metadata": "not a dict"}
        self.assertFalse(store._validate_chunk(chunk))

    def test_validate_chunk_missing_required_field(self):
        """Test chunk validation missing required metadata field."""
        store = VectorStore(persist_directory=self.persist_dir)

        chunk = {
            "text": "Sample text",
            "metadata": {"chunk_id": "test:1"},  # missing 'source'
        }
        self.assertFalse(store._validate_chunk(chunk))

    def test_map_to_collection_github(self):
        """Test source mapping for GitHub sources."""
        store = VectorStore(persist_directory=self.persist_dir)

        self.assertEqual(store._map_to_collection("github_repo"), "github_docs")
        self.assertEqual(store._map_to_collection("github_issue"), "github_docs")
        self.assertEqual(store._map_to_collection("github_pr"), "github_docs")
        self.assertEqual(store._map_to_collection("github_gist"), "github_docs")

    def test_map_to_collection_web(self):
        """Test source mapping for web sources."""
        store = VectorStore(persist_directory=self.persist_dir)

        self.assertEqual(store._map_to_collection("blog"), "web_content")
        self.assertEqual(store._map_to_collection("forum"), "web_content")
        self.assertEqual(store._map_to_collection("website"), "web_content")
        self.assertEqual(store._map_to_collection("linkedin"), "web_content")
        self.assertEqual(store._map_to_collection("twitter"), "web_content")

    def test_map_to_collection_unknown(self):
        """Test source mapping for unknown sources."""
        store = VectorStore(persist_directory=self.persist_dir)

        self.assertEqual(store._map_to_collection("unknown_source"), "combined")
        self.assertEqual(store._map_to_collection("random"), "combined")

    def test_add_documents_basic(self):
        """Test adding documents to vector store."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {
                "text": "Document 1",
                "metadata": {
                    "chunk_id": "doc1",
                    "source": "github_repo",
                    "url": "https://github.com/test/repo",
                },
            }
        ]
        embeddings = [[0.1, 0.2, 0.3]]

        added = store.add_documents(chunks, embeddings)
        self.assertEqual(added, 1)

        # Verify document stored
        collection = store.db.get_collection("github_docs")
        self.assertEqual(collection.count(), 1)

    def test_add_documents_multiple_collections(self):
        """Test adding documents to multiple collections."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {
                "text": "GitHub doc",
                "metadata": {"chunk_id": "gh1", "source": "github_repo"},
            },
            {"text": "Web doc", "metadata": {"chunk_id": "web1", "source": "blog"}},
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        added = store.add_documents(chunks, embeddings)
        self.assertEqual(added, 2)

        # Verify both collections have documents
        github_coll = store.db.get_collection("github_docs")
        web_coll = store.db.get_collection("web_content")
        self.assertEqual(github_coll.count(), 1)
        self.assertEqual(web_coll.count(), 1)

    def test_add_documents_with_length_mismatch(self):
        """Test error when chunks and embeddings length mismatch."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [{"text": "doc1", "metadata": {"chunk_id": "1", "source": "github"}}]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]  # 2 embeddings for 1 chunk

        with self.assertRaises(ValueError):
            store.add_documents(chunks, embeddings)

    def test_add_documents_invalid_chunks(self):
        """Test adding invalid chunks (filtered out)."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {"text": "", "metadata": {"chunk_id": "1", "source": "github"}},  # Invalid
            {"text": "Valid doc", "metadata": {"chunk_id": "2", "source": "github"}},
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        added = store.add_documents(chunks, embeddings)
        self.assertEqual(added, 1)  # Only valid one added

    def test_add_documents_batch_size(self):
        """Test adding documents with custom batch size."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {"text": f"doc{i}", "metadata": {"chunk_id": str(i), "source": "github"}}
            for i in range(10)
        ]
        embeddings = [[0.1 * i] * 10 for i in range(10)]

        added = store.add_documents(chunks, embeddings, batch_size=3)
        self.assertEqual(added, 10)

        # Verify all documents stored
        github_coll = store.db.get_collection("github_docs")
        self.assertEqual(github_coll.count(), 10)

    def test_add_chunks_with_embeddings(self):
        """Test convenience method add_chunks_with_embeddings."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [{"text": "doc1", "metadata": {"chunk_id": "1", "source": "website"}}]
        embeddings = [[0.1, 0.2]]

        added = store.add_chunks_with_embeddings(chunks, embeddings)
        self.assertEqual(added, 1)

    def test_add_jsonl_file(self):
        """Test loading chunks from JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "chunks.jsonl"

            chunks_data = [
                {
                    "text": "Chunk 1",
                    "metadata": {"chunk_id": "c1", "source": "github_repo"},
                },
                {"text": "Chunk 2", "metadata": {"chunk_id": "c2", "source": "blog"}},
            ]

            with open(jsonl_path, "w") as f:
                for chunk in chunks_data:
                    f.write(json.dumps(chunk) + "\n")

            store = VectorStore(persist_directory=self.persist_dir)
            store.db.init_database()

            # Mock embeddings
            embeddings = [[0.1, 0.2], [0.3, 0.4]]

            added = store.add_jsonl_file(jsonl_path, embeddings)
            self.assertEqual(added, 2)

    def test_add_jsonl_file_with_invalid_json(self):
        """Test JSONL file with some invalid lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "chunks.jsonl"

            with open(jsonl_path, "w") as f:
                f.write(
                    '{"text": "chunk1", "metadata": {"chunk_id": "c1", "source": "github"}}\n'
                )
                f.write("invalid json line\n")
                f.write(
                    '{"text": "chunk2", "metadata": {"chunk_id": "c2", "source": "github"}}\n'
                )

            store = VectorStore(persist_directory=self.persist_dir)
            store.db.init_database()

            embeddings = [[0.1], [0.2]]

            added = store.add_jsonl_file(jsonl_path, embeddings)
            # Should only add valid chunks (2)
            self.assertEqual(added, 2)

    def test_get_collection_stats(self):
        """Test getting collection statistics."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        # Add a document
        chunks = [{"text": "doc", "metadata": {"chunk_id": "1", "source": "github"}}]
        embeddings = [[0.1, 0.2]]
        store.add_documents(chunks, embeddings)

        stats = store.get_collection_stats("github_docs")
        self.assertEqual(stats["collection"], "github_docs")
        self.assertEqual(stats["document_count"], 1)

    def test_get_collection_stats_error(self):
        """Test getting stats for non-existent collection."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        stats = store.get_collection_stats("nonexistent")
        self.assertIn("error", stats)

    def test_list_all_documents(self):
        """Test listing documents in collection."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {"text": "doc1", "metadata": {"chunk_id": "1", "source": "github"}},
            {"text": "doc2", "metadata": {"chunk_id": "2", "source": "github"}},
        ]
        embeddings = [[0.1], [0.2]]
        store.add_documents(chunks, embeddings)

        docs = store.list_all_documents("github_docs", limit=10)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["text"], "doc1")
        self.assertEqual(docs[1]["text"], "doc2")

    def test_list_all_documents_pagination(self):
        """Test pagination for list_all_documents."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {"text": f"doc{i}", "metadata": {"chunk_id": str(i), "source": "github"}}
            for i in range(5)
        ]
        embeddings = [[0.1 * i] for i in range(5)]
        store.add_documents(chunks, embeddings)

        # Get with offset
        docs = store.list_all_documents("github_docs", limit=2, offset=2)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["text"], "doc2")
        self.assertEqual(docs[1]["text"], "doc3")

    def test_delete_by_metadata(self):
        """Test deleting documents by metadata filter."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {
                "text": "doc1",
                "metadata": {"chunk_id": "1", "source": "github", "repo": "test/repo1"},
            },
            {
                "text": "doc2",
                "metadata": {"chunk_id": "2", "source": "github", "repo": "test/repo2"},
            },
        ]
        embeddings = [[0.1], [0.2]]
        store.add_documents(chunks, embeddings)

        # Delete by repo filter
        deleted = store.delete_by_metadata("github_docs", {"repo": "test/repo1"})
        self.assertEqual(deleted, 1)

        # Verify only one remains
        collection = store.db.get_collection("github_docs")
        self.assertEqual(collection.count(), 1)

    def test_clear_collection(self):
        """Test clearing a collection."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        chunks = [
            {"text": "doc1", "metadata": {"chunk_id": "1", "source": "github"}},
            {"text": "doc2", "metadata": {"chunk_id": "2", "source": "github"}},
        ]
        embeddings = [[0.1], [0.2]]
        store.add_documents(chunks, embeddings)

        # Clear collection
        success = store.clear_collection("github_docs")
        self.assertTrue(success)

        # Verify empty
        collection = store.db.get_collection("github_docs")
        self.assertEqual(collection.count(), 0)

    def test_get_total_document_count(self):
        """Test getting total document count across collections."""
        store = VectorStore(persist_directory=self.persist_dir)
        store.db.init_database()

        # Add to different collections
        chunks_github = [
            {"text": "gh", "metadata": {"chunk_id": "1", "source": "github_repo"}}
        ]
        chunks_web = [{"text": "web", "metadata": {"chunk_id": "2", "source": "blog"}}]
        embeddings_github = [[0.1]]
        embeddings_web = [[0.2]]

        store.add_documents(chunks_github, embeddings_github)
        store.add_documents(chunks_web, embeddings_web)

        total = store.get_total_document_count()
        self.assertEqual(total, 2)


class TestIngestChunksFromFile(unittest.TestCase):
    """Test ingest_chunks_from_file convenience function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.persist_dir = Path(self.temp_dir.name) / "vector_db"

        # Mock chromadb at the database module level
        self.patcher_db_chromadb = patch("src.database.chromadb")
        self.mock_db_chromadb = self.patcher_db_chromadb.start()
        self.mock_db_chromadb.PersistentClient = MockChromaClient
        self.mock_db_chromadb.errors = Mock()
        self.mock_db_chromadb.errors.NotFoundError = ValueError

        # Mock embedder - patch at the embedder module level used by ingest_chunks_from_file
        self.patcher_batch_embed = patch("src.embedder.batch_embed")
        self.mock_batch_embed = self.patcher_batch_embed.start()
        self.mock_batch_embed.return_value = [[0.1], [0.2]]

    def tearDown(self):
        """Clean up."""
        self.patcher_db_chromadb.stop()
        self.patcher_batch_embed.stop()
        self.temp_dir.cleanup()

    def test_ingest_chunks_from_file(self):
        """Test full ingestion from JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "chunks.jsonl"

            chunks_data = [
                {
                    "text": "Chunk 1",
                    "metadata": {"chunk_id": "c1", "source": "github_repo"},
                },
                {
                    "text": "Chunk 2",
                    "metadata": {"chunk_id": "c2", "source": "github_repo"},
                },
            ]

            with open(jsonl_path, "w") as f:
                for chunk in chunks_data:
                    f.write(json.dumps(chunk) + "\n")

            stats = ingest_chunks_from_file(
                jsonl_path,
                embedding_config_path="config/embeddings.yaml",
                batch_size=100,
            )

            self.assertIn("chunks_loaded", stats)
            self.assertIn("embeddings_generated", stats)
            self.assertIn("documents_added", stats)
            self.assertIn("collection", stats)
            self.assertIn("duration_seconds", stats)

            self.assertEqual(stats["chunks_loaded"], 2)
            self.assertEqual(stats["embeddings_generated"], 2)
            self.assertEqual(stats["documents_added"], 2)
            self.assertEqual(stats["collection"], "github_docs")

    def test_ingest_with_collection_override(self):
        """Test ingestion with collection override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "chunks.jsonl"

            chunks_data = [
                {"text": "Chunk", "metadata": {"chunk_id": "c1", "source": "unknown"}}
            ]

            with open(jsonl_path, "w") as f:
                f.write(json.dumps(chunks_data[0]) + "\n")

            # Override mock to return 1 embedding for 1 chunk
            self.mock_batch_embed.return_value = [[0.1]]

            stats = ingest_chunks_from_file(
                jsonl_path, collection_override="web_content"
            )

            self.assertEqual(stats["collection"], "web_content")

    def test_ingest_empty_file(self):
        """Test ingestion with empty or invalid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "empty.jsonl"
            jsonl_path.write_text("")

            stats = ingest_chunks_from_file(jsonl_path)

            self.assertIn("error", stats)
            self.assertEqual(stats["added"], 0)


if __name__ == "__main__":
    unittest.main()
