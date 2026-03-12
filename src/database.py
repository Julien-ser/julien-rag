"""
Vector database initialization and management for RAG system.

This module handles:
- ChromaDB persistent client setup with cosine similarity
- Collection creation with HNSW indexing
- Database directory management
- Collection lifecycle (create, get, list)
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# Collection names as defined in TASKS.md
COLLECTIONS = ["github_docs", "web_content", "combined"]


class VectorDatabase:
    """
    Vector database wrapper for ChromaDB with persistent storage.

    Provides:
    - Database initialization with proper configuration
    - Collection management with HNSW indexing
    - Cosine similarity metric
    - Easy access to collections
    """

    def __init__(self, persist_directory: Union[str, Path] = "data/vector_db"):
        """
        Initialize vector database client.

        Args:
            persist_directory: Directory for persistent database storage
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self._client: Optional[chromadb.PersistentClient] = None
        self._collections: Dict[str, chromadb.Collection] = {}

        logger.info(
            f"VectorDatabase initialized with persist_dir: {self.persist_directory}"
        )

    def init_database(self) -> None:
        """
        Initialize the ChromaDB client and ensure all required collections exist.

        Creates the persistent client and initializes collections with:
        - Cosine similarity metric
        - HNSW indexing (ChromaDB default)
        """
        logger.info("Initializing vector database...")

        # Create persistent client with default settings
        # ChromaDB uses HNSW index by default with cosine similarity
        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        logger.info(f"ChromaDB client created at: {self.persist_directory}")

        # Ensure all required collections exist
        for collection_name in COLLECTIONS:
            self.create_collection(collection_name)

        logger.info(
            f"Database initialization complete. Collections: {self.list_collections()}"
        )

    def create_collection(self, name: str) -> chromadb.Collection:
        """
        Create or get a collection with appropriate configuration.

        Args:
            name: Collection name (must be one of: github_docs, web_content, combined)

        Returns:
            ChromaDB collection instance

        Raises:
            ValueError: If collection name is not in allowed list
        """
        if name not in COLLECTIONS:
            raise ValueError(
                f"Invalid collection name: {name}. Must be one of {COLLECTIONS}"
            )

        if self._client is None:
            raise RuntimeError("Database not initialized. Call init_database() first.")

        # Check if collection already exists
        try:
            collection = self._client.get_collection(name=name)
            logger.debug(f"Collection '{name}' already exists")
        except chromadb.errors.NotFoundError:
            # Collection doesn't exist, create it
            collection = self._client.create_collection(
                name=name,
                metadata={"description": f"Collection for {name} documents"},
            )
            logger.info(f"Created collection: {name}")

        self._collections[name] = collection
        return collection

    def get_collection(self, name: str) -> chromadb.Collection:
        """
        Get an existing collection.

        Args:
            name: Collection name (github_docs, web_content, or combined)

        Returns:
            ChromaDB collection instance

        Raises:
            ValueError: If collection name is invalid or collection doesn't exist
        """
        if name not in COLLECTIONS:
            raise ValueError(
                f"Invalid collection name: {name}. Must be one of {COLLECTIONS}"
            )

        if name in self._collections:
            return self._collections[name]

        if self._client is None:
            raise RuntimeError("Database not initialized. Call init_database() first.")

        try:
            collection = self._client.get_collection(name=name)
            self._collections[name] = collection
            logger.debug(f"Retrieved collection: {name}")
            return collection
        except ValueError as e:
            logger.error(f"Collection '{name}' not found: {e}")
            raise ValueError(
                f"Collection '{name}' does not exist. Create it first with create_collection()."
            )

    def list_collections(self) -> List[str]:
        """
        List all collection names.

        Returns:
            List of collection names
        """
        if self._client is None:
            return []

        collections = self._client.list_collections()
        return [coll.name for coll in collections]

    def delete_collection(self, name: str) -> None:
        """
        Delete a collection.

        Args:
            name: Collection name to delete
        """
        if self._client is None:
            raise RuntimeError("Database not initialized. Call init_database() first.")

        if name in self._collections:
            del self._collections[name]

        try:
            self._client.delete_collection(name=name)
            logger.info(f"Deleted collection: {name}")
        except Exception as e:
            logger.warning(f"Error deleting collection {name}: {e}")

    def reset_database(self) -> None:
        """
        Reset the entire database (deletes all collections and data).

        Use with caution!
        """
        if self._client is None:
            raise RuntimeError("Database not initialized. Call init_database() first.")

        logger.warning("Resetting entire database - all data will be lost!")
        self._client.reset()
        self._collections.clear()

        # Recreate required collections
        for collection_name in COLLECTIONS:
            self.create_collection(collection_name)

        logger.info("Database reset complete")

    @property
    def client(self) -> chromadb.PersistentClient:
        """Get the underlying ChromaDB client."""
        if self._client is None:
            raise RuntimeError("Database not initialized. Call init_database() first.")
        return self._client

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with collection counts and database info
        """
        if self._client is None:
            return {"status": "not_initialized"}

        collections = self.list_collections()
        stats = {
            "status": "initialized",
            "persist_directory": str(self.persist_directory),
            "collections": {},
        }

        for coll_name in collections:
            try:
                coll = self.get_collection(coll_name)
                count = coll.count()
                stats["collections"][coll_name] = {
                    "document_count": count,
                }
            except Exception as e:
                logger.error(f"Error getting stats for {coll_name}: {e}")
                stats["collections"][coll_name] = {"error": str(e)}

        return stats


def init_database(
    persist_directory: Union[str, Path] = "data/vector_db",
) -> VectorDatabase:
    """
    Convenience function to initialize and return a database instance.

    Args:
        persist_directory: Directory for persistent database storage

    Returns:
        Initialized VectorDatabase instance

    Example:
        >>> db = init_database()
        >>> db.init_database()
        >>> collection = db.get_collection("github_docs")
    """
    db = VectorDatabase(persist_directory=persist_directory)
    db.init_database()
    return db


def create_collection(
    name: str, db: Optional[VectorDatabase] = None
) -> chromadb.Collection:
    """
    Create a collection in the database.

    Args:
        name: Collection name
        db: Optional VectorDatabase instance (creates new if None)

    Returns:
        ChromaDB collection
    """
    if db is None:
        db = init_database()
    elif not isinstance(db, VectorDatabase):
        raise TypeError(f"db must be VectorDatabase, got {type(db)}")

    return db.create_collection(name)


def get_collection(
    name: str, db: Optional[VectorDatabase] = None
) -> chromadb.Collection:
    """
    Get an existing collection.

    Args:
        name: Collection name
        db: Optional VectorDatabase instance (creates new if None)

    Returns:
        ChromaDB collection
    """
    if db is None:
        db = init_database()
    elif not isinstance(db, VectorDatabase):
        raise TypeError(f"db must be VectorDatabase, got {type(db)}")

    return db.get_collection(name)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize database with all collections
    logger = logging.getLogger(__name__)
    logger.info("Initializing vector database...")

    db = init_database()

    logger.info("Database statistics:")
    stats = db.get_stats()
    for key, value in stats.items():
        if key == "collections":
            for coll_name, coll_stats in value.items():
                logger.info(f"  {coll_name}: {coll_stats}")
        else:
            logger.info(f"  {key}: {value}")

    logger.info("Database ready for use!")
