"""
Unified data ingestion pipeline for RAG system.

This module orchestrates the complete data pipeline:
1. Data collection from GitHub and web sources
2. Document preprocessing and chunking
3. Progress tracking and error handling
4. Comprehensive logging

Features:
- Retry logic for API calls with exponential backoff
- Incremental updates based on file modification times
- Detailed statistics and reporting
- Graceful degradation on failures
"""

import os
import sys
import json
import time
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import project modules
from src.github_collector import GitHubCollector, run_all as github_run_all
from src.web_scraper import WebScraper, run_all as web_run_all
from src.preprocessor import process_all_raw_files, Preprocessor

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for pipeline execution."""

    start_time: datetime
    end_time: Optional[datetime] = None

    # Collection stats
    github_files_collected: int = 0
    web_files_collected: int = 0
    collection_errors: int = 0

    # Processing stats
    files_processed: int = 0
    chunks_generated: int = 0
    processing_errors: int = 0

    # Incremental stats
    skipped_files: int = 0

    def duration(self) -> timedelta:
        """Get total duration."""
        end = self.end_time or datetime.utcnow()
        return end - self.start_time

    def summary(self) -> str:
        """Generate summary string."""
        duration = self.duration()
        summary_lines = [
            "=== Pipeline Execution Summary ===",
            f"Total duration: {duration}",
            f"Start: {self.start_time.isoformat()}",
            f"End: {self.end_time.isoformat() if self.end_time else 'N/A'}",
            "",
            "Collection:",
            f"  GitHub files: {self.github_files_collected}",
            f"  Web files: {self.web_files_collected}",
            f"  Collection errors: {self.collection_errors}",
            "",
            "Processing:",
            f"  Files processed: {self.files_processed}",
            f"  Chunks generated: {self.chunks_generated}",
            f"  Processing errors: {self.processing_errors}",
            f"  Files skipped (incremental): {self.skipped_files}",
            "",
            "Total errors: " + str(self.collection_errors + self.processing_errors),
        ]
        return "\n".join(summary_lines)


class RetryHandler:
    """Handles retry logic with exponential backoff."""

    def __init__(
        self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0
    ):
        """
        Initialize retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay between retries
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute_with_retry(self, func, *args, **kwargs):
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            Exception: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed for {func.__name__}: {e}"
                    )
                    raise last_exception


