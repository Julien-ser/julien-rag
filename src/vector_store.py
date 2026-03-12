"""
Vector storage module for RAG system.

This module handles:
- Storing document chunks with embeddings in ChromaDB
- Batch operations with progress tracking
- Collection management (github_docs, web_content, combined)
- Metadata management and validation
- Error handling and retry logic
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from .database import VectorDatabase, init_database

logger = logging.getLogger(__name__)


class VectorStore:
    """
    High-level interface for storing and managing vectorized documents.

    Provides:
    - Batch document storage with embeddings
    - Collection-based organization
    - Progress tracking and logging
    - Metadata validation
    """

    def __init__(
        self,
        persist_directory: Union[str, Path] = "data/vector_db",
        database: Optional[VectorDatabase] = None,
    ):
        """
        Initialize vector store.

        Args:
            persist_directory: Directory for ChromaDB persistence
            database: Optional existing VectorDatabase instance
        """
        if database is not None:
            self.db = database
        else:
            logger.info(
                f"Initializing VectorStore with persist_dir: {persist_directory}"
            )
            self.db = init_database(persist_directory)
            self.db.init_database()

        self._collections_cache = {}

    def _get_collection(self, name: str):
        """Get or create collection."""
        if name not in self._collections_cache:
            self._collections_cache[name] = self.db.create_collection(name)
        return self._collections_cache[name]

    def _validate_chunk(self, chunk: Dict[str, Any]) -> bool:
        """
        Validate a chunk document before storage.

        Args:
            chunk: Chunk dictionary with 'text' and 'metadata'

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(chunk, dict):
            logger.warning(f"Invalid chunk type: {type(chunk)}")
            return False

        if "text" not in chunk or not chunk["text"]:
            logger.warning("Chunk missing 'text' field or empty")
            return False

        if "metadata" not in chunk or not isinstance(chunk["metadata"], dict):
            logger.warning("Chunk missing 'metadata' field or not a dict")
            return False

        # Check required metadata fields
        required_metadata = ["chunk_id", "source"]
        for field in required_metadata:
            if field not in chunk["metadata"]:
                logger.warning(f"Chunk missing required metadata field: {field}")
                return False

        return True

    def _map_to_collection(self, source: str) -> str:
        """
        Map source type to collection name.

        Args:
            source: Source identifier from chunk metadata

        Returns:
            Collection name (github_docs, web_content, or combined)
        """
        if source.startswith("github"):
            return "github_docs"
        elif source.startswith(("blog", "forum", "website", "linkedin", "twitter")):
            return "web_content"
        else:
            # Default to combined for unknown sources
            return "combined"

    def add_documents(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        collection_name: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        """
        Add documents with embeddings to the vector store.

        Args:
            chunks: List of chunk dictionaries with 'text' and 'metadata'
            embeddings: List of embedding vectors (must match chunks length)
            collection_name: Override collection name (auto-detected if None)
            batch_size: Number of documents to add per batch

        Returns:
            Number of documents successfully added

        Raises:
            ValueError: If chunks and embeddings length mismatch
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Length mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
            )

        total = len(chunks)
        added = 0
        failed = 0

        logger.info(f"Adding {total} documents to vector store")

        # Group chunks by collection
        collection_batches: Dict[str, List[Dict]] = {}
        for chunk, embedding in zip(chunks, embeddings):
            if not self._validate_chunk(chunk):
                failed += 1
                continue

            metadata = chunk["metadata"]
            source = metadata.get("source", "unknown")
            coll_name = collection_name or self._map_to_collection(source)

            if coll_name not in collection_batches:
                collection_batches[coll_name] = []
            collection_batches[coll_name].append(
                {
                    "text": chunk["text"],
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )

        # Add batches to each collection
        for coll_name, batch_list in collection_batches.items():
            collection = self._get_collection(coll_name)
            logger.info(
                f"Adding {len(batch_list)} documents to collection '{coll_name}'"
            )

            # Process in batches
            for i in range(0, len(batch_list), batch_size):
                batch = batch_list[i : i + batch_size]

                try:
                    # Prepare batch data for ChromaDB
                    ids = [item["metadata"]["chunk_id"] for item in batch]
                    embeddings = [item["embedding"] for item in batch]
                    documents = [item["text"] for item in batch]
                    metadatas = [item["metadata"] for item in batch]

                    # Upsert to collection
                    collection.upsert(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas,
                    )

                    added += len(batch)
                    logger.debug(
                        f"Added batch of {len(batch)} documents to {coll_name}"
                    )

                except Exception as e:
                    logger.error(f"Failed to add batch to {coll_name}: {e}")
                    failed += len(batch)
                    continue

        logger.info(f"Storage complete: {added} added, {failed} failed, {total} total")
        return added

    def add_chunks_with_embeddings(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        batch_size: int = 100,
    ) -> int:
        """
        Convenience method to add chunks with embeddings (auto-routes to collections).

        Args:
            chunks: List of chunk dictionaries
            embeddings: Corresponding embeddings
            batch_size: Batch size for storage

        Returns:
            Number of documents added
        """
        return self.add_documents(
            chunks=chunks,
            embeddings=embeddings,
            batch_size=batch_size,
        )

    def add_jsonl_file(
        self,
        jsonl_path: Union[str, Path],
        embeddings: List[List[float]],
        collection_name: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        """
        Load chunks from JSONL file and add with embeddings.

        Args:
            jsonl_path: Path to JSONL file with chunks
            embeddings: List of embedding vectors
            collection_name: Override collection name
            batch_size: Batch size

        Returns:
            Number of documents added
        """
        jsonl_path = Path(jsonl_path)

        logger.info(f"Loading chunks from {jsonl_path}")
        chunks = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    chunks.append(chunk)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON on line {line_num}: {e}")
                    continue

        logger.info(f"Loaded {len(chunks)} chunks from {jsonl_path}")

        return self.add_documents(
            chunks=chunks,
            embeddings=embeddings,
            collection_name=collection_name,
            batch_size=batch_size,
        )

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        Get statistics for a collection.

        Args:
            collection_name: Collection name

        Returns:
            Dictionary with count and other info
        """
        try:
            collection = self.db.get_collection(collection_name)
            count = collection.count()
            return {
                "collection": collection_name,
                "document_count": count,
            }
        except Exception as e:
            logger.error(f"Error getting stats for {collection_name}: {e}")
            return {
                "collection": collection_name,
                "error": str(e),
            }

    def list_all_documents(
        self,
        collection_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List documents in a collection.

        Args:
            collection_name: Collection to query
            limit: Maximum number of documents to return
            offset: Offset for pagination

        Returns:
            List of documents with id, document, metadata
        """
        try:
            collection = self.db.get_collection(collection_name)
            results = collection.get(
                limit=limit,
                offset=offset,
                include=["documents", "metadatas"],
            )

            documents = []
            for i, (doc_id, doc_text, metadata) in enumerate(
                zip(results["ids"], results["documents"], results["metadatas"])
            ):
                documents.append(
                    {
                        "id": doc_id,
                        "text": doc_text,
                        "metadata": metadata,
                    }
                )

            return documents
        except Exception as e:
            logger.error(f"Error listing documents in {collection_name}: {e}")
            return []

    def delete_by_metadata(
        self,
        collection_name: str,
        filters: Dict[str, Any],
    ) -> int:
        """
        Delete documents matching metadata filters.

        Args:
            collection_name: Collection to delete from
            filters: Metadata key-value pairs to match

        Returns:
            Number of documents deleted
        """
        try:
            collection = self.db.get_collection(collection_name)

            # Get all documents and filter manually (ChromaDB where filter may be limited)
            results = collection.get(include=["metadatas"])
            ids_to_delete = []

            for doc_id, metadata in zip(results["ids"], results["metadatas"]):
                match = all(metadata.get(k) == v for k, v in filters.items())
                if match:
                    ids_to_delete.append(doc_id)

            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(
                    f"Deleted {len(ids_to_delete)} documents from {collection_name}"
                )
                return len(ids_to_delete)

            return 0
        except Exception as e:
            logger.error(f"Error deleting from {collection_name}: {e}")
            return 0

    def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all documents from a collection.

        Args:
            collection_name: Collection to clear

        Returns:
            True if successful
        """
        try:
            self.db.delete_collection(collection_name)
            self.db.create_collection(collection_name)
            logger.info(f"Cleared collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error clearing {collection_name}: {e}")
            return False

    def get_total_document_count(self) -> int:
        """Get total document count across all collections."""
        stats = self.db.get_stats()
        total = 0
        for coll_name, coll_stats in stats.get("collections", {}).items():
            total += coll_stats.get("document_count", 0)
        return total


def ingest_chunks_from_file(
    chunks_jsonl_path: Union[str, Path],
    embedding_config_path: Union[str, Path] = "config/embeddings.yaml",
    batch_size: int = 100,
    collection_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to ingest preprocessed chunks from JSONL file.

    Args:
        chunks_jsonl_path: Path to JSONL file with chunks
        embedding_config_path: Path to embedding configuration
        batch_size: Batch size for operations
        collection_override: Optional collection name override

    Returns:
        Dictionary with ingestion statistics
    """
    import json

    start_time = time.time()

    logger.info(f"Starting ingestion of {chunks_jsonl_path}")

    # Load chunks
    chunks = []
    with open(chunks_jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                chunks.append(chunk)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON on line {line_num}: {e}")
                continue

    if not chunks:
        logger.warning("No valid chunks found in file")
        return {"error": "No valid chunks", "added": 0}

    # Determine collection from first chunk if not overridden
    if collection_override:
        collection = collection_override
    else:
        source = chunks[0]["metadata"].get("source", "unknown")
        store = VectorStore()
        collection = store._map_to_collection(source)

    # Generate embeddings
    logger.info(f"Generating embeddings for {len(chunks)} chunks...")
    from .embedder import batch_embed

    embeddings = batch_embed(
        chunks, batch_size=batch_size, config_path=embedding_config_path
    )

    # Store in database
    logger.info(f"Storing documents in collection '{collection}'...")
    store = VectorStore()
    added = store.add_documents(
        chunks=chunks,
        embeddings=embeddings,
        collection_name=collection,
        batch_size=batch_size,
    )

    duration = time.time() - start_time

    stats = {
        "chunks_loaded": len(chunks),
        "embeddings_generated": len(embeddings),
        "documents_added": added,
        "collection": collection,
        "duration_seconds": duration,
        "docs_per_second": added / duration if duration > 0 else 0,
    }

    logger.info(f"Ingestion complete: {stats}")
    return stats


if __name__ == "__main__":
    import os
    import json
    import time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Quick test with sample data
    logger.info("Testing vector store...")

    # Create sample chunks
    sample_chunks = [
        {
            "text": "This is sample document 1 about AI and machine learning.",
            "metadata": {
                "chunk_id": "test:doc1:0",
                "source": "website",
                "source_id": "doc1",
                "url": "https://example.com/doc1",
                "date": "2024-01-01T00:00:00Z",
                "type": "webpage",
                "chunk_index": 0,
                "total_chunks": 1,
                "token_count": 10,
                "text_length": 50,
            },
        },
        {
            "text": "This is sample document 2 about data science and analytics.",
            "metadata": {
                "chunk_id": "test:doc2:0",
                "source": "github_repo",
                "source_id": "myrepo",
                "url": "https://github.com/user/myrepo",
                "date": "2024-01-02T00:00:00Z",
                "type": "readme",
                "chunk_index": 0,
                "total_chunks": 1,
                "token_count": 10,
                "text_length": 50,
                "repository": "user/myrepo",
                "language": "Python",
            },
        },
    ]

    # Generate embeddings
    try:
        embedder = Embedder()
        embeddings = embedder.embed_batch([c["text"] for c in sample_chunks])

        # Store
        store = VectorStore()
        added = store.add_documents(sample_chunks, embeddings)

        logger.info(f"Test successful: {added} documents stored")

        # Show stats
        stats = store.db.get_stats()
        logger.info(f"Database stats: {stats}")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
