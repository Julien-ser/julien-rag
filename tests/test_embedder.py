"""
Unit tests for embedder module.

Tests:
- Embedder initialization from config
- OpenAI embedder mock tests
- Local embedder tests
- Batch embedding with progress tracking
- Token usage tracking
- Error handling and retries
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
from pathlib import Path
import logging

from src.embedder import (
    EmbeddingConfig,
    TokenUsageTracker,
    OpenAIEmbedder,
    LocalEmbedder,
    Embedder,
    generate_embeddings,
    batch_embed,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    OPENAI_AVAILABLE,
)


class TestTokenUsageTracker(unittest.TestCase):
    """Test TokenUsageTracker class."""

    def test_tracker_initialization(self):
        """Test tracker starts with zero values."""
        tracker = TokenUsageTracker()
        self.assertEqual(tracker.total_input_tokens, 0)
        self.assertEqual(tracker.total_batches, 0)
        self.assertEqual(tracker.total_documents, 0)
        self.assertIsNone(tracker.start_time)

    def test_start_and_stop(self):
        """Test start and stop methods."""
        tracker = TokenUsageTracker()
        tracker.start()
        self.assertIsNotNone(tracker.start_time)
        tracker.stop()
        self.assertIsNotNone(tracker.end_time)

    def test_add_batch(self):
        """Test recording batch statistics."""
        tracker = TokenUsageTracker()
        tracker.start()
        tracker.add_batch(10, 500)
        tracker.add_batch(5, 250)
        tracker.stop()

        self.assertEqual(tracker.total_batches, 2)
        self.assertEqual(tracker.total_documents, 15)
        self.assertEqual(tracker.total_input_tokens, 750)

    def test_get_report(self):
        """Test usage report generation."""
        tracker = TokenUsageTracker()
        tracker.start()
        tracker.add_batch(10, 500)
        tracker.stop()

        report = tracker.get_report()

        self.assertIn("total_input_tokens", report)
        self.assertIn("total_batches", report)
        self.assertIn("total_documents", report)
        self.assertIn("duration_seconds", report)
        self.assertIn("tokens_per_second", report)
        self.assertIn("docs_per_second", report)

        self.assertEqual(report["total_input_tokens"], 500)
        self.assertEqual(report["total_batches"], 1)
        self.assertEqual(report["total_documents"], 10)

    def test_report_before_start(self):
        """Test report returns empty dict if not started."""
        tracker = TokenUsageTracker()
        report = tracker.get_report()
        self.assertEqual(report, {})


class TestEmbeddingConfig(unittest.TestCase):
    """Test EmbeddingConfig dataclass."""

    def test_config_creation(self):
        """Test creating config with required fields."""
        config = EmbeddingConfig(provider="openai")
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.openai_model, "text-embedding-ada-002")
        self.assertEqual(config.openai_dimensions, 1536)
        self.assertEqual(config.batch_size, 100)

    def test_config_custom_values(self):
        """Test config with custom values."""
        config = EmbeddingConfig(
            provider="local",
            local_model_name="custom-model",
            local_dimensions=512,
            batch_size=50,
        )
        self.assertEqual(config.provider, "local")
        self.assertEqual(config.local_model_name, "custom-model")
        self.assertEqual(config.local_dimensions, 512)
        self.assertEqual(config.batch_size, 50)


class TestOpenAIEmbedder(unittest.TestCase):
    """Test OpenAIEmbedder class (mocked)."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("src.embedder.OPENAI_AVAILABLE", True)
    @patch("src.embedder.OpenAI")
    def test_init_from_env(self, mock_openai_class):
        """Test initialization from environment variable."""
        config = EmbeddingConfig(provider="openai")
        embedder = OpenAIEmbedder(config)

        mock_openai_class.assert_called_once_with(api_key="sk-test", timeout=30)

    @patch("src.embedder.OPENAI_AVAILABLE", False)
    def test_init_without_openai_package(self):
        """Test error when OpenAI package not available."""
        config = EmbeddingConfig(provider="openai")
        with self.assertRaises(ImportError):
            OpenAIEmbedder(config)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("src.embedder.OPENAI_AVAILABLE", True)
    @patch("src.embedder.OpenAI")
    def test_embed_batch_success(self, mock_openai_class):
        """Test successful batch embedding."""
        # Mock response
        mock_response = Mock()
        mock_item = Mock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        mock_response.data = [mock_item, mock_item]
        mock_client = Mock()
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        config = EmbeddingConfig(provider="openai")
        embedder = OpenAIEmbedder(config)

        texts = ["text1", "text2"]
        embeddings = embedder.embed_batch(texts)

        self.assertEqual(len(embeddings), 2)
        self.assertEqual(embeddings[0], [0.1, 0.2, 0.3])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("src.embedder.OPENAI_AVAILABLE", True)
    @patch("src.embedder.OpenAI")
    def test_embed_batch_empty(self, mock_openai_class):
        """Test embedding empty list."""
        config = EmbeddingConfig(provider="openai")
        embedder = OpenAIEmbedder(config)

        embeddings = embedder.embed_batch([])
        self.assertEqual(embeddings, [])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("src.embedder.OPENAI_AVAILABLE", True)
    @patch("src.embedder.OpenAI")
    def test_get_usage_report(self, mock_openai_class):
        """Test usage report from embedder."""
        config = EmbeddingConfig(provider="openai")
        embedder = OpenAIEmbedder(config)

        # Manually add some usage
        embedder.usage_tracker.start()
        embedder.usage_tracker.add_batch(5, 100)
        embedder.usage_tracker.stop()

        report = embedder.get_usage_report()
        self.assertEqual(report["total_documents"], 5)
        self.assertEqual(report["total_input_tokens"], 100)