class IncrementalUpdater:
    """Handles incremental updates based on file modification times."""

    def __init__(
        self, raw_dir: str = "data/raw", processed_dir: str = "data/processed"
    ):
        """
        Initialize incremental updater.

        Args:
            raw_dir: Directory containing raw data files
            processed_dir: Directory containing processed chunk files
        """
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)

        # Track last successful run
        self.state_file = self.processed_dir / ".pipeline_state.json"
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load pipeline state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}. Starting fresh.")

        return {"last_run": None, "processed_files": {}}

    def _save_state(self):
        """Save pipeline state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")

    def get_files_to_process(self, pattern: str = "*.json") -> List[Path]:
        """
        Determine which raw files need processing based on modification time.

        Args:
            pattern: Glob pattern for raw files

        Returns:
            List of raw file paths that need processing
        """
        files_to_process = []

        for raw_file in self.raw_dir.glob(pattern):
            # Skip manifest/state files
            if raw_file.name.startswith("."):
                continue

            # Check if processed output exists and is newer than raw file
            processed_marker = self.processed_dir / f"{raw_file.stem}_chunks.jsonl"

            raw_mtime = raw_file.stat().st_mtime
            processed_mtime = (
                processed_marker.stat().st_mtime if processed_marker.exists() else 0
            )

            # Check if file is new or modified since last processing
            raw_file_str = str(raw_file)
            last_processed = self.state.get("processed_files", {}).get(raw_file_str, 0)

            if raw_mtime > max(processed_mtime, last_processed):
                files_to_process.append(raw_file)
                logger.debug(f"File needs processing: {raw_file}")
            else:
                logger.debug(f"File up-to-date: {raw_file}")

        return files_to_process

    def mark_processed(self, raw_files: List[Path]):
        """
        Mark files as processed in state.

        Args:
            raw_files: List of raw file paths that were processed
        """
        now = time.time()
        for raw_file in raw_files:
            raw_file_str = str(raw_file)
            if "processed_files" not in self.state:
                self.state["processed_files"] = {}
            self.state["processed_files"][raw_file_str] = now

        self.state["last_run"] = now
        self._save_state()

    def should_skip_collection(
        self, collection_type: str, source_name: str = None
    ) -> bool:
        """
        Determine if a collection step should be skipped (incremental mode).

        Args:
            collection_type: Type of collection ('github', 'web')
            source_name: Specific source name

        Returns:
            True if collection can be skipped
        """
        # For now, conservative approach: always collect fresh data
        # Could be enhanced with timestamp tracking similar to file processing
        return False


def setup_logging(
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure comprehensive logging with rotation.

    Args:
        log_dir: Directory for log files
        log_level: Logging level
        max_bytes: Maximum bytes per log file before rotation
        backup_count: Number of backup files to keep

    Returns:
        Root logger
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate log filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"ingestion_{timestamp}.log"

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")
    return root_logger


def collect_github_data(
    config: Dict[str, Any], retry_handler: RetryHandler, stats: PipelineStats
) -> List[Path]:
    """
    Collect data from GitHub.

    Args:
        config: Configuration dictionary with collection parameters
        retry_handler: Retry logic handler
        stats: Statistics tracker

    Returns:
        List of output file paths
    """
    logger.info("=== Starting GitHub data collection ===")

    try:
        # Run GitHub collection
        output_files = retry_handler.execute_with_retry(
            github_run_all,
            token=config.get("github_token"),
            output_dir=config.get("raw_dir", "data/raw"),
            repos_limit=config.get("repos_limit"),
            commits_limit_per_repo=config.get("commits_limit_per_repo", 50),
            issues_limit_per_repo=config.get("issues_limit_per_repo", 50),
            gists_limit=config.get("gists_limit"),
            starred_limit=config.get("starred_limit"),
        )

        stats.github_files_collected = len(output_files)
        logger.info(f"GitHub collection complete: {len(output_files)} files")
        return (
            list(output_files.values())
            if isinstance(output_files, dict)
            else output_files
        )

    except Exception as e:
        logger.error(f"GitHub collection failed: {e}")
        stats.collection_errors += 1
        return []


def collect_web_data(
    config: Dict[str, Any], retry_handler: RetryHandler, stats: PipelineStats
) -> List[Path]:
    """
    Collect data from web sources.

    Args:
        config: Configuration dictionary with scraper config
        retry_handler: Retry logic handler
        stats: Statistics tracker

    Returns:
        List of output file paths
    """
    logger.info("=== Starting web data collection ===")

    try:
        # Get web scrape configuration
        web_config = config.get("web_scrape_config", {})
        output_dir = config.get("raw_dir", "data/raw")

        if not web_config:
            logger.warning(
                "No web scrape configuration provided. Skipping web collection."
            )
            return []

        # Run web scraping
        results = retry_handler.execute_with_retry(
            web_run_all,
            config=web_config,
            output_dir=output_dir,
            use_selenium=config.get("use_selenium", False),
            selenium_options=config.get("selenium_options", {}),
        )

        # The web_run_all saves files, so we need to find what was created
        # For now, assume it created a file with timestamp
        raw_dir = Path(output_dir)
        # Look for latest web_scraped_*.json file
        web_files = list(raw_dir.glob("web_scraped_*.json"))
        if web_files:
            # Sort by modification time, get latest
            latest_file = max(web_files, key=lambda p: p.stat().st_mtime)
            stats.web_files_collected = 1
            logger.info(f"Web collection complete: {latest_file}")
            return [latest_file]

        return []

    except Exception as e:
        logger.error(f"Web collection failed: {e}")
        stats.collection_errors += 1
        return []


def process_chunks(
    raw_files: List[Path],
    config: Dict[str, Any],
    incremental_updater: IncrementalUpdater,
    stats: PipelineStats,
) -> List[Path]:
    """
    Process raw files into chunks.

    Args:
        raw_files: List of raw data file paths (from collection or existing)
        config: Configuration with preprocessing parameters
        incremental_updater: Incremental update handler
        stats: Statistics tracker

    Returns:
        List of output chunk file paths
    """
    logger.info("=== Starting document processing ===")

    # If no raw files from collection, try to discover existing ones
    if not raw_files:
        logger.info("No raw files from collection. Checking for existing raw data...")
        raw_dir = Path(config.get("raw_dir", "data/raw"))
        raw_files = list(raw_dir.glob("*.json"))
        # Filter out state files and duplicates
        raw_files = [f for f in raw_files if not f.name.startswith(".")]
        if raw_files:
            logger.info(f"Found {len(raw_files)} existing raw files to process")

    # Determine which files need processing (incremental)
    if config.get("incremental", True):
        files_to_process = incremental_updater.get_files_to_process()
    else:
        files_to_process = raw_files

    if not files_to_process:
        logger.info("No files need processing (all up-to-date)")
        stats.skipped_files = len(raw_files) if raw_files else 0
        return []

    logger.info(f"Processing {len(files_to_process)} files")

    processed_files = []
    preprocessor = Preprocessor(
        chunk_size=config.get("chunk_size", 512),
        chunk_overlap=config.get("chunk_overlap", 100),
        min_chunk_size=config.get("min_chunk_size", 100),
        max_chunk_size=config.get("max_chunk_size", 768),
        output_dir=config.get("processed_dir", "data/processed"),
    )

    for raw_file in files_to_process:
        try:
            logger.info(f"Processing {raw_file}")

            # Determine source type from filename
            filename = raw_file.stem

            if "github_" in filename:
                source_type = filename.replace("github_", "").rstrip("s")
                if source_type == "repos":
                    source_type = "github_repos"
                elif source_type == "commits":
                    source_type = "github_commits"
                elif source_type == "issues":
                    source_type = "github_issues"
                elif source_type == "gists":
                    source_type = "github_gists"
                elif source_type == "starred":
                    source_type = "github_starred"
                else:
                    source_type = f"github_{source_type}"
            elif "web_" in filename:
                source_type = filename
            else:
                logger.warning(f"Unknown source type for {filename}, skipping")
                stats.processing_errors += 1
                continue

            # Process the file
            output_path = preprocessor.process_file(
                input_path=raw_file,
                source_type=source_type,
                output_filename=f"{raw_file.stem}_chunks.jsonl",
            )

            processed_files.append(output_path)
            stats.files_processed += 1

            # Count chunks
            with open(output_path, "r") as f:
                chunk_count = sum(1 for _ in f)
            stats.chunks_generated += chunk_count

            logger.info(f"Generated {chunk_count} chunks from {raw_file}")

        except Exception as e:
            logger.error(f"Failed to process {raw_file}: {e}")
            stats.processing_errors += 1
            continue

    # Mark processed files for incremental updates
    incremental_updater.mark_processed(files_to_process)

    logger.info(
        f"Processing complete: {len(processed_files)} files, {stats.chunks_generated} total chunks"
    )
    return processed_files


def run_pipeline(config_path: Optional[str] = None) -> PipelineStats:
    """
    Main pipeline orchestration function.

    Args:
        config_path: Optional path to configuration file (JSON)

    Returns:
        PipelineStats object with execution statistics
    """
    logger.info("Starting unified data ingestion pipeline")

    # Initialize stats
    stats = PipelineStats(start_time=datetime.utcnow())

    # Load configuration
    config = {}
    if config_path:
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            config = {}

    # Set default configuration
    config.setdefault("raw_dir", "data/raw")
    config.setdefault("processed_dir", "data/processed")
    config.setdefault("logs_dir", "logs")
    config.setdefault("incremental", True)
    config.setdefault("chunk_size", 512)
    config.setdefault("chunk_overlap", 100)
    config.setdefault("min_chunk_size", 100)
    config.setdefault("max_chunk_size", 768)
    config.setdefault("github_token", os.getenv("GITHUB_TOKEN"))
    config.setdefault("max_retries", 3)

    # Setup retry handler
    retry_handler = RetryHandler(max_retries=config["max_retries"])

    # Setup incremental updater
    incremental_updater = IncrementalUpdater(
        raw_dir=config["raw_dir"], processed_dir=config["processed_dir"]
    )

    try:
        # Step 1: Collect GitHub data
        github_files = collect_github_data(config, retry_handler, stats)

        # Step 2: Collect web data
        web_files = collect_web_data(config, retry_handler, stats)

        # Combine all raw files
        all_raw_files = github_files + web_files

        if not all_raw_files:
            logger.warning("No raw data files collected. Pipeline may have no input.")

        # Step 3: Process into chunks
        processed_files = process_chunks(
            all_raw_files, config, incremental_updater, stats
        )

        # Finalize stats
        stats.end_time = datetime.utcnow()

        # Log summary
        logger.info("\n" + stats.summary())

        # Save stats to file
        stats_file = Path(config["processed_dir"]) / "pipeline_stats.json"
        try:
            stats_file.parent.mkdir(parents=True, exist_ok=True)
            with open(stats_file, "w") as f:
                json.dump(asdict(stats), f, indent=2, default=str)
            logger.info(f"Statistics saved to {stats_file}")
        except Exception as e:
            logger.warning(f"Failed to save statistics: {e}")

        return stats

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        stats.end_time = datetime.utcnow()
        return stats
    except Exception as e:
        logger.error(f"Pipeline failed with unexpected error: {e}", exc_info=True)
        stats.end_time = datetime.utcnow()
        raise


def main():
    """Main entry point for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Unified data ingestion pipeline for RAG system"
    )
    parser.add_argument("--config", "-c", help="Path to configuration file (JSON)")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = getattr(logging, args.log_level)
    setup_logging(log_level=log_level)

    try:
        # Run pipeline
        stats = run_pipeline(config_path=args.config)

        # Exit with appropriate code
        total_errors = stats.collection_errors + stats.processing_errors
        if total_errors > 0:
            logger.warning(f"Pipeline completed with {total_errors} errors")
            sys.exit(1)
        else:
            logger.info("Pipeline completed successfully")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
