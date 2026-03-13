"""
FastAPI REST endpoints for RAG system.

This module provides:
- Search endpoint for similarity search
- Sources listing endpoint
- Database statistics endpoint
- Refresh/reindexing endpoint (admin protected)
- Health check endpoint
- Interactive API documentation at /docs

Features:
- Async endpoint support
- CORS enabled
- Pydantic request/response models
- Comprehensive error handling
- Structured logging
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from retriever import Retriever, SearchResult
from database import init_database
from pipeline import run_pipeline
from rag import RAGPipeline, RAGConfig
from monitoring import MetricsMiddleware, metrics_endpoint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Pydantic models
class QueryRequest(BaseModel):
    """Request model for search queries."""

    query: str = Field(
        ..., min_length=1, max_length=2000, description="Search query text"
    )
    k: int = Field(10, ge=1, le=100, description="Number of results to return")
    collection: Optional[str] = Field(
        None, description="Optional collection name to search"
    )
    filters: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata filters"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning project",
                "k": 5,
                "collection": "github_docs",
                "filters": {"source": "github_repos"},
            }
        }


class QueryResponse(BaseModel):
    """Response model for search results."""

    documents: List[str]
    metadatas: List[Dict[str, Any]]
    scores: List[float]
    collection: str
    query_time: float
    total_results: int

    class Config:
        json_schema_extra = {
            "example": {
                "documents": ["..."],
                "metadatas": [{"source": "github", "type": "repo"}],
                "scores": [0.95, 0.87],
                "collection": "github_docs",
                "query_time": 0.234,
                "total_results": 2,
            }
        }


class SourcesResponse(BaseModel):
    """Response model for available sources."""

    sources: List[str]
    description: str
    count: int

    class Config:
        json_schema_extra = {
            "example": {
                "sources": ["github_repos", "github_commits", "web_content"],
                "description": "Available data source types",
                "count": 3,
            }
        }


class StatsResponse(BaseModel):
    """Response model for database statistics."""

    status: str
    persist_directory: str
    collections: Dict[str, Dict[str, Any]]
    timestamp: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "status": "initialized",
                "persist_directory": "data/vector_db",
                "collections": {
                    "github_docs": {"document_count": 1500},
                    "web_content": {"document_count": 300},
                },
                "timestamp": "2024-01-15T10:30:00",
            }
        }


class RefreshResponse(BaseModel):
    """Response model for refresh operation."""

    status: str
    message: str
    stats: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Data refresh completed successfully",
                "stats": {"total_duration": "00:05:30"},
            }
        }


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    timestamp: datetime
    reason: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {"status": "healthy", "timestamp": "2024-01-15T10:30:00"}
        }


class RAGRequest(BaseModel):
    """Request model for RAG query."""

    query: str = Field(
        ..., min_length=1, max_length=2000, description="Question or query"
    )
    k: int = Field(10, ge=1, le=100, description="Number of context chunks to retrieve")
    collection: Optional[str] = Field(None, description="Optional collection to search")
    filters: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata filters"
    )
    return_context: bool = Field(
        False, description="Include retrieved context in response"
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Override LLM temperature"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, le=4000, description="Override max tokens to generate"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Explain the key architectural decisions in this project",
                "k": 5,
                "collection": "github_docs",
                "filters": {"source": "github_repos"},
                "return_context": False,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
        }


class RAGResponse(BaseModel):
    """Response model for RAG query."""

    answer: str = Field(..., description="Generated answer")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    sources: List[Dict[str, Any]] = Field(..., description="List of source documents")
    query_time: float = Field(..., description="Total query time in seconds")
    context_chunks: int = Field(..., description="Number of context chunks used")
    context_length: Optional[int] = Field(
        None, description="Length of context in characters"
    )
    context: Optional[str] = Field(
        None, description="Retrieved context if return_context=True"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "The project uses ChromaDB as the vector database...",
                "confidence": 0.92,
                "sources": [
                    {
                        "source": "github_repos",
                        "type": "repo",
                        "title": "julien-rag",
                        "url": "https://github.com/user/julien-rag",
                        "collection": "github_docs",
                    }
                ],
                "query_time": 1.234,
                "context_chunks": 5,
                "context_length": 1500,
                "context": None,
            }
        }


# FastAPI app initialization
app = FastAPI(
    title="Julien RAG API",
    description="Vector database RAG implementation with search capabilities",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware for automatic request tracking
app.add_middleware(MetricsMiddleware)

# Global retriever instance
retriever: Optional[Retriever] = None


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    global retriever
    try:
        logger.info("Initializing retriever...")
        retriever = Retriever()
        logger.info("Retriever initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize retriever: {e}")
        retriever = None


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global retriever
    retriever = None
    logger.info("API shutdown complete")


# Authentication dependency
async def verify_admin_token(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> bool:
    """
    Verify admin token for protected endpoints.

    Args:
        x_admin_token: Admin token from request header

    Returns:
        True if token is valid

    Raises:
        HTTPException: If token is invalid or missing
    """
    expected_token = os.getenv("ADMIN_TOKEN")

    # If no ADMIN_TOKEN set, allow all (development mode)
    if not expected_token:
        logger.warning("ADMIN_TOKEN not set, allowing all requests in dev mode")
        return True

    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required"
        )

    if x_admin_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token"
        )

    return True


# API Endpoints
@app.post("/query", response_model=QueryResponse, tags=["Search"])
async def query_endpoint(request: QueryRequest):
    """
    Search for relevant documents using vector similarity.

    Args:
        request: Query request with text, k, collection, and optional filters

    Returns:
        QueryResponse with matching documents, scores, and metadata

    Raises:
        HTTPException: If service is unavailable or query fails
    """
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )

    try:
        logger.info(f"Processing query: '{request.query[:100]}...' k={request.k}")

        result = retriever.search(
            query_text=request.query,
            k=request.k,
            collection_name=request.collection,
            filters=request.filters,
        )

        logger.info(
            f"Query completed: {len(result)} results in {result.query_time:.3f}s"
        )

        return result.to_dict()

    except ValueError as e:
        logger.warning(f"Invalid query request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )


@app.get("/sources", response_model=SourcesResponse, tags=["Metadata"])
async def get_sources():
    """
    List available source types in the database.

    Returns:
        SourcesResponse with list of unique source types found in metadata
    """
    # Known source types based on the data collection modules
    sources = [
        "github_repos",
        "github_commits",
        "github_issues",
        "github_gists",
        "github_starred",
        "web_content",
    ]

    logger.info(f"Returning {len(sources)} known source types")

    return SourcesResponse(
        sources=sources,
        description="Available data source types in the vector database",
        count=len(sources),
    )


@app.get("/stats", response_model=StatsResponse, tags=["Metadata"])
async def get_stats():
    """
    Get database statistics.

    Returns:
        StatsResponse with document counts per collection and database info
    """
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )

    try:
        # Get collection statistics from retriever
        collection_stats = retriever.get_collection_stats()

        # Get persist directory
        persist_dir = (
            str(retriever.db.persist_directory)
            if hasattr(retriever, "db") and retriever.db
            else "data/vector_db"
        )

        stats = {
            "status": "initialized",
            "persist_directory": persist_dir,
            "collections": collection_stats,
            "timestamp": datetime.utcnow(),
        }

        logger.info(f"Stats requested: {len(collection_stats)} collections")

        return stats

    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics",
        )


@app.post("/refresh", response_model=RefreshResponse, tags=["Admin"])
async def refresh_endpoint(admin_token: bool = Depends(verify_admin_token)):
    """
    Trigger reindexing of all data (admin only).

    This endpoint runs the full ingestion pipeline to collect fresh data
    from GitHub and web sources, process it, and update the vector database.

    Requires X-Admin-Token header with valid admin token.

    Args:
        admin_token: Verified admin authentication

    Returns:
        RefreshResponse with status and pipeline statistics
    """
    try:
        logger.info("Starting data refresh via API request")

        # Run the complete pipeline
        stats = run_pipeline()

        logger.info("Data refresh completed successfully")

        return RefreshResponse(
            status="success",
            message="Data refresh completed successfully",
            stats={
                "duration_seconds": stats.duration().total_seconds(),
                "github_files": stats.github_files_collected,
                "web_files": stats.web_files_collected,
                "files_processed": stats.files_processed,
                "chunks_generated": stats.chunks_generated,
                "errors": stats.collection_errors + stats.processing_errors,
            }
            if stats
            else None,
        )

    except Exception as e:
        logger.error(f"Refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refresh operation failed: {str(e)}",
        )


@app.post("/rag-query", response_model=RAGResponse, tags=["RAG"])
async def rag_query_endpoint(request: RAGRequest):
    """
    Generate answer using RAG (Retrieval-Augmented Generation).

    This endpoint retrieves relevant documents from the vector database
    and uses an LLM to generate an answer based on the retrieved context.

    Args:
        request: RAG query request with query, k, optional filters, and LLM overrides

    Returns:
        RAGResponse with generated answer, confidence score, and sources

    Raises:
        HTTPException: If service is unavailable or generation fails
    """
    global retriever
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )

    try:
        logger.info(
            f"Processing RAG query: '{request.query[:100]}...' "
            f"k={request.k}, return_context={request.return_context}"
        )

        # Initialize RAG pipeline with retriever
        rag_config_path = os.getenv("RAG_CONFIG", "config/rag.yaml")
        pipeline = RAGPipeline(retriever, config_path=rag_config_path)

        # Generate answer
        result = pipeline.generate(
            query=request.query,
            k=request.k,
            collection_name=request.collection,
            filters=request.filters,
            return_context=request.return_context,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        logger.info(
            f"RAG query completed: confidence={result['confidence']:.3f}, "
            f"time={result['query_time']:.3f}s, sources={len(result['sources'])}"
        )

        return result

    except ValueError as e:
        logger.warning(f"Invalid RAG query request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RAG generation failed",
        )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns:
        HealthResponse with service status
    """
    if retriever is None:
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            reason="retriever not initialized",
        )

    # Could add more checks: database connection, embedding service, etc.
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())


@app.get("/metrics", tags=["Monitoring"])
async def metrics_endpoint_handler():
    """
    Prometheus metrics endpoint.

    Returns:
        Response with metrics in Prometheus text format
    """
    return await metrics_endpoint()


# Additional metadata endpoints
@app.get("/collections", tags=["Metadata"])
async def list_collections():
    """
    List all available collections in the database.

    Returns:
        Dictionary with collection names and their document counts
    """
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized",
        )

    try:
        collections = retriever.db.list_collections()
        stats = {}

        for coll_name in collections:
            try:
                collection = retriever.db.get_collection(coll_name)
                count = collection.count()
                stats[coll_name] = {"document_count": count, "name": coll_name}
            except Exception as e:
                logger.error(f"Error getting info for collection {coll_name}: {e}")
                stats[coll_name] = {"error": str(e)}

        return {"collections": collections, "stats": stats, "count": len(collections)}

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list collections",
        )


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=os.getenv("API_RELOAD", "false").lower() == "true",
        log_level=os.getenv("API_LOG_LEVEL", "info").lower(),
    )
