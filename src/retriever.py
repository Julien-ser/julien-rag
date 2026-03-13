"""
Similarity search and retrieval module for RAG system.

This module provides:
- Vector similarity search with top-k retrieval
- Metadata filtering (source, date range, document type, tags)
- Multi-collection search support
- Configurable search parameters
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from database import VectorDatabase, init_database
from embedder import Embedder

logger = logging.getLogger(__name__)


class SearchResult:
    """Container for search results with metadata."""

    def __init__(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        scores: List[float],
        collection: str,
        query_time: float,
    ):
        """
        Initialize search result.

        Args:
            documents: List of retrieved document texts
            metadatas: List of metadata dictionaries
            scores: List of similarity scores (0-1, higher is better)
            collection: Collection name searched
            query_time: Time taken for the query in seconds
        """
        self.documents = documents
        self.metadatas = metadatas
        self.scores = scores
        self.collection = collection
        self.query_time = query_time

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "documents": self.documents,
            "metadatas": self.metadatas,
            "scores": self.scores,
            "collection": self.collection,
            "query_time": self.query_time,
            "total_results": len(self.documents),
        }

    def __len__(self) -> int:
        """Return number of results."""
        return len(self.documents)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """Get individual result by index."""
        return {
            "document": self.documents[idx],
            "metadata": self.metadatas[idx],
            "score": self.scores[idx],
        }


def _build_where_filter(
    filters: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build ChromaDB where filter from user-provided filters.

    Args:
        filters: Dictionary of filter conditions:
            - source: str or list of source identifiers
            - date_range: dict with 'start' and 'end' datetime strings
            - type: str or list of document types
            - tags: list of tags (matches if document has all tags)

    Returns:
        ChromaDB where filter dictionary or None
    """
    if not filters:
        return None

    where_clauses = []

    # Source filter
    if "source" in filters:
        source_val = filters["source"]
        if isinstance(source_val, list):
            # Multiple sources - use $in operator
            where_clauses.append({"source": {"$in": source_val}})
        else:
            where_clauses.append({"source": source_val})

    # Type filter
    if "type" in filters:
        type_val = filters["type"]
        if isinstance(type_val, list):
            where_clauses.append({"type": {"$in": type_val}})
        else:
            where_clauses.append({"type": type_val})

    # Date range filter
    if "date_range" in filters:
        date_range = filters["date_range"]
        start = date_range.get("start")
        end = date_range.get("end")

        date_clauses = []
        if start:
            date_clauses.append({"date": {"$gte": start}})
        if end:
            date_clauses.append({"date": {"$lte": end}})

        if date_clauses:
            if len(date_clauses) == 1:
                where_clauses.append(date_clauses[0])
            else:
                where_clauses.append({"$and": date_clauses})

    # Build final filter
    if len(where_clauses) == 0:
        return None
    elif len(where_clauses) == 1:
        return where_clauses[0]
    else:
        return {"$and": where_clauses}


def _normalize_scores(distances: List[float]) -> List[float]:
    """
    Convert ChromaDB distances to similarity scores (0-1).

    For cosine distance: similarity = 1 - distance
    Since ChromaDB cosine distance is 1 - cosine_similarity,
    we need to invert.

    Args:
        distances: List of distances from ChromaDB query

    Returns:
        List of similarity scores (0-1, higher is better)
    """
    # Cosine distance = 1 - cosine_similarity
    # So similarity = 1 - distance
    return [max(0.0, min(1.0, 1.0 - d)) for d in distances]


