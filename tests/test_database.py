"""
Tests for database module.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database import (
    VectorDatabase,
    init_database,
    create_collection,
    get_collection,
    COLLECTIONS,
)


class TestDatabaseImports:
    """Test that all database functions can be imported correctly."""

    def test_import_vector_database(self):
        """Test that VectorDatabase class exists."""
        assert VectorDatabase is not None

    def test_import_init_database(self):
        """Test that init_database function exists."""
        assert callable(init_database)

    def test_import_create_collection(self):
        """Test that create_collection function exists."""
        assert callable(create_collection)

    def test_import_get_collection(self):
        """Test that get_collection function exists."""
        assert callable(get_collection)

    def test_collections_constant(self):
        """Test that COLLECTIONS constant has required collections."""
        assert "github_docs" in COLLECTIONS
        assert "web_content" in COLLECTIONS
        assert "combined" in COLLECTIONS


class TestVectorDatabaseInit:
    """Test VectorDatabase initialization."""

    def test_init_default_directory(self):
        """Test initialization with default persist directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            assert db.persist_directory == Path(tmpdir)
            assert db._client is None
            assert db._collections == {}

    def test_init_custom_directory(self):
        """Test initialization with custom persist directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / "custom_db"
            db = VectorDatabase(persist_directory=custom_dir)
            assert db.persist_directory == custom_dir

    def test_init_creates_directory(self):
        """Test that initialization creates the persist directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "new_dir"
            assert not db_dir.exists()
            db = VectorDatabase(persist_directory=db_dir)
            assert db_dir.exists()


class TestDatabaseInitDatabase:
    """Test init_database method."""

    def test_init_database_creates_client(self):
        """Test that init_database creates a ChromaDB client."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            assert db._client is not None

    def test_init_database_creates_all_collections(self):
        """Test that init_database creates all required collections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            collections = db.list_collections()
            assert "github_docs" in collections
            assert "web_content" in collections
            assert "combined" in collections

    def test_init_database_idempotent(self):
        """Test that init_database can be called multiple times safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            # Call again - should not raise
            db.init_database()
            collections = db.list_collections()
            assert len(collections) == 3


class TestDatabaseCollectionManagement:
    """Test collection creation and retrieval."""

    def test_create_collection_valid(self):
        """Test creating a valid collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            collection = db.create_collection("github_docs")
            assert collection is not None
            assert collection.name == "github_docs"

    def test_create_collection_invalid(self):
        """Test that creating an invalid collection raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            with pytest.raises(ValueError, match="Invalid collection name"):
                db.create_collection("invalid_collection")

    def test_get_collection_existing(self):
        """Test getting an existing collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            collection = db.get_collection("web_content")
            assert collection is not None
            assert collection.name == "web_content"

    def test_get_collection_invalid(self):
        """Test that getting an invalid collection raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            with pytest.raises(ValueError, match="does not exist"):
                db.get_collection("nonexistent")

    def test_get_collection_before_init(self):
        """Test that getting collection before init raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            with pytest.raises(RuntimeError, match="Database not initialized"):
                db.get_collection("github_docs")

    def test_create_collection_before_init(self):
        """Test that creating collection before init raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            with pytest.raises(RuntimeError, match="Database not initialized"):
                db.create_collection("github_docs")


class TestDatabaseListCollections:
    """Test list_collections method."""

    def test_list_collections_after_init(self):
        """Test listing collections after initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            collections = db.list_collections()
            assert len(collections) == 3
            assert set(collections) == set(COLLECTIONS)

    def test_list_collections_before_init(self):
        """Test listing collections before initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            collections = db.list_collections()
            assert collections == []


class TestDatabaseDeleteCollection:
    """Test delete_collection method."""

    def test_delete_collection(self):
        """Test deleting a collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            # Verify collection exists
            collections_before = db.list_collections()
            assert "github_docs" in collections_before

            # Delete collection
            db.delete_collection("github_docs")

            # Verify it's gone
            collections_after = db.list_collections()
            assert "github_docs" not in collections_after

    def test_delete_collection_before_init(self):
        """Test that deleting before init raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            with pytest.raises(RuntimeError, match="Database not initialized"):
                db.delete_collection("github_docs")


class TestDatabaseReset:
    """Test reset_database method."""

    def test_reset_database(self):
        """Test resetting the database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()

            # Add some custom collection (would fail due to validation)
            # Just reset and check all original collections remain
            db.reset_database()
            collections = db.list_collections()
            assert set(collections) == set(COLLECTIONS)

    def test_reset_before_init(self):
        """Test that reset before init raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            with pytest.raises(RuntimeError, match="Database not initialized"):
                db.reset_database()


class TestDatabaseStats:
    """Test get_stats method."""

    def test_get_stats_after_init(self):
        """Test getting stats after initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            db.init_database()
            stats = db.get_stats()
            assert stats["status"] == "initialized"
            assert stats["persist_directory"] == str(Path(tmpdir))
            assert "collections" in stats
            assert "github_docs" in stats["collections"]
            assert "web_content" in stats["collections"]
            assert "combined" in stats["collections"]
            # All collections should have count 0 initially
            for coll_stats in stats["collections"].values():
                assert coll_stats["document_count"] == 0

    def test_get_stats_before_init(self):
        """Test getting stats before initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = VectorDatabase(persist_directory=tmpdir)
            stats = db.get_stats()
            assert stats["status"] == "not_initialized"


class TestConvenienceFunctions:
    """Test convenience module-level functions."""

    def test_init_database_function(self):
        """Test the init_database convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = init_database(persist_directory=tmpdir)
            assert isinstance(db, VectorDatabase)
            assert db._client is not None

    def test_create_collection_function(self):
        """Test the create_collection convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection = create_collection("github_docs", persist_directory=tmpdir)
            assert collection is not None
            assert collection.name == "github_docs"

    def test_get_collection_function(self):
        """Test the get_collection convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection = get_collection("web_content", persist_directory=tmpdir)
            assert collection is not None
            assert collection.name == "web_content"


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_full_workflow(self):
        """Test complete database workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize database
            db = init_database(persist_directory=tmpdir)
            stats = db.get_stats()
            assert stats["status"] == "initialized"

            # Verify all collections exist
            collections = db.list_collections()
            assert len(collections) == 3

            # Get each collection and verify they're accessible
            for coll_name in COLLECTIONS:
                collection = db.get_collection(coll_name)
                assert collection.name == coll_name
                assert collection.count() == 0

    def test_persistence_across_instances(self):
        """Test that database persists across different instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create first instance and init
            db1 = VectorDatabase(persist_directory=tmpdir)
            db1.init_database()

            # Create second instance pointing to same directory
            db2 = VectorDatabase(persist_directory=tmpdir)
            # Should be able to get collections without calling init_database
            # because ChromaDB will load existing database
            collection = db2.get_collection("github_docs")
            assert collection is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
