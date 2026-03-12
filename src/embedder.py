"""
Embedding generation module for RAG system.

This module handles:
- Batch embedding generation with progress tracking
- Support for OpenAI API and local sentence-transformers
- Rate limiting and retry logic for API calls
- Token usage tracking with tiktoken
- Configuration-driven model selection
"""

import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

import tiktoken
from dotenv import load_dotenv

# OpenAI
try:
    from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Local embeddings
try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Configuration
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""

    provider: str  # "openai" or "local"
    openai_model: str = "text-embedding-ada-002"
    openai_dimensions: int = 1536
    local_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_dimensions: int = 384
    local_device: str = "cpu"
    local_cache_folder: str = "models/embeddings"
    batch_size: int = 100
    max_retries: int = 3
    timeout: int = 30
    openai_api_key: Optional[str] = None


class TokenUsageTracker:
    """Track token usage for embedding generation."""

    def __init__(self):
        self.total_input_tokens = 0
        self.total_batches = 0
        self.total_documents = 0
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start tracking."""
        self.start_time = time.time()

    def add_batch(self, num_texts: int, num_tokens: int):
        """Record a batch."""
        self.total_batches += 1
        self.total_documents += num_texts
        self.total_input_tokens += num_tokens

    def stop(self):
        """Stop tracking."""
        self.end_time = time.time()

    def get_report(self) -> Dict[str, Any]:
        """Get usage report."""
        if self.start_time is None:
            return {}

        duration = (self.end_time or time.time()) - self.start_time
        tokens_per_second = self.total_input_tokens / duration if duration > 0 else 0
        docs_per_second = self.total_documents / duration if duration > 0 else 0

        return {
            "total_input_tokens": self.total_input_tokens,
            "total_batches": self.total_batches,
            "total_documents": self.total_documents,
            "duration_seconds": duration,
            "tokens_per_second": tokens_per_second,
            "docs_per_second": docs_per_second,
        }


class OpenAIEmbedder:
    """OpenAI API-based embedding generator."""

    def __init__(self, config: EmbeddingConfig):
        """
        Initialize OpenAI embedder.

        Args:
            config: EmbeddingConfig with provider="openai"
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not installed. Run: pip install openai")

        self.config = config
        self.api_key = config.openai_api_key or self._load_api_key()
        self.client = OpenAI(api_key=self.api_key, timeout=config.timeout)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.usage_tracker = TokenUsageTracker()

        logger.info(
            f"OpenAIEmbedder initialized with model: {config.openai_model}, "
            f"dimensions: {config.openai_dimensions}"
        )

    def _load_api_key(self) -> str:
        """Load OpenAI API key from environment."""
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment. Set it in .env file."
            )
        return api_key

    def _count_tokens(self, texts: List[str]) -> int:
        """Count tokens in a batch of texts."""
        total = 0
        for text in texts:
            total += len(self.tokenizer.encode(text))
        return total

    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text (for fallback)."""
        response = self.client.embeddings.create(
            model=self.config.openai_model,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is list of floats)
        """
        if not texts:
            return []

        # Count tokens before API call
        token_count = self._count_tokens(texts)

        # Retry logic
        for attempt in range(self.config.max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.config.openai_model,
                    input=texts,
                )
                break
            except RateLimitError as e:
                logger.warning(
                    f"Rate limit hit, retry {attempt + 1}/{self.config.max_retries}"
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep((2**attempt) + 1)  # Exponential backoff
                    continue
                raise
            except (APIConnectionError, APITimeoutError) as e:
                logger.warning(
                    f"API error: {e}, retry {attempt + 1}/{self.config.max_retries}"
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise

        # Extract embeddings
        embeddings = [item.embedding for item in response.data]

        # Track usage
        self.usage_tracker.add_batch(len(texts), token_count)
        logger.debug(f"Embedded {len(texts)} texts ({token_count} tokens)")

        return embeddings

    def get_usage_report(self) -> Dict[str, Any]:
        """Get token usage report."""
        return self.usage_tracker.get_report()


class LocalEmbedder:
    """Local sentence-transformers embedding generator."""

    def __init__(self, config: EmbeddingConfig):
        """
        Initialize local embedder.

        Args:
            config: EmbeddingConfig with provider="local"
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers package not installed. "
                "Run: pip install sentence-transformers"
            )

        self.config = config
        self.model = None
        self.device = config.local_device
        self.usage_tracker = TokenUsageTracker()

        logger.info(
            f"LocalEmbedder initializing with model: {config.local_model_name}, "
            f"device: {config.local_device}"
        )
        self._load_model()

    def _load_model(self):
        """Load the sentence-transformers model."""
        try:
            self.model = SentenceTransformer(
                self.config.local_model_name,
                cache_folder=self.config.local_cache_folder,
                device=self.device,
            )
            logger.info(
                f"Loaded model with dimension: {self.model.get_sentence_embedding_dimension()}"
            )
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is list of floats)
        """
        if not texts:
            return []

        # Simple token counting via tokenizer approximation
        token_count = sum(len(text.split()) for text in texts)

        # Generate embeddings
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=False,  # Returns list of lists
            show_progress_bar=False,
            batch_size=len(texts),  # All at once for local
        )

        # Convert to list of lists if numpy arrays
        if hasattr(embeddings[0], "tolist"):
            embeddings = [emb.tolist() for emb in embeddings]

        # Track usage
        self.usage_tracker.add_batch(len(texts), token_count)
        logger.debug(f"Embedded {len(texts)} texts ({token_count} tokens)")

        return embeddings

    def get_usage_report(self) -> Dict[str, Any]:
        """Get usage report."""
        return self.usage_tracker.get_report()


class Embedder:
    """
    Unified embedding generator supporting multiple providers.

    This class provides a single interface for generating embeddings,
    automatically selecting the appropriate backend (OpenAI or local)
    based on configuration.
    """

    def __init__(self, config_path: Union[str, Path] = "config/embeddings.yaml"):
        """
        Initialize embedder from configuration.

        Args:
            config_path: Path to embeddings configuration YAML file
        """
        self.config = self._load_config(config_path)
        self.provider = self._init_provider()
        self.usage_tracker = TokenUsageTracker()

    def _load_config(self, config_path: Union[str, Path]) -> EmbeddingConfig:
        """Load configuration from YAML file."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Load environment variables
        load_dotenv()

        # Extract OpenAI config
        openai_config = config_data.get("openai", {})
        local_config = config_data.get("local", {})

        return EmbeddingConfig(
            provider=config_data["provider"],
            openai_model=openai_config.get("model", "text-embedding-ada-002"),
            openai_dimensions=openai_config.get("dimensions", 1536),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            local_model_name=local_config.get(
                "model_name", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            local_dimensions=local_config.get("dimensions", 384),
            local_device=local_config.get("device", "cpu"),
            local_cache_folder=local_config.get("cache_folder", "models/embeddings"),
            batch_size=config_data.get("batch_size", 100),
            max_retries=config_data.get("max_retries", 3),
            timeout=config_data.get("timeout", 30),
        )

    def _init_provider(self):
        """Initialize the appropriate embedding provider."""
        if self.config.provider == "openai":
            return OpenAIEmbedder(self.config)
        elif self.config.provider == "local":
            return LocalEmbedder(self.config)
        else:
            raise ValueError(
                f"Invalid provider: {self.config.provider}. Must be 'openai' or 'local'"
            )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self.usage_tracker.start()
        try:
            embeddings = self.provider.embed_batch(texts)
            return embeddings
        finally:
            self.usage_tracker.stop()

    def embed_batch(
        self, texts: List[str], batch_size: Optional[int] = None
    ) -> List[List[float]]:
        """
        Generate embeddings with batch processing.

        Args:
            texts: List of text strings to embed
            batch_size: Override batch size (uses config if None)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        batch_size = batch_size or self.config.batch_size
        all_embeddings = []

        self.usage_tracker.start()

        try:
            # Process in batches
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_embeddings = self.provider.embed_batch(batch)
                all_embeddings.extend(batch_embeddings)

                # Progress logging
                if (i // batch_size + 1) % 10 == 0:
                    logger.info(
                        f"Embedded {i + len(batch)}/{len(texts)} documents "
                        f"({(i + len(batch)) / len(texts) * 100:.1f}%)"
                    )

            return all_embeddings
        finally:
            self.usage_tracker.stop()

    def get_usage_report(self) -> Dict[str, Any]:
        """Get embedding usage report."""
        return self.provider.get_usage_report()

    def get_dimensions(self) -> int:
        """Get embedding dimensions for the current provider."""
        if self.config.provider == "openai":
            return self.config.openai_dimensions
        else:
            return self.config.local_dimensions


def generate_embeddings(
    texts: List[str], config_path: Union[str, Path] = "config/embeddings.yaml"
) -> List[List[float]]:
    """
    Convenience function to generate embeddings.

    Args:
        texts: List of texts to embed
        config_path: Path to embedding configuration

    Returns:
        List of embedding vectors
    """
    embedder = Embedder(config_path)
    return embedder.embed_batch(texts)


def batch_embed(
    chunks: List[Dict[str, Any]],
    batch_size: int = 100,
    config_path: Union[str, Path] = "config/embeddings.yaml",
) -> List[List[float]]:
    """
    Batch embed a list of chunk documents.

    Args:
        chunks: List of chunk dictionaries with 'text' and 'metadata'
        batch_size: Number of texts to process per batch
        config_path: Path to embedding configuration

    Returns:
        List of embedding vectors
    """
    texts = [chunk["text"] for chunk in chunks]
    embedder = Embedder(config_path)
    return embedder.embed_batch(texts, batch_size=batch_size)


if __name__ == "__main__":
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Test embedding generation
    test_texts = [
        "This is a test document about artificial intelligence.",
        "Machine learning models can process natural language.",
        "Vector databases enable efficient similarity search.",
    ]

    logger.info("Testing embedding generation...")
    try:
        embedder = Embedder()
        embeddings = embedder.embed_batch(test_texts)

        logger.info(f"Generated {len(embeddings)} embeddings")
        logger.info(f"Embedding dimensions: {len(embeddings[0])}")
        logger.info(f"Usage: {embedder.get_usage_report()}")
    except Exception as e:
        logger.error(f"Embedding test failed: {e}")
        raise
