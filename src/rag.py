"""
RAG Generation Pipeline

This module provides:
- LLM-based answer generation from retrieved context
- Configurable LLM providers (OpenAI or local)
- Context formatting and prompt construction
- Confidence scoring based on retrieval scores
"""

import logging
import os
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
from pathlib import Path

import yaml
from dotenv import load_dotenv

from retriever import SearchResult

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class RAGConfig:
    """Configuration for RAG generation."""

    def __init__(self, config_path: Union[str, Path] = "config/rag.yaml"):
        """
        Initialize RAG configuration.

        Args:
            config_path: Path to RAG configuration YAML file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"RAG config not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded RAG config from {self.config_path}")
        return config

    @property
    def provider(self) -> str:
        """Get LLM provider."""
        return self.config.get("provider", "openai")

    @property
    def openai_config(self) -> Dict[str, Any]:
        """Get OpenAI configuration."""
        return self.config.get("openai", {})

    @property
    def local_config(self) -> Dict[str, Any]:
        """Get local LLM configuration."""
        return self.config.get("local", {})

    @property
    def generation_config(self) -> Dict[str, Any]:
        """Get generation settings."""
        return self.config.get("generation", {})

    @property
    def system_prompt(self) -> str:
        """Get system prompt for LLM."""
        return self.generation_config.get(
            "system_prompt",
            "You are a helpful assistant that answers questions based on the provided context.",
        )

    @property
    def max_context_length(self) -> int:
        """Get maximum context length in characters."""
        return self.generation_config.get("max_context_length", 4000)

    @property
    def min_context_chunks(self) -> int:
        """Get minimum number of context chunks to use."""
        return self.generation_config.get("min_context_chunks", 3)


class LLMProvider:
    """Base class for LLM providers."""

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Generate text from LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific arguments

        Returns:
            Tuple of (generated_text, confidence_score)
        """
        raise NotImplementedError("Subclasses must implement generate()")


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OpenAI provider.

        Args:
            config: OpenAI configuration from RAG config
        """
        self.config = config
        self.api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        self.model = config.get("model", "gpt-4o")
        self.max_retries = config.get("max_retries", 3)

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY in .env or provide in config."
            )

        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key)
            logger.info(f"Initialized OpenAI provider with model: {self.model}")
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Generate text using OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: System prompt (overrides config)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Returns:
            Tuple of (generated_text, confidence_score)
        """
        import time
        from openai import RateLimitError, APIError, APIConnectionError

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Merge config with overrides
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.config.get("temperature", 0.7),
            "max_tokens": max_tokens or self.config.get("max_tokens", 1000),
            "top_p": self.config.get("top_p", 1.0),
            "frequency_penalty": self.config.get("frequency_penalty", 0.0),
            "presence_penalty": self.config.get("presence_penalty", 0.0),
        }
        params.update(kwargs)

        retries = 0
        while retries <= self.max_retries:
            try:
                logger.debug(f"Calling OpenAI API (attempt {retries + 1})")
                start_time = time.time()

                response = self.client.chat.completions.create(**params)

                elapsed = time.time() - start_time
                logger.debug(f"OpenAI API call completed in {elapsed:.2f}s")

                generated_text = response.choices[0].message.content.strip()
                # OpenAI doesn't provide explicit confidence, use completion tokens as proxy
                confidence = 0.9  # Default confidence for successful completion

                return generated_text, confidence

            except RateLimitError as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(
                        f"OpenAI rate limit exceeded after {retries} retries: {e}"
                    )
                    raise
                wait_time = 2**retries
                logger.warning(f"Rate limited, retrying in {wait_time}s...")
                time.sleep(wait_time)

            except (APIError, APIConnectionError) as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"OpenAI API error after {retries} retries: {e}")
                    raise
                wait_time = 2**retries
                logger.warning(f"API error, retrying in {wait_time}s...")
                time.sleep(wait_time)

            except Exception as e:
                logger.error(f"Unexpected error calling OpenAI: {e}")
                raise

        raise RuntimeError(
            f"Failed to get response from OpenAI after {self.max_retries} retries"
        )


