"""
Prometheus metrics and monitoring endpoints for the RAG API.

This module provides:
- Custom metrics for API performance tracking
- Metrics endpoint for Prometheus scraping
- Integration with FastAPI application

Metrics tracked:
- API request counts and latencies by endpoint and method
- Database query performance
- Embedding generation statistics
- RAG pipeline metrics
- System resource usage (if psutil available)
"""

import time
import logging
from typing import Optional, Dict, Any
from collections import defaultdict

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus-client not installed; metrics endpoint disabled")

logger = logging.getLogger(__name__)

# Define metrics if prometheus client is available
if PROMETHEUS_AVAILABLE:
    # API Request metrics
    API_REQUESTS_TOTAL = Counter(
        "rag_api_requests_total",
        "Total number of API requests",
        ["endpoint", "method", "status"],
    )

    API_REQUEST_DURATION = Histogram(
        "rag_api_request_duration_seconds",
        "API request duration in seconds",
        ["endpoint", "method"],
        buckets=(
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
            float("inf"),
        ),
    )

    # Database metrics
    DB_QUERY_DURATION = Histogram(
        "rag_db_query_duration_seconds",
        "Database query duration in seconds",
        ["operation", "collection"],
        buckets=(
            0.001,
            0.005,
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
        ),
    )

    DB_DOCUMENT_COUNT = Gauge(
        "rag_db_document_count", "Number of documents in collection", ["collection"]
    )

    # Embedding metrics
    EMBEDDING_REQUESTS_TOTAL = Counter(
        "rag_embedding_requests_total", "Total number of embedding generation requests"
    )

    EMBEDDING_DURATION = Histogram(
        "rag_embedding_duration_seconds",
        "Embedding generation duration in seconds",
        ["provider"],
        buckets=(
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
            15.0,
            30.0,
            float("inf"),
        ),
    )

    EMBEDDING_TOKENS_TOTAL = Counter(
        "rag_embedding_tokens_total", "Total number of tokens embedded"
    )

    # RAG Pipeline metrics
    RAG_QUERIES_TOTAL = Counter(
        "rag_rag_queries_total", "Total number of RAG queries", ["status"]
    )

    RAG_CONFIDENCE_SCORE = Gauge(
        "rag_rag_confidence_score", "Confidence score of last RAG query"
    )

    # System metrics (optional, if psutil available)
    try:
        import psutil

        SYSTEM_CPU_USAGE = Gauge(
            "rag_system_cpu_usage_percent", "System CPU usage percentage"
        )
        SYSTEM_MEMORY_USAGE = Gauge(
            "rag_system_memory_usage_bytes", "System memory usage in bytes"
        )
        PSUTIL_AVAILABLE = True
    except ImportError:
        PSUTIL_AVAILABLE = False
else:
    # Dummy metrics for when prometheus is not available
    class DummyMetric:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    API_REQUESTS_TOTAL = DummyMetric()
    API_REQUEST_DURATION = DummyMetric()
    DB_QUERY_DURATION = DummyMetric()
    DB_DOCUMENT_COUNT = DummyMetric()
    EMBEDDING_REQUESTS_TOTAL = DummyMetric()
    EMBEDDING_DURATION = DummyMetric()
    EMBEDDING_TOKENS_TOTAL = DummyMetric()
    RAG_QUERIES_TOTAL = DummyMetric()
    RAG_CONFIDENCE_SCORE = DummyMetric()


class MetricsMiddleware:
    """FastAPI middleware for automatic request metrics collection."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract endpoint and method
        path = scope.get("path", "/")
        method = scope.get("method", "GET")

        # Start timing
        start_time = time.time()

        # Capture response status
        status_code = "500"  # default error

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = str(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Record metrics
            duration = time.time() - start_time
            API_REQUEST_DURATION.labels(endpoint=path, method=method).observe(duration)
            API_REQUESTS_TOTAL.labels(
                endpoint=path, method=method, status=status_code
            ).inc()

            logger.debug(
                f"Metrics recorded: {method} {path} -> {status_code} in {duration:.3f}s"
            )


def update_db_metrics(collections_data: Dict[str, Dict[str, Any]]):
    """
    Update database metrics with current collection statistics.

    Args:
        collections_data: Dictionary mapping collection names to stats (must include 'document_count')
    """
    for collection_name, stats in collections_data.items():
        if isinstance(stats, dict) and "document_count" in stats:
            DB_DOCUMENT_COUNT.labels(collection=collection_name).set(
                stats["document_count"]
            )


def record_embedding_metrics(
    num_tokens: int, duration: float, provider: str = "openai"
):
    """
    Record embedding generation metrics.

    Args:
        num_tokens: Number of tokens embedded
        duration: Time taken in seconds
        provider: Embedding provider name (e.g., 'openai', 'sentence-transformers')
    """
    EMBEDDING_REQUESTS_TOTAL.inc()
    EMBEDDING_DURATION.labels(provider=provider).observe(duration)
    if num_tokens > 0:
        EMBEDDING_TOKENS_TOTAL.inc(num_tokens)


def record_rag_metrics(success: bool, confidence: Optional[float] = None):
    """
    Record RAG query metrics.

    Args:
        success: Whether the RAG query succeeded
        confidence: Confidence score if successful
    """
    status = "success" if success else "failure"
    RAG_QUERIES_TOTAL.labels(status=status).inc()
    if confidence is not None and success:
        RAG_CONFIDENCE_SCORE.set(confidence)


def update_system_metrics():
    """Update system resource usage metrics if psutil is available."""
    if not PSUTIL_AVAILABLE:
        return

    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.Process().memory_info()
        SYSTEM_CPU_USAGE.set(cpu_percent)
        SYSTEM_MEMORY_USAGE.set(memory_info.rss)  # Resident set size
    except Exception as e:
        logger.warning(f"Failed to update system metrics: {e}")


def get_metrics_response() -> bytes:
    """
    Generate Prometheus metrics response.

    Returns:
        Bytes containing metrics in Prometheus text format
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# prometheus-client not installed\n# Install with: pip install prometheus-client\n"

    try:
        metrics = generate_latest(REGISTRY)
        return metrics
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        return f"# Error generating metrics: {e}\n".encode()


async def metrics_endpoint():
    """
    FastAPI endpoint handler for /metrics.

    Returns:
        Response with Prometheus metrics
    """
    from fastapi.responses import Response

    # Update system metrics before generating output
    update_system_metrics()

    metrics_data = get_metrics_response()
    return Response(content=metrics_data, media_type="text/plain; version=0.0.4")


# Utility to reset metrics (useful for testing)
def reset_metrics():
    """Reset all metrics to initial state (for testing purposes)."""
    if not PROMETHEUS_AVAILABLE:
        return

    # Remove all metrics from registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)

    logger.info("All metrics reset")