class TestLocalEmbedder(unittest.TestCase):
    """Test LocalEmbedder class (mocked)."""

    @unittest.skipIf(
        not SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not installed"
    )
    @patch("src.embedder.SentenceTransformer")
    def test_init(self, mock_st):
        """Test local embedder initialization."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        config = EmbeddingConfig(provider="local", local_device="cpu")
        embedder = LocalEmbedder(config)

        mock_st.assert_called_once()
        self.assertEqual(embedder.model, mock_model)

    @patch("src.embedder.SENTENCE_TRANSFORMERS_AVAILABLE", False)
    def test_init_without_st_package(self):
        """Test error when sentence-transformers not available."""
        config = EmbeddingConfig(provider="local")
        with self.assertRaises(ImportError):
            LocalEmbedder(config)

    @unittest.skipIf(
        not SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not installed"
    )
    @patch("src.embedder.SentenceTransformer")
    def test_embed_batch(self, mock_st):
        """Test local batch embedding."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        # Mock encode to return list of lists
        mock_model.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
        mock_st.return_value = mock_model

        config = EmbeddingConfig(provider="local")
        embedder = LocalEmbedder(config)

        texts = ["text1", "text2"]
        embeddings = embedder.embed_batch(texts)

        self.assertEqual(len(embeddings), 2)
        self.assertEqual(embeddings[0], [0.1, 0.2])
        mock_model.encode.assert_called_once()

    @unittest.skipIf(
        not SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not installed"
    )
    @patch("src.embedder.SentenceTransformer")
    def test_embed_batch_empty(self, mock_st):
        """Test embedding empty list with local embedder."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        config = EmbeddingConfig(provider="local")
        embedder = LocalEmbedder(config)

        embeddings = embedder.embed_batch([])
        self.assertEqual(embeddings, [])


class TestEmbedder(unittest.TestCase):
    """Test unified Embedder class."""

    def test_init_openai_from_config(self):
        """Test OpenAI embedder initialization from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text(
                """
provider: openai
openai:
  model: text-embedding-ada-002
  dimensions: 1536
batch_size: 50
"""
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                with patch("src.embedder.OpenAIEmbedder") as mock_openai:
                    embedder = Embedder(config_path)
                    self.assertEqual(embedder.config.provider, "openai")
                    mock_openai.assert_called_once()

    def test_init_local_from_config(self):
        """Test local embedder initialization from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text(
                """
provider: local
local:
  model_name: test-model
  dimensions: 512
batch_size: 25
"""
            )

            with patch("src.embedder.LocalEmbedder") as mock_local:
                embedder = Embedder(config_path)
                self.assertEqual(embedder.config.provider, "local")
                self.assertEqual(embedder.config.local_model_name, "test-model")
                mock_local.assert_called_once()

    def test_invalid_provider(self):
        """Test error with invalid provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text("provider: invalid")

            with self.assertRaises(ValueError):
                Embedder(config_path)

    def test_embed_empty(self):
        """Test embedding empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text("provider: local")

            with patch("src.embedder.LocalEmbedder") as mock_local:
                mock_instance = Mock()
                mock_instance.embed_batch.return_value = []
                mock_local.return_value = mock_instance

                embedder = Embedder(config_path)
                result = embedder.embed([])
                self.assertEqual(result, [])

    def test_embed_batch_with_progress(self):
        """Test batch embedding with progress logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text(
                """
provider: local
batch_size: 10
"""
            )

            with patch("src.embedder.LocalEmbedder") as mock_local:
                mock_instance = Mock()
                # Simulate batch processing: first 10 texts, then 5 texts
                mock_instance.embed_batch.side_effect = [
                    [[0.1] * 384 for _ in range(10)],  # first batch
                    [[0.1] * 384 for _ in range(5)],  # second batch
                ]
                mock_local.return_value = mock_instance

                with patch.object(logging.Logger, "info") as mock_log:
                    embedder = Embedder(config_path)
                    texts = ["text"] * 15
                    result = embedder.embed_batch(texts, batch_size=10)

                    self.assertEqual(len(result), 15)
                    # Should have called embed_batch twice (10 + 5)
                    self.assertEqual(mock_instance.embed_batch.call_count, 2)

    def test_get_dimensions_openai(self):
        """Test getting dimensions for OpenAI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text(
                """
provider: openai
openai:
  dimensions: 1536
"""
            )

            with patch("src.embedder.OpenAIEmbedder") as mock_openai:
                embedder = Embedder(config_path)
                self.assertEqual(embedder.get_dimensions(), 1536)

    def test_get_dimensions_local(self):
        """Test getting dimensions for local."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text(
                """
provider: local
local:
  dimensions: 384
"""
            )

            with patch("src.embedder.LocalEmbedder") as mock_local:
                embedder = Embedder(config_path)
                self.assertEqual(embedder.get_dimensions(), 384)

    def test_get_usage_report(self):
        """Test unified usage report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "embeddings.yaml"
            config_path.write_text("provider: local")

            with patch("src.embedder.LocalEmbedder") as mock_local:
                mock_instance = Mock()
                mock_instance.get_usage_report.return_value = {"total_documents": 100}
                mock_local.return_value = mock_instance

                embedder = Embedder(config_path)
                report = embedder.get_usage_report()
                self.assertEqual(report["total_documents"], 100)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    @patch("src.embedder.Embedder")
    def test_generate_embeddings(self, mock_embedder_class):
        """Test generate_embeddings convenience function."""
        mock_instance = Mock()
        mock_instance.embed_batch.return_value = [[0.1, 0.2]]
        mock_embedder_class.return_value = mock_instance

        from src.embedder import generate_embeddings

        result = generate_embeddings(["test"])

        mock_embedder_class.assert_called_once_with("config/embeddings.yaml")
        mock_instance.embed_batch.assert_called_once_with(["test"])
        self.assertEqual(result, [[0.1, 0.2]])

    @patch("src.embedder.Embedder")
    def test_batch_embed(self, mock_embedder_class):
        """Test batch_embed convenience function."""
        mock_instance = Mock()
        mock_instance.embed_batch.return_value = [[0.1, 0.2]]
        mock_embedder_class.return_value = mock_instance

        from src.embedder import batch_embed

        chunks = [{"text": "doc1"}, {"text": "doc2"}]
        result = batch_embed(chunks, batch_size=50)

        mock_embedder_class.assert_called_once_with("config/embeddings.yaml")
        mock_instance.embed_batch.assert_called_once_with(
            ["doc1", "doc2"], batch_size=50
        )
        self.assertEqual(result, [[0.1, 0.2]])


if __name__ == "__main__":
    unittest.main()