class LocalProvider(LLMProvider):
    """Local LLM provider (Ollama, etc.)."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize local LLM provider.

        Args:
            config: Local LLM configuration
        """
        self.config = config
        self.provider_type = config.get("provider", "ollama")
        self.model = config.get("model", "llama3")
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 1000)

        if self.provider_type == "ollama":
            self._init_ollama()
        else:
            raise ValueError(f"Unsupported local provider: {self.provider_type}")

    def _init_ollama(self):
        """Initialize Ollama client."""
        try:
            import requests

            self.requests = requests
            logger.info(f"Initialized Ollama provider with model: {self.model}")
        except ImportError:
            raise ImportError(
                "requests package not installed. Run: pip install requests"
            )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Generate text using local LLM (Ollama).

        Args:
            prompt: User prompt
            system_prompt: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific arguments

        Returns:
            Tuple of (generated_text, confidence_score)
        """
        if self.provider_type != "ollama":
            raise NotImplementedError(f"Provider {self.provider_type} not implemented")

        # Construct full prompt for Ollama
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": max_tokens or self.max_tokens,
            },
        }

        try:
            response = self.requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=300,  # 5 minute timeout
            )
            response.raise_for_status()
            result = response.json()

            generated_text = result.get("response", "").strip()
            # Ollama doesn't provide explicit confidence
            confidence = 0.85  # Default confidence for local models

            return generated_text, confidence

        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise


class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline.

    Combines vector search with LLM generation to provide
    context-aware answers to user queries.
    """

    def __init__(self, retriever, config_path: Union[str, Path] = "config/rag.yaml"):
        """
        Initialize RAG pipeline.

        Args:
            retriever: Retriever instance for document search
            config_path: Path to RAG configuration file
        """
        self.retriever = retriever
        self.config = RAGConfig(config_path)
        self.llm = self._init_llm()
        logger.info("RAG pipeline initialized")

    def _init_llm(self) -> LLMProvider:
        """
        Initialize LLM provider based on configuration.

        Returns:
            Initialized LLM provider instance
        """
        provider = self.config.provider

        if provider == "openai":
            return OpenAIProvider(self.config.openai_config)
        elif provider == "local":
            return LocalProvider(self.config.local_config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _format_context(
        self, search_result: SearchResult, max_length: Optional[int] = None
    ) -> str:
        """
        Format search results into context string for LLM.

        Args:
            search_result: SearchResult from retriever
            max_length: Maximum total context length (characters)

        Returns:
            Formatted context string
        """
        if max_length is None:
            max_length = self.config.max_context_length

        context_parts = []
        total_length = 0

        for i, (doc, meta, score) in enumerate(
            zip(search_result.documents, search_result.metadatas, search_result.scores)
        ):
            # Build context entry
            source = meta.get("source", "unknown")
            doc_type = meta.get("type", "document")
            title = meta.get("title", "Untitled")
            url = meta.get("url", "")

            entry = f"[{i + 1}] Source: {source} ({doc_type})\n"
            if title and title != "Untitled":
                entry += f"Title: {title}\n"
            if url:
                entry += f"URL: {url}\n"
            entry += f"Relevance: {score:.3f}\n"
            entry += f"Content:\n{doc}\n\n"

            # Check if adding this would exceed max length
            if total_length + len(entry) > max_length and context_parts:
                logger.warning(
                    f"Context truncated at {total_length} chars (max: {max_length})"
                )
                break

            context_parts.append(entry)
            total_length += len(entry)

        if not context_parts:
            return "No relevant context found."

        context = "".join(context_parts)
        logger.info(
            f"Formatted context: {len(context_parts)} chunks, {total_length} characters"
        )
        return context

    def _build_prompt(
        self, query: str, context: str, system_prompt: Optional[str] = None
    ) -> str:
        """
        Build complete prompt for LLM.

        Args:
            query: User query
            context: Formatted context string
            system_prompt: Optional custom system prompt

        Returns:
            Complete prompt string
        """
        template = self.config.generation_config.get(
            "context_template", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        )

        prompt = template.format(context=context, question=query)
        return prompt

    def generate(
        self,
        query: str,
        k: int = 10,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        return_context: bool = False,
        **llm_overrides,
    ) -> Dict[str, Any]:
        """
        Generate answer for query using RAG.

        Args:
            query: User query
            k: Number of context chunks to retrieve
            collection_name: Optional specific collection to search
            filters: Optional metadata filters for search
            return_context: Whether to include formatted context in response
            **llm_overrides: Override LLM parameters (temperature, max_tokens, etc.)

        Returns:
            Dictionary with:
                - answer: Generated answer text
                - confidence: Confidence score (0-1)
                - sources: List of source metadata
                - query_time: Total time taken
                - context_chunks: (optional) Number of context chunks used
                - context: (optional) Formatted context if return_context=True
        """
        import time

        logger.info(f"Generating RAG response for query: '{query[:100]}...'")
        start_time = time.time()

        try:
            # Step 1: Retrieve relevant documents
            retrieval_start = time.time()
            search_result = self.retriever.search(
                query_text=query, k=k, collection_name=collection_name, filters=filters
            )
            retrieval_time = time.time() - retrieval_start
            logger.info(
                f"Retrieved {len(search_result)} documents in {retrieval_time:.3f}s"
            )

            if len(search_result) == 0:
                logger.warning("No relevant documents found for query")
                total_time = time.time() - start_time
                return {
                    "answer": "I couldn't find any relevant information to answer your question.",
                    "confidence": 0.0,
                    "sources": [],
                    "query_time": total_time,
                    "stats": {
                        "retrieval_time": retrieval_time,
                        "generation_time": 0.0,
                        "context_chunks": 0,
                        "context_length": 0,
                    },
                }

            # Step 2: Format context
            format_start = time.time()
            context = self._format_context(search_result)
            format_time = time.time() - format_start
            logger.debug(f"Context formatted in {format_time:.3f}s")

            # Step 3: Build prompt
            system_prompt = self.config.system_prompt
            prompt = self._build_prompt(query, context, system_prompt)

            # Step 4: Generate answer
            generation_start = time.time()
            temperature = llm_overrides.get(
                "temperature", self.config.openai_config.get("temperature", 0.7)
            )
            max_tokens = llm_overrides.get(
                "max_tokens", self.config.openai_config.get("max_tokens", 1000)
            )

            # Remove these from llm_overrides to avoid duplicate keyword arguments
            llm_overrides_clean = {
                k: v
                for k, v in llm_overrides.items()
                if k not in ["temperature", "max_tokens"]
            }

            answer, confidence = self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **llm_overrides_clean,
            )
            generation_time = time.time() - generation_start
            logger.info(
                f"Answer generated in {generation_time:.3f}s, confidence: {confidence:.3f}"
            )

            # Step 5: Extract sources
            sources = []
            seen_urls = set()
            for meta in search_result.metadatas:
                source_info = {
                    "source": meta.get("source", "unknown"),
                    "type": meta.get("type", "document"),
                    "title": meta.get("title", "Untitled"),
                    "url": meta.get("url", ""),
                    "collection": meta.get("_collection", "unknown"),
                }
                # Deduplicate sources based on URL or title
                url = source_info["url"]
                title = source_info["title"]
                dedup_key = url if url else title

                if dedup_key and dedup_key not in seen_urls:
                    sources.append(source_info)
                    seen_urls.add(dedup_key)

            total_time = time.time() - start_time
            logger.info(f"RAG query completed in {total_time:.3f}s total")

            result = {
                "answer": answer,
                "confidence": confidence,
                "sources": sources,
                "query_time": total_time,
                "stats": {
                    "retrieval_time": retrieval_time,
                    "generation_time": generation_time,
                    "context_chunks": len(search_result),
                    "context_length": len(context),
                },
            }

            if return_context:
                result["context"] = context

            return result

        except Exception as e:
            logger.error(f"RAG generation failed: {e}", exc_info=True)
            raise