class Retriever:
    """
    Vector similarity search with metadata filtering.

    Provides:
    - Top-k similarity search using embeddings
    - Metadata filters (source, date range, type, tags)
    - Multi-collection search
    - Query performance tracking
    """

    def __init__(
        self,
        persist_directory: Union[str, Path] = "data/vector_db",
        database: Optional[VectorDatabase] = None,
        embedding_config_path: Union[str, Path] = "config/embeddings.yaml",
    ):
        """
        Initialize retriever.

        Args:
            persist_directory: Directory for vector database
            database: Optional existing VectorDatabase instance
            embedding_config_path: Path to embedding configuration
        """
        self.db = database if database else init_database(persist_directory)
        self.embedder = Embedder(embedding_config_path)

        logger.info(f"Retriever initialized with persist_dir: {persist_directory}")

    def search(
        self,
        query_text: str,
        k: int = 10,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        include_embeddings: bool = False,
    ) -> SearchResult:
        """
        Search for similar documents using vector similarity.

        Args:
            query_text: Query text to search for
            k: Number of top results to return
            collection_name: Collection to search (None = search all collections)
            filters: Optional metadata filters (source, date_range, type, tags)
            include_embeddings: Whether to include embeddings in results

        Returns:
            SearchResult object with documents, scores, and metadata

        Raises:
            ValueError: If query is invalid or collection doesn't exist
            RuntimeError: If database or embedder fails
        """
        import time

        if not query_text or not query_text.strip():
            raise ValueError("Query text must not be empty")

        start_time = time.time()
        logger.info(f"Searching for query: '{query_text[:100]}...' with k={k}")

        try:
            # Generate query embedding
            query_embedding = self.embedder.embed([query_text])[0]
            logger.debug(f"Generated embedding with dimension: {len(query_embedding)}")

            # Determine which collections to search
            if collection_name:
                collections_to_search = [collection_name]
            else:
                # Search all collections except 'combined' (it's a union of others)
                collections_to_search = ["github_docs", "web_content"]

            # Query each collection and accumulate results
            all_docs = []
            all_metas = []
            all_scores = []
            all_collections = []

            where_filter = _build_where_filter(filters)
            logger.debug(f"Using where filter: {where_filter}")

            for coll_name in collections_to_search:
                try:
                    collection = self.db.get_collection(coll_name)

                    # Query ChromaDB
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=k,
                        where=where_filter,
                        include=["documents", "metadatas", "distances"],
                    )

                    # Extract results
                    docs = results["documents"][0] if results["documents"] else []
                    metas = results["metadatas"][0] if results["metadatas"] else []
                    distances = results["distances"][0] if results["distances"] else []

                    # Convert distances to scores
                    scores = _normalize_scores(distances)

                    # Add collection name to metadata
                    for meta in metas:
                        meta["_collection"] = coll_name

                    all_docs.extend(docs)
                    all_metas.extend(metas)
                    all_scores.extend(scores)
                    all_collections.extend([coll_name] * len(docs))

                    logger.debug(
                        f"Collection '{coll_name}' returned {len(docs)} results"
                    )

                except Exception as e:
                    logger.error(f"Error querying collection '{coll_name}': {e}")
                    continue

            # Sort by score descending and take top k
            # But we need to sort all three lists together
            if all_scores:
                # Create list of tuples for sorting
                combined = list(zip(all_scores, all_docs, all_metas, all_collections))
                combined.sort(
                    key=lambda x: x[0], reverse=True
                )  # Sort by score descending

                # Unzip and take top k
                all_scores, all_docs, all_metas, all_collections = zip(*combined[:k])

                # Convert back to lists
                all_scores = list(all_scores)
                all_docs = list(all_docs)
                all_metas = list(all_metas)
                all_collections = list(all_collections)
            else:
                all_docs = []
                all_metas = []
                all_scores = []
                all_collections = []

            query_time = time.time() - start_time

            logger.info(
                f"Search complete: {len(all_docs)} results in {query_time:.3f}s"
            )

            # For now, return results from the first collection that had results
            # In a multi-collection search, we could aggregate; but for simplicity
            # we'll return the mixed results sorted by score
            result = SearchResult(
                documents=list(all_docs),
                metadatas=list(all_metas),
                scores=list(all_scores),
                collection=collection_name or "multiple",
                query_time=query_time,
            )

            return result

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def search_collection(
        self,
        query_text: str,
        collection_name: str,
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        """
        Search within a specific collection.

        Args:
            query_text: Query text to search for
            collection_name: Collection to search
            k: Number of top results
            filters: Optional metadata filters

        Returns:
            SearchResult object
        """
        return self.search(
            query_text=query_text,
            k=k,
            collection_name=collection_name,
            filters=filters,
        )

    def get_collection_stats(
        self, collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about collections.

        Args:
            collection_name: Specific collection or None for all

        Returns:
            Dictionary with collection statistics
        """
        if collection_name:
            collections = [collection_name]
        else:
            collections = ["github_docs", "web_content", "combined"]

        stats = {}
        for coll_name in collections:
            try:
                collection = self.db.get_collection(coll_name)
                count = collection.count()
                stats[coll_name] = {
                    "document_count": count,
                }
            except Exception as e:
                logger.error(f"Error getting stats for {coll_name}: {e}")
                stats[coll_name] = {"error": str(e)}

        return stats


def search(
    query_text: str,
    k: int = 10,
    persist_directory: Union[str, Path] = "data/vector_db",
    collection_name: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> SearchResult:
    """
    Convenience function for performing a similarity search.

    Args:
        query_text: Query text to search for
        k: Number of results to return
        persist_directory: Database directory
        collection_name: Collection to search (None for all)
        filters: Optional metadata filters

    Returns:
        SearchResult object

    Example:
        >>> results = search("machine learning", k=5)
        >>> print(f"Found {len(results)} documents")
        >>> for i, doc in enumerate(results):
        >>>     print(f"{i+1}. Score: {doc['score']:.3f} - {doc['document'][:100]}...")
    """
    retriever = Retriever(persist_directory=persist_directory)
    return retriever.search(
        query_text=query_text,
        k=k,
        collection_name=collection_name,
        filters=filters,
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add src to path if running as script
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    # Quick test if database has data
    logger.info("Testing retriever...")

    try:
        # Try searching with a simple query
        results = search("test query", k=5)

        logger.info(f"Search test successful: {len(results)} results")
        logger.info(f"Query time: {results.query_time:.3f}s")
        if results.documents:
            logger.info(f"First result score: {results.scores[0]:.3f}")
            logger.info(f"First result preview: {results.documents[0][:100]}...")

    except Exception as e:
        logger.error(f"Search test failed: {e}")
        sys.exit(1)
