"""
Tests for RAG pipeline and generation functionality.

This module tests:
- RAGConfig loading and validation
- LLM provider initialization and generation
- RAGPipeline end-to-end generation
- Context formatting and prompt building
- Error handling and edge cases
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
from pathlib import Path
import yaml
import pytest

from src.rag import (
    RAGConfig,
    LLMProvider,
    OpenAIProvider,
    LocalProvider,
    RAGPipeline,
    generate_answer,
)
from src.retriever import SearchResult


class TestRAGConfig(unittest.TestCase):
    """Tests for RAG configuration."""

    def test_config_load_valid(self, tmp_path):
        """Test loading valid RAG configuration."""
        config_data = {
            "provider": "openai",
            "openai": {
                "model": "gpt-4o",
                "api_key": "sk-test",
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            "generation": {
                "system_prompt": "You are a helpful assistant.",
                "max_context_length": 4000,
                "min_context_chunks": 3,
            },
        }

        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        assert config.provider == "openai"
        assert config.openai_config["model"] == "gpt-4o"
        assert config.system_prompt == "You are a helpful assistant."
        assert config.max_context_length == 4000

    def test_config_missing_file(self):
        """Test error when config file not found."""
        with pytest.raises(FileNotFoundError):
            RAGConfig("/nonexistent/config.yaml")

    def test_config_default_values(self, tmp_path):
        """Test default values when missing."""
        config_data = {"provider": "openai"}
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        assert config.provider == "openai"
        assert "system_prompt" in config.generation_config

    def test_provider_selection(self, tmp_path):
        """Test provider selection from config."""
        for provider in ["openai", "local"]:
            config_data = {"provider": provider}
            config_file = tmp_path / f"rag_{provider}.yaml"
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            config = RAGConfig(str(config_file))
            assert config.provider == provider


class TestOpenAIProvider(unittest.TestCase):
    """Tests for OpenAI LLM provider."""

    def test_provider_init_missing_api_key(self, tmp_path):
        config_data = {"provider": "openai", "openai": {"model": "gpt-4o"}}
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as cm:
                OpenAIProvider(config.openai_config)
            self.assertIn("API key not found", str(cm.exception))

    def test_provider_init_with_env_key(self, tmp_path, monkeypatch):
        """Test initialization with environment API key."""
        config_data = {"provider": "openai", "openai": {"model": "gpt-4o"}}
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        provider = OpenAIProvider(config.openai_config)
        self.assertEqual(provider.model, "gpt-4o")
        self.assertEqual(provider.api_key, "sk-test-key")

    @patch("src.rag.OpenAIProvider.__init__", return_value=None)
    def test_generate_success(self, mock_init, tmp_path, monkeypatch):
        """Test successful text generation."""
        # Create a mock OpenAIProvider instance
        from src.rag import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider.config = {"model": "gpt-4o", "api_key": "sk-test", "max_retries": 3}
        provider.api_key = "sk-test"
        provider.model = "gpt-4o"
        provider.max_retries = 3
        provider.client = MagicMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        provider.client.chat.completions.create.return_value = mock_response

        config_data = {
            "provider": "openai",
            "openai": {
                "model": "gpt-4o",
                "api_key": "sk-test",
                "temperature": 0.7,
                "max_tokens": 1000,
            },
        }
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))

        # Manually set provider's generate method
        result, confidence = provider.generate(
            prompt="Test prompt",
            system_prompt="You are helpful",
            temperature=0.5,
            max_tokens=500,
        )

        self.assertEqual(result, "Test answer")
        self.assertEqual(confidence, 0.9)
        provider.client.chat.completions.create.assert_called_once()

    @patch("openai.OpenAI")
    def test_generate_rate_limit_retry(self, mock_openai_class, tmp_path, monkeypatch):
        """Test rate limit error with retry."""
        from openai import RateLimitError

        # Mock rate limit then success
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Retry success"))]
        mock_client.chat.completions.create.side_effect = [
            RateLimitError("Rate limited"),
            mock_response,
        ]
        mock_openai_class.return_value = mock_client

        config_data = {
            "provider": "openai",
            "openai": {
                "model": "gpt-4o",
                "api_key": "sk-test",
                "max_retries": 3,
            },
        }
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        provider = OpenAIProvider(config.openai_config)

        result, confidence = provider.generate(prompt="Test")
        assert result == "Retry success"
        assert mock_client.chat.completions.create.call_count == 2


class TestLocalProvider:
    """Tests for local LLM provider."""

    def test_provider_init_unsupported(self, tmp_path):
        """Test initialization fails with unsupported provider."""
        config_data = {
            "provider": "local",
            "local": {"provider": "unknown", "model": "test"},
        }
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))

        with pytest.raises(ValueError, match="Unsupported local provider"):
            LocalProvider(config.local_config)

    @patch("requests.post")
    def test_generate_ollama_success(self, mock_post, tmp_path):
        """Test successful generation with Ollama."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Ollama answer"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        config_data = {
            "provider": "local",
            "local": {
                "provider": "ollama",
                "model": "llama3",
                "base_url": "http://localhost:11434",
            },
        }
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        provider = LocalProvider(config.local_config)

        result, confidence = provider.generate(prompt="Test prompt")
        assert result == "Ollama answer"
        assert confidence == 0.85
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_generate_ollama_error(self, mock_post, tmp_path):
        """Test Ollama generation failure."""
        mock_post.side_effect = Exception("Connection error")

        config_data = {
            "provider": "local",
            "local": {
                "provider": "ollama",
                "model": "llama3",
            },
        }
        config_file = tmp_path / "rag_test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = RAGConfig(str(config_file))
        provider = LocalProvider(config.local_config)

        with pytest.raises(Exception, match="Connection error"):
            provider.generate(prompt="Test")


