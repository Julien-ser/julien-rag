"""
Data models for Julien RAG SDK.

This module provides Pydantic models for request/response types
used in the RAG client library.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator


class SearchRequest(BaseModel):
    """Request model for search operation."""

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


class SearchResponse(BaseModel):
    """Response model for search results."""

    documents: List[str]
    metadatas: List[Dict[str, Any]]
    scores: List[float]
    collection: str
    query_time: float
    total_results: int

    @validator("scores")
    def scores_must_be_valid(cls, v):
        """Validate scores are between 0 and 1."""
        for score in v:
            if not 0 <= score <= 1:
                raise ValueError(f"Score {score} is out of range [0, 1]")
        return v

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


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    timestamp: datetime
    reason: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {"status": "healthy", "timestamp": "2024-01-15T10:30:00"}
        }
