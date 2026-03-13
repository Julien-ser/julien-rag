#!/usr/bin/env python3
"""
Database Validation and Optimization Script

This script performs comprehensive validation of the vector database:
- Data integrity checks
- Performance benchmarks (latency, throughput)
- Recall@k tests with known queries
- Index optimization recommendations
- Storage analysis

Usage:
    python scripts/validate_db.py [--db-dir DIR] [--output REPORT.json] [--benchmark]

Options:
    --db-dir DIR       Database directory (default: data/vector_db)
    --output FILE      Output report file (default: database_validation_report.json)
    --benchmark N      Number of benchmark queries to run (default: 100)
    --test-recall      Run recall@k tests (requires test data)
    --verbose          Enable verbose logging
"""

import argparse
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database import VectorDatabase, init_database
from retriever import Retriever, SearchResult
from embedder import Embedder
import chromadb

logger = logging.getLogger(__name__)


class DatabaseValidator:
    """Comprehensive database validation and benchmarking tool."""

    def __init__(
        self,
        persist_directory: Union[str, Path] = "data/vector_db",
        embedder: Optional[Embedder] = None,
    ):
        """
        Initialize validator.

        Args:
            persist_directory: ChromaDB directory
            embedder: Optional embedder instance (creates default if None)
        """
        self.persist_directory = Path(persist_directory)
        self.db = None
        self.retriever = None
        self.embedder = embedder
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "database_path": str(self.persist_directory),
            "validation": {},
            "performance": {},
            "recommendations": [],
        }

    def initialize(self) -> None:
        """Initialize database and retriever connections."""
        logger.info(f"Initializing validator for database: {self.persist_directory}")

        # Initialize database
        self.db = init_database(persist_directory=self.persist_directory)

        # Initialize embedder if not provided
        if self.embedder is None:
            try:
                self.embedder = Embedder()
            except Exception as e:
                logger.warning(f"Could not initialize embedder: {e}")
                logger.warning("Some tests requiring embeddings will be skipped")

        # Initialize retriever
        self.retriever = Retriever(
            persist_directory=self.persist_directory,
            embedder=self.embedder,
        )

        logger.info("Validator initialized successfully")

    def check_data_integrity(self) -> Dict[str, Any]:
        """
        Validate data integrity in all collections.

        Checks:
        - Collection existence
        - Document counts
        - Metadata completeness
        - Embedding dimensions consistency
        """
        logger.info("Starting data integrity checks...")

        integrity = {
            "collections_checked": [],
            "total_documents": 0,
            "collections_with_data": 0,
            "embedding_dimensions": {},
            "metadata_issues": [],
            "errors": [],
        }

        try:
            collections = self.db.list_collections()
            logger.info(f"Found {len(collections)} collections: {collections}")

            for coll_name in collections:
                try:
                    collection = self.db.get_collection(coll_name)
                    count = collection.count()
                    integrity["collections_checked"].append(coll_name)
                    integrity["total_documents"] += count

                    if count > 0:
                        integrity["collections_with_data"] += 1

                        # Sample documents to check embedding dimensions
                        sample = collection.get(
                            limit=min(10, count),
                            include=["embeddings", "metadatas"],
                        )

                        if sample["embeddings"] and len(sample["embeddings"]) > 0:
                            dim = len(sample["embeddings"][0])
                            integrity["embedding_dimensions"][coll_name] = dim
                            logger.debug(
                                f"Collection {coll_name}: embedding dimension = {dim}"
                            )

                            # Check for consistent dimensions
                            dims = [len(emb) for emb in sample["embeddings"]]
                            if len(set(dims)) > 1:
                                integrity["errors"].append(
                                    f"Collection {coll_name} has inconsistent embedding dimensions"
                                )

                        # Check metadata completeness
                        for i, meta in enumerate(sample["metadatas"]):
                            if not isinstance(meta, dict):
                                integrity["metadata_issues"].append(
                                    f"{coll_name}: sample {i} has non-dict metadata"
                                )
                                continue

                            # Check required fields
                            required = ["chunk_id", "source"]
                            for field in required:
                                if field not in meta:
                                    integrity["metadata_issues"].append(
                                        f"{coll_name}: sample {i} missing '{field}'"
                                    )

                    logger.info(f"Collection {coll_name}: {count} documents, OK")

                except Exception as e:
                    logger.error(f"Error checking collection {coll_name}: {e}")
                    integrity["errors"].append(f"{coll_name}: {str(e)}")

        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            integrity["errors"].append(f"Failed to list collections: {str(e)}")

        logger.info(
            f"Data integrity check complete: "
            f"{integrity['total_documents']} documents across {integrity['collections_with_data']} collections"
        )

        return integrity

    def measure_storage_size(self) -> Dict[str, Any]:
        """
        Calculate database storage size on disk.

        Returns:
            Dictionary with size information in bytes and human-readable format
        """
        logger.info("Measuring storage size...")

        size_info = {
            "db_directory": str(self.persist_directory),
            "total_size_bytes": 0,
            "files": {},
        }

        try:
            db_path = self.persist_directory
            if db_path.exists():
                total = 0
                for file_path in db_path.rglob("*"):
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        total += size
                        size_info["files"][file_path.name] = size

                size_info["total_size_bytes"] = total
                size_info["total_size_human"] = self._bytes_to_human(total)

                logger.info(f"Total database size: {self._bytes_to_human(total)}")

        except Exception as e:
            logger.error(f"Error measuring storage: {e}")
            size_info["error"] = str(e)

        return size_info

    def _bytes_to_human(self, bytes_size: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"

    def benchmark_query_latency(
        self, num_queries: int = 100, k_values: List[int] = [5, 10, 20]
    ) -> Dict[str, Any]:
        """
        Measure query latency distribution.

        Args:
            num_queries: Number of queries to run
            k_values: List of k values to test

        Returns:
            Dictionary with latency statistics for each k
        """
        logger.info(f"Running query latency benchmark ({num_queries} queries)...")

        benchmark = {
            "num_queries": num_queries,
            "queries_per_second": 0,
            "by_k": {},
        }

        # Use a set of test queries
        test_queries = [
            "machine learning",
            "python programming",
            "data science",
            "web development",
            "database optimization",
            "API design",
            "git version control",
            "Docker containers",
            "testing frameworks",
            "cloud computing",
        ]

        if self.retriever is None or self.embedder is None:
            logger.warning("Retriever or embedder not available, skipping benchmark")
            benchmark["error"] = "Retriever/embedder not available"
            return benchmark

        for k in k_values:
            logger.info(f"Benchmarking with k={k}...")
            latencies = []

            for i in range(num_queries):
                query = test_queries[i % len(test_queries)]

                try:
                    start = time.perf_counter()
                    results = self.retriever.search(query, k=k)
                    elapsed = time.perf_counter() - start
                    latencies.append(elapsed)
                except Exception as e:
                    logger.warning(f"Query {i} failed: {e}")
                    continue

            if latencies:
                stats = self._calculate_statistics(latencies)
                benchmark["by_k"][k] = stats
                logger.info(
                    f"k={k}: avg={stats['mean']:.3f}s, "
                    f"p95={stats['p95']:.3f}s, p99={stats['p99']:.3f}s"
                )

        # Overall QPS
        if latencies:
            total_time = sum(latencies)
            benchmark["queries_per_second"] = (
                len(latencies) / total_time if total_time > 0 else 0
            )

        return benchmark

    def _calculate_statistics(self, values: List[float]) -> Dict[str, float]:
        """Calculate statistical measures."""
        if not values:
            return {}

        sorted_vals = sorted(values)
        n = len(values)

        return {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
            "p50": sorted_vals[int(n * 0.50)],
            "p90": sorted_vals[int(n * 0.90)],
            "p95": sorted_vals[int(n * 0.95)],
            "p99": sorted_vals[int(n * 0.99)],
        }

    def test_recall_at_k(
        self, test_cases: List[Dict[str, Any]], k_values: List[int] = [1, 5, 10, 20]
    ) -> Dict[str, Any]:
        """
        Test recall@k using known query-document relevance pairs.

        Args:
            test_cases: List of dicts with 'query' and 'relevant_ids' (set of chunk_ids)
            k_values: List of k values to evaluate

        Returns:
            Dictionary with recall@k metrics
        """
        logger.info("Running recall@k tests...")

        recall_results = {
            "test_cases": len(test_cases),
            "by_k": {},
        }

        if not test_cases:
            logger.warning("No test cases provided for recall@k")
            recall_results["error"] = "No test cases"
            return recall_results

        if self.retriever is None:
            logger.warning("Retriever not available, skipping recall@k")
            recall_results["error"] = "Retriever not available"
            return recall_results

        for k in k_values:
            recalls = []

            for test_case in test_cases:
                query = test_case["query"]
                relevant_ids = set(test_case.get("relevant_ids", []))

                if not relevant_ids:
                    continue

                try:
                    results = self.retriever.search(query, k=k)
                    retrieved_ids = set(
                        meta.get("chunk_id")
                        for meta in results.metadatas
                        if "chunk_id" in meta
                    )

                    # Calculate recall
                    if relevant_ids:
                        intersection = relevant_ids.intersection(retrieved_ids)
                        recall = len(intersection) / len(relevant_ids)
                        recalls.append(recall)

                except Exception as e:
                    logger.warning(f"Recall test query failed: {e}")
                    continue

            if recalls:
                avg_recall = statistics.mean(recalls)
                recall_results["by_k"][k] = {
                    "average_recall": avg_recall,
                    "num_queries": len(recalls),
                    "min_recall": min(recalls),
                    "max_recall": max(recalls),
                }
                logger.info(
                    f"Recall@{k}: {avg_recall:.4f} (avg over {len(recalls)} queries)"
                )

        return recall_results

    def test_metadata_filtering(self) -> Dict[str, Any]:
        """
        Test metadata filtering performance and correctness.

        Returns:
            Dictionary with filtering test results
        """
        logger.info("Testing metadata filtering...")

        filter_tests = {
            "total_tests": 0,
            "passed": 0,
            "by_type": {},
        }

        if self.retriever is None:
            filter_tests["error"] = "Retriever not available"
            return filter_tests

        # Get available sources from database
        try:
            stats = self.retriever.get_collection_stats()
            sources = set()

            # Sample to discover available sources
            for coll_name in ["github_docs", "web_content"]:
                try:
                    collection = self.db.get_collection(coll_name)
                    sample = collection.get(limit=100, include=["metadatas"])
                    for meta in sample["metadatas"]:
                        if "source" in meta:
                            sources.add(meta["source"])
                except:
                    pass

            if not sources:
                logger.warning("No sources found to test filtering")
                filter_tests["error"] = "No data to test filtering"
                return filter_tests

            # Test source filtering for each source
            for source in sources:
                test_query = "test"
                filter_tests["total_tests"] += 1

                try:
                    results = self.retriever.search(
                        test_query, k=50, filters={"source": source}
                    )

                    # Check all results match filter
                    all_match = all(
                        meta.get("source") == source for meta in results.metadatas
                    )

                    filter_tests["by_type"][f"source:{source}"] = {
                        "passed": all_match,
                        "results_count": len(results),
                        "execution_time": results.query_time,
                    }

                    if all_match:
                        filter_tests["passed"] += 1

                except Exception as e:
                    logger.warning(f"Filter test failed for source {source}: {e}")
                    filter_tests["by_type"][f"source:{source}"] = {
                        "passed": False,
                        "error": str(e),
                    }

        except Exception as e:
            logger.error(f"Metadata filtering test failed: {e}")
            filter_tests["error"] = str(e)

        logger.info(
            f"Metadata filtering: {filter_tests['passed']}/{filter_tests['total_tests']} tests passed"
        )

        return filter_tests

    def generate_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate optimization recommendations based on validation results.

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        # Check document count
        total_docs = self.report["validation"].get("total_documents", 0)

        if total_docs == 0:
            recommendations.append(
                {
                    "severity": "high",
                    "category": "data",
                    "message": "Database is empty. Run the ingestion pipeline to populate it.",
                    "action": "Run: python -m src.pipeline or ./scripts/ingest_all.sh",
                }
            )

        # Check embedding dimensions consistency
        dims = self.report["validation"].get("embedding_dimensions", {})
        if len(set(dims.values())) > 1:
            recommendations.append(
                {
                    "severity": "high",
                    "category": "data",
                    "message": "Inconsistent embedding dimensions across collections.",
                    "action": "Re-embed all documents with a single embedding model.",
                }
            )

        # Check for metadata issues
        metadata_issues = len(self.report["validation"].get("metadata_issues", []))
        if metadata_issues > 0:
            recommendations.append(
                {
                    "severity": "medium",
                    "category": "data",
                    "message": f"Found {metadata_issues} metadata issues.",
                    "action": "Review and fix metadata schema in preprocessing pipeline.",
                }
            )

        # Performance recommendations
        perf = self.report["performance"].get("by_k", {})
        if perf:
            # Check latency for k=10
            stats = perf.get(10, {})
            if stats.get("p95", 0) > 1.0:
                recommendations.append(
                    {
                        "severity": "medium",
                        "category": "performance",
                        "message": f"95th percentile latency ({stats['p95']:.3f}s) is high.",
                        "action": "Consider reducing chunk size or optimizing embedding model.",
                    }
                )

            if stats.get("mean", 0) > 0.5:
                recommendations.append(
                    {
                        "severity": "low",
                        "category": "performance",
                        "message": f"Average latency ({stats['mean']:.3f}s) could be improved.",
                        "action": "Consider using a faster embedding model or local embeddings.",
                    }
                )

        # Storage recommendations
        storage_bytes = self.report["performance"].get("storage_size_bytes", 0)
        if storage_bytes > 1e9:  # > 1GB
            recommendations.append(
                {
                    "severity": "low",
                    "category": "storage",
                    "message": f"Database size ({self._bytes_to_human(storage_bytes)}) is large.",
                    "action": "Consider archiving old data or implementing TTL policies.",
                }
            )

        return recommendations

    def run_full_validation(
        self,
        num_benchmark_queries: int = 100,
        run_recall_tests: bool = False,
        test_cases: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run complete validation suite.

        Args:
            num_benchmark_queries: Number of queries for latency benchmark
            run_recall_tests: Whether to run recall@k tests
            test_cases: Test cases for recall@k (list of {'query': ..., 'relevant_ids': ...})

        Returns:
            Complete validation report dictionary
        """
        logger.info("Starting full database validation...")

        try:
            # 1. Data integrity
            self.report["validation"] = self.check_data_integrity()

            # 2. Storage size
            self.report["performance"]["storage_size"] = self.measure_storage_size()
            self.report["performance"]["storage_size_bytes"] = self.report[
                "performance"
            ]["storage_size"].get("total_size_bytes", 0)

            # 3. Query latency benchmark
            self.report["performance"]["latency_benchmark"] = (
                self.benchmark_query_latency(num_queries=num_benchmark_queries)
            )

            # 4. Metadata filtering tests
            self.report["validation"]["filtering_tests"] = (
                self.test_metadata_filtering()
            )

            # 5. Recall@k tests (optional)
            if run_recall_tests and test_cases:
                self.report["validation"]["recall_at_k"] = self.test_recall_at_k(
                    test_cases
                )

            # 6. Generate recommendations
            self.report["recommendations"] = self.generate_recommendations()

            logger.info("Validation complete")
            return self.report

        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            self.report["error"] = str(e)
            return self.report

    def save_report(self, output_path: Union[str, Path]) -> None:
        """Save validation report to JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.report, f, indent=2)

        logger.info(f"Validation report saved to: {output_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Database validation and optimization tool"
    )
    parser.add_argument(
        "--db-dir",
        default="data/vector_db",
        help="ChromaDB directory (default: data/vector_db)",
    )
    parser.add_argument(
        "--output",
        default="database_validation_report.json",
        help="Output report file (default: database_validation_report.json)",
    )
    parser.add_argument(
        "--benchmark",
        type=int,
        default=100,
        help="Number of benchmark queries (default: 100)",
    )
    parser.add_argument(
        "--test-recall",
        action="store_true",
        help="Run recall@k tests (requires test data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelno)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load test cases if recall test requested
    test_cases = []
    if args.test_recall:
        # Try to load test cases from data/processed/ or create from sample data
        test_cases_file = Path("data/processed/test_recall_cases.json")
        if test_cases_file.exists():
            with open(test_cases_file) as f:
                test_cases = json.load(f)
            logger.info(f"Loaded {len(test_cases)} recall test cases")
        else:
            logger.warning(
                "No test_recall_cases.json found, recall@k tests will be skipped"
            )

    try:
        # Initialize validator
        validator = DatabaseValidator(persist_directory=args.db_dir)
        validator.initialize()

        # Run validation
        report = validator.run_full_validation(
            num_benchmark_queries=args.benchmark,
            run_recall_tests=args.test_recall and len(test_cases) > 0,
            test_cases=test_cases,
        )

        # Print summary
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Database: {args.db_dir}")
        print(f"Total documents: {report['validation'].get('total_documents', 0)}")
        print(
            f"Collections: {', '.join(report['validation'].get('collections_checked', []))}"
        )

        perf = report.get("performance", {}).get("latency_benchmark", {})
        if "by_k" in perf and 10 in perf["by_k"]:
            stats = perf["by_k"][10]
            print(f"Latency (k=10): avg={stats['mean']:.3f}s, p95={stats['p95']:.3f}s")

        print(f"\nRecommendations: {len(report.get('recommendations', []))}")
        for i, rec in enumerate(report.get("recommendations", []), 1):
            print(f"  {i}. [{rec['severity'].upper()}] {rec['message']}")

        print(f"\nFull report: {args.output}")
        print("=" * 60)

        # Save report
        validator.save_report(args.output)

        # Exit with appropriate code
        if report.get("error") or len(report.get("recommendations", [])) > 0:
            sys.exit(1 if report.get("error") else 0)

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