def generate_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    config_path: Union[str, Path] = "config/rag.yaml",
    **llm_overrides,
) -> Dict[str, Any]:
    """
    Convenience function for generating answers from query and context chunks.

    This function allows answer generation without a full retriever setup,
    useful when you already have retrieved or curated context chunks.

    Args:
        query: User query
        context_chunks: List of chunks with 'document', 'metadata', 'score' keys
        config_path: Path to RAG configuration
        **llm_overrides: Override LLM parameters (temperature, max_tokens, etc.)

    Returns:
        Dictionary with:
            - answer: Generated answer text
            - confidence: Confidence score (0-1)
            - sources: List of source metadata
            - query_time: Total time taken (0 for this simple function)
            - context_chunks: Number of context chunks used
            - context_length: Length of formatted context in characters
    """
    import time

    if not context_chunks:
        return {
            "answer": "No context provided.",
            "confidence": 0.0,
            "sources": [],
            "query_time": 0.0,
            "context_chunks": 0,
            "context_length": 0,
        }

    try:
        # Load configuration
        config = RAGConfig(config_path)

        # Initialize LLM provider
        provider = None
        if config.provider == "openai":
            provider = OpenAIProvider(config.openai_config)
        elif config.provider == "local":
            provider = LocalProvider(config.local_config)
        else:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")

        # Create SearchResult-like object from chunks
        docs = [chunk["document"] for chunk in context_chunks]
        metas = [chunk["metadata"] for chunk in context_chunks]
        scores = [chunk.get("score", 1.0) for chunk in context_chunks]

        # Create a minimal SearchResult for formatting
        class MinimalSearchResult:
            def __init__(self, documents, metadatas, scores):
                self.documents = documents
                self.metadatas = metadatas
                self.scores = scores

        search_result = MinimalSearchResult(docs, metas, scores)

        # Format context (similar to RAGPipeline._format_context)
        context = ""
        total_length = 0
        max_length = config.max_context_length

        for i, (doc, meta, score) in enumerate(
            zip(search_result.documents, search_result.metadatas, search_result.scores)
        ):
            source = meta.get("source", "unknown")
            doc_type = meta.get("type", "document")
            title = meta.get("title", "Untitled")
            url = meta.get("url", "")

            entry = f"[{i + 1}] Source: {source} ({doc_type})\n"
            if title and title != "Untitled":
                entry += f"Title: {title}\n"
            if url:
                entry += f"URL: {url}\n"
            entry += f"Relevance: {score:.3f}\n"
            entry += f"Content:\n{doc}\n\n"

            if total_length + len(entry) > max_length and i > 0:
                logger.warning(
                    f"Context truncated at {total_length} chars (max: {max_length})"
                )
                break

            context += entry
            total_length += len(entry)

        if not context.strip():
            return {
                "answer": "No valid context could be formatted from the provided chunks.",
                "confidence": 0.0,
                "sources": [],
                "query_time": 0.0,
                "context_chunks": 0,
                "context_length": 0,
            }

        # Build prompt
        template = config.generation_config.get(
            "context_template", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        )
        prompt = template.format(context=context, question=query)

        # Get LLM parameters with overrides
        temperature = llm_overrides.get(
            "temperature", config.openai_config.get("temperature", 0.7)
        )
        max_tokens = llm_overrides.get(
            "max_tokens", config.openai_config.get("max_tokens", 1000)
        )

        # Remove these from llm_overrides to avoid duplicate keyword arguments
        llm_overrides_clean = {
            k: v
            for k, v in llm_overrides.items()
            if k not in ["temperature", "max_tokens"]
        }

        # Generate answer
        system_prompt = config.system_prompt
        answer, confidence = provider.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **llm_overrides_clean,
        )

        # Extract sources
        sources = []
        seen_urls = set()
        for meta in metas:
            source_info = {
                "source": meta.get("source", "unknown"),
                "type": meta.get("type", "document"),
                "title": meta.get("title", "Untitled"),
                "url": meta.get("url", ""),
            }
            dedup_key = (
                source_info["url"] if source_info["url"] else source_info["title"]
            )
            if dedup_key and dedup_key not in seen_urls:
                sources.append(source_info)
                seen_urls.add(dedup_key)

        return {
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "query_time": 0.0,  # Not tracking in this simple function
            "context_chunks": len(docs),
            "context_length": total_length,
        }

    except Exception as e:
        logger.error(f"generate_answer failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Quick test if retriever is available
    import sys
    from pathlib import Path

    # Add src to path if running as script
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    if len(sys.argv) < 2:
        print("Usage: python rag.py <query> [--k N] [--collection NAME]")
        sys.exit(1)

    query = sys.argv[1]
    k = 5
    collection = None

    # Parse args
    if len(sys.argv) > 2:
        if sys.argv[2] == "--k" and len(sys.argv) > 3:
            k = int(sys.argv[3])
        if sys.argv[2] == "--collection" and len(sys.argv) > 3:
            collection = sys.argv[3]

    try:
        from retriever import Retriever

        logger.info("Initializing retriever...")
        retriever = Retriever()

        logger.info("Initializing RAG pipeline...")
        pipeline = RAGPipeline(retriever)

        logger.info(f"Generating answer for: {query}")
        result = pipeline.generate(
            query=query, k=k, collection_name=collection, return_context=True
        )

        print("\n" + "=" * 80)
        print("ANSWER:")
        print("=" * 80)
        print(result["answer"])
        print("\n" + "=" * 80)
        print(f"Confidence: {result['confidence']:.3f}")
        print(f"Query time: {result['query_time']:.3f}s")
        print(f"Context chunks: {result['stats']['context_chunks']}")
        print(f"Sources: {len(result['sources'])}")
        for i, src in enumerate(result["sources"], 1):
            print(
                f"  {i}. {src.get('title', 'Untitled')} ({src.get('source', 'unknown')})"
            )
        print("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