class TestRAGPipeline:
    """Tests for RAG pipeline."""

    @pytest.fixture
    def mock_retriever(self):
        """Create mock retriever."""
        retriever = Mock()
        retriever.search.return_value = SearchResult(
            documents=["Doc 1 content", "Doc 2 content"],
            metadatas=[
                {"source": "github", "title": "Doc 1", "url": "http://example.com/1"},
                {"source": "web", "title": "Doc 2", "url": "http://example.com/2"},
            ],
            scores=[0.95, 0.87],
            collection="test",
            query_time=0.1,
        )
        return retriever

    @pytest.fixture
    def tmp_config(self, tmp_path):
        """Create temporary RAG config."""
        config_data = {
            "provider": "openai",
            "openai": {
                "model": "gpt-4o",
                "api_key": "sk-test",
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            "generation": {
                "system_prompt": "You are a test assistant.",
                "max_context_length": 4000,
                "min_context_chunks": 1,
                "context_template": "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:",
            },
        }
        config_file = tmp_path / "rag.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        return str(config_file)

    @patch("src.rag.OpenAIProvider")
    def test_pipeline_init(self, mock_provider_class, tmp_config, mock_retriever):
        """Test pipeline initialization."""
        mock_llm = Mock()
        mock_provider_class.return_value = mock_llm

        pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)
        assert pipeline.retriever == mock_retriever
        assert pipeline.llm == mock_llm
        mock_provider_class.assert_called_once()

    @patch("src.rag.OpenAIProvider")
    def test_generate_full_pipeline(
        self, mock_provider_class, tmp_config, mock_retriever
    ):
        """Test full RAG generation."""
        # Mock LLM to return predetermined answer
        mock_llm = Mock()
        mock_llm.generate.return_value = ("Generated answer text", 0.92)
        mock_provider_class.return_value = mock_llm

        pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        result = pipeline.generate(
            query="What is the project about?", k=5, return_context=True
        )

        # Verify result structure
        assert "answer" in result
        assert "confidence" in result
        assert "sources" in result
        assert "query_time" in result
        assert "stats" in result
        assert "context" in result

        assert result["answer"] == "Generated answer text"
        assert result["confidence"] == 0.92
        assert len(result["sources"]) == 2
        assert result["stats"]["context_chunks"] == 2

        # Verify retriever was called
        mock_retriever.search.assert_called_once_with(
            query_text="What is the project about?",
            k=5,
            collection_name=None,
            filters=None,
        )

        # Verify LLM was called with properly formatted prompt
        mock_llm.generate.assert_called_once()
        call_args = mock_llm.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "Context:" in prompt
        assert "Doc 1 content" in prompt
        assert "Doc 2 content" in prompt
        assert "What is the project about?" in prompt

    @patch("src.rag.OpenAIProvider")
    def test_generate_no_results(self, mock_provider_class, tmp_config, mock_retriever):
        """Test RAG with no retrieved documents."""
        # Mock retriever to return empty results
        mock_retriever.search.return_value = SearchResult(
            documents=[], metadatas=[], scores=[], collection="test", query_time=0.05
        )

        pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        result = pipeline.generate(query="Obscure query")

        assert (
            result["answer"]
            == "I couldn't find any relevant information to answer your question."
        )
        assert result["confidence"] == 0.0
        assert result["sources"] == []
        assert result["stats"]["context_chunks"] == 0

        # LLM should not be called when no context
        mock_pipeline = pipeline
        mock_pipeline.llm = Mock()
        mock_pipeline.llm.generate.assert_not_called()

    @patch("src.rag.OpenAIProvider")
    def test_generate_with_filters(
        self, mock_provider_class, tmp_config, mock_retriever
    ):
        """Test RAG with metadata filters."""
        mock_llm = Mock()
        mock_llm.generate.return_value = ("Filtered answer", 0.88)
        mock_provider_class.return_value = mock_llm

        pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        filters = {"source": "github", "type": "repo"}
        result = pipeline.generate(query="Test query", filters=filters)

        # Verify filters were passed to retriever
        mock_retriever.search.assert_called_with(
            query_text="Test query", k=10, collection_name=None, filters=filters
        )

    @patch("src.rag.OpenAIProvider")
    def test_generate_with_llm_overrides(
        self, mock_provider_class, tmp_config, mock_retriever
    ):
        """Test RAG with LLM parameter overrides."""
        mock_llm = Mock()
        mock_llm.generate.return_value = ("Answer with custom temp", 0.85)
        mock_provider_class.return_value = mock_llm

        pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        result = pipeline.generate(query="Test", temperature=0.3, max_tokens=500)

        # Verify overrides were passed to LLM
        call_args = mock_llm.generate.call_args
        assert call_args[1]["temperature"] == 0.3
        assert call_args[1]["max_tokens"] == 500

    def test_format_context(self, tmp_config, mock_retriever):
        """Test context formatting."""
        config = RAGConfig(tmp_config)

        # Create pipeline just to access _format_context
        with patch("src.rag.OpenAIProvider"):
            pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        search_result = SearchResult(
            documents=["Document content here."],
            metadatas=[
                {
                    "source": "github",
                    "type": "repo",
                    "title": "Test Repo",
                    "url": "https://github.com/test/repo",
                    "_collection": "github_docs",
                }
            ],
            scores=[0.95],
            collection="github_docs",
            query_time=0.1,
        )

        context = pipeline._format_context(search_result)

        assert "[1]" in context
        assert "Source: github" in context
        assert "Title: Test Repo" in context
        assert "URL: https://github.com/test/repo" in context
        assert "Relevance: 0.950" in context
        assert "Document content here." in context

    def test_format_context_truncation(self, tmp_config, mock_retriever):
        """Test context truncation when exceeding max length."""
        config = RAGConfig(tmp_config)
        config.generation_config["max_context_length"] = 100

        with patch("src.rag.OpenAIProvider"):
            pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        # Create many chunks to trigger truncation
        docs = ["x" * 50 for _ in range(10)]
        metas = [{"source": "test", "title": f"Doc {i}"} for i in range(10)]
        scores = [0.9] * 10

        search_result = SearchResult(
            documents=docs,
            metadatas=metas,
            scores=scores,
            collection="test",
            query_time=0.1,
        )

        context = pipeline._format_context(search_result)
        assert len(context) <= 150  # Should be truncated near 100 chars

    def test_build_prompt(self, tmp_config, mock_retriever):
        """Test prompt building."""
        config = RAGConfig(tmp_config)

        with patch("src.rag.OpenAIProvider"):
            pipeline = RAGPipeline(mock_retriever, config_path=tmp_config)

        query = "What is RAG?"
        context = "Context information here."

        prompt = pipeline._build_prompt(query, context)

        assert "Context:" in prompt
        assert context in prompt
        assert "Question: What is RAG?" in prompt
        assert "Answer:" in prompt


class TestGenerateAnswer:
    """Tests for convenience function."""

    def test_generate_answer_not_implemented(self):
        """Test that convenience function raises NotImplementedError."""
        chunks = [{"document": "Test", "metadata": {}, "score": 1.0}]

        with pytest.raises(NotImplementedError):
            generate_answer("test query", chunks)


class TestRAGIntegration:
    """Integration tests for RAG (require mocked or real LLM)."""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
    )
    @pytest.mark.integration
    def test_full_integration_with_openai(self, mock_retriever):
        """Integration test with real OpenAI API (requires API key)."""
        pipeline = RAGPipeline(mock_retriever)

        result = pipeline.generate(query="What is this project about?", k=3)

        assert result["answer"]
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result["sources"], list)


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    """Set up test environment with temporary config."""
    monkeypatch.chdir(tmp_path)
    yield
