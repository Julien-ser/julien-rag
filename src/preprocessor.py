"""
Document preprocessing and chunking pipeline for RAG system.

This module handles:
- Text extraction from raw JSON sources (GitHub, web scraped)
- Text cleaning and normalization
- Recursive chunking with token limits
- Token counting with tiktoken
- Metadata generation according to schema_design.md
- Output to JSONL format for downstream processing
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

import tiktoken
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TokenCounter:
    """Token counting utility using tiktoken."""

    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding = tiktoken.get_encoding(encoding_name)
        self.encoding_name = encoding_name

    def count(self, text: str) -> int:
        """Count tokens in text."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to max_tokens."""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)

    def split_fixed(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Fallback: split text into fixed-size token chunks with overlap."""
        tokens = self.encoding.encode(text)
        chunks = []
        start = 0

        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)

            if end >= len(tokens):
                break
            start = end - overlap

        return chunks


class TextCleaner:
    """Text cleaning and normalization utility."""

    @staticmethod
    def clean_html(text: str) -> str:
        """Remove HTML tags and decode entities."""
        if not text:
            return ""

        # Use BeautifulSoup to strip HTML
        soup = BeautifulSoup(text, "html.parser")
        cleaned = soup.get_text(separator=" ", strip=True)

        # Decode HTML entities
        import html as html_lib

        cleaned = html_lib.unescape(cleaned)

        return cleaned

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace: collapse multiple spaces, fix line breaks."""
        if not text:
            return ""

        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)

        # Ensure consistent line breaks
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove trailing/leading whitespace
        text = text.strip()

        return text

    @staticmethod
    def clean_markdown_code_blocks(text: str) -> str:
        """Normalize markdown code blocks: preserve indentation."""
        # Ensure code fence lines are on their own line
        text = re.sub(r"```(\w*)\s*\n", r"```\1\n", text)
        text = re.sub(r"\n\s*```", r"\n```", text)

        return text

    def clean(self, text: str, preserve_code: bool = True) -> str:
        """
        Full cleaning pipeline.

        Args:
            text: Raw text input
            preserve_code: If True, handle code blocks specially
        """
        if not text:
            return ""

        if preserve_code:
            # Protect code blocks first
            text, code_blocks = self._protect_code_blocks(text)

            # Remove HTML (code blocks are placeholders, so they're safe)
            text = self.clean_html(text)

            # Normalize whitespace
            text = self.normalize_whitespace(text)

            # Restore code blocks
            text = self._restore_code_blocks(text, code_blocks)

            # Clean code block formatting
            text = self.clean_markdown_code_blocks(text)
        else:
            text = self.clean_html(text)
            text = self.normalize_whitespace(text)

        return text

    def _protect_code_blocks(self, text: str) -> tuple[str, List[Dict]]:
        """Extract code blocks to preserve them during whitespace normalization."""
        code_blocks = []

        # Pattern for fenced code blocks
        fenced_pattern = r"```(\w*)\n(.*?)\n```"

        def replace_with_placeholder(match):
            placeholder = f"___CODE_BLOCK_{len(code_blocks)}___"
            code_blocks.append(
                {
                    "placeholder": placeholder,
                    "language": match.group(1),
                    "code": match.group(2),
                }
            )
            return placeholder

        # Replace all fenced code blocks
        text = re.sub(fenced_pattern, replace_with_placeholder, text, flags=re.DOTALL)

        return text, code_blocks

    def _restore_code_blocks(self, text: str, code_blocks: List[Dict]) -> str:
        """Restore code blocks from placeholders."""
        for block in code_blocks:
            replacement = f"```{block['language']}\n{block['code']}\n```"
            text = text.replace(block["placeholder"], replacement)
        return text


class RecursiveTextSplitter:
    """Recursive character text splitter with token-based limits."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 100,
        min_chunk_size: int = 100,
        max_chunk_size: int = 768,
        separators: Optional[List[str]] = None,
        token_counter: Optional[TokenCounter] = None,
    ):
        """
        Initialize the recursive text splitter.

        Args:
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
            min_chunk_size: Minimum chunk size (chunks smaller are merged)
            max_chunk_size: Maximum chunk size (chunks larger are split)
            separators: List of separators in priority order
            token_counter: TokenCounter instance
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

        self.separators = separators or [
            "\n\n\n",  # Triple newline
            "\n\n",  # Double newline
            "\n",  # Single newline
            ". ",  # Sentence boundary
            "! ",  # Sentence boundary
            "? ",  # Sentence boundary
            "; ",  # Clause boundary
            ", ",  # Phrase boundary
            " ",  # Word boundary
            "",  # Character boundary
        ]

        self.token_counter = token_counter or TokenCounter()

    def split_text(self, text: str, content_type: str = "webpage") -> List[str]:
        """
        Split text into chunks using recursive strategy.

        Args:
            text: Text to split
            content_type: Content type for special handling (e.g., 'code')

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        # Adjust parameters based on content type
        chunk_size = self.chunk_size
        chunk_overlap = self.chunk_overlap

        if content_type == "code":
            chunk_size = 768
            chunk_overlap = 150
        elif content_type in ["commit_message", "tweet"]:
            # These are typically small; no chunking needed
            token_count = self.token_counter.count(text)
            return [text] if token_count <= self.max_chunk_size else []

        # Quick check: if text is already within limits, return as single chunk
        token_count = self.token_counter.count(text)
        if token_count <= chunk_size:
            return [text]

        # If text is too large, apply recursive splitting
        return self._recursive_split(text, self.separators, chunk_size, chunk_overlap)

    def _recursive_split(
        self, text: str, separators: List[str], chunk_size: int, overlap: int
    ) -> List[str]:
        """
        Recursively split text using separators.

        Args:
            text: Text to split
            separators: Available separators (in priority order)
            chunk_size: Target chunk size in tokens
            overlap: Overlap between chunks in tokens

        Returns:
            List of chunks
        """
        if not separators:
            # No more separators to try, use fixed token splitting
            return self.token_counter.split_fixed(text, chunk_size, overlap)

        separator = separators[0]
        remaining_separators = separators[1:]

        # Try splitting on current separator
        if separator == "":
            # Last resort: character-level split
            return self.token_counter.split_fixed(text, chunk_size, overlap)

        splits = text.split(separator)

        # If no split occurred (separator not found), try next separator
        if len(splits) == 1 and separator not in [" ", ""]:
            return self._recursive_split(
                text, remaining_separators, chunk_size, overlap
            )

        # Process splits recursively
        chunks = []
        current_chunk = []
        current_tokens = 0

        for split in splits:
            split_tokens = self.token_counter.count(split)

            # Add separator token count if this isn't the first in chunk
            if current_chunk:
                split_tokens += self.token_counter.count(separator)

            # Check if adding this split fits within limits
            if current_tokens + split_tokens <= chunk_size:
                current_chunk.append(split)
                current_tokens += split_tokens
            else:
                # Current chunk is full, save it
                if current_chunk:
                    chunk_text = separator.join(current_chunk)
                    chunks.append(chunk_text)

                    # Start new chunk with overlap
                    if overlap > 0:
                        # Simplified overlap: keep last portion of previous chunk
                        # We'll handle this better by including part of the current split
                        pass

                # Start new chunk with this split
                current_chunk = [split]
                current_tokens = split_tokens

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = separator.join(current_chunk)
            chunks.append(chunk_text)

        # Merge small chunks
        chunks = self._merge_small_chunks(chunks, self.min_chunk_size, separator)

        # Check if any chunks are still too large
        final_chunks = []
        for chunk in chunks:
            chunk_token_count = self.token_counter.count(chunk)
            if chunk_token_count > self.max_chunk_size:
                # This chunk needs further splitting with next-level separators
                sub_chunks = self._recursive_split(
                    chunk, remaining_separators, chunk_size, overlap
                )
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)

        return final_chunks

    def _merge_small_chunks(
        self, chunks: List[str], min_size: int, separator: str
    ) -> List[str]:
        """Merge chunks that are smaller than min_size."""
        merged = []
        i = 0

        while i < len(chunks):
            current = chunks[i]
            current_tokens = self.token_counter.count(current)

            # If this chunk is too small and there's a next chunk to merge with
            if current_tokens < min_size and i + 1 < len(chunks):
                next_chunk = chunks[i + 1]
                combined = current + separator + next_chunk
                combined_tokens = self.token_counter.count(combined)

                # Only merge if combined doesn't exceed max size
                if combined_tokens <= self.max_chunk_size:
                    merged.append(combined)
                    i += 2  # Skip next chunk
                    continue

            merged.append(current)
            i += 1

        return merged


class MetadataGenerator:
    """Generate standardized metadata from raw source data."""

    # Mappings from raw source to standardized schema
    SOURCE_MAPPINGS = {
        "github_repos": {"source": "github_repo", "type": "readme"},
        "github_commits": {"source": "github_commit", "type": "commit_message"},
        "github_issues": {"source": "github_issue", "type": "issue_body"},
        "github_gists": {"source": "github_gist", "type": "gist_description"},
        "github_starred": {"source": "github_starred", "type": "starred_repo_info"},
        "web_blog": {"source": "blog", "type": "blog_post"},
        "web_forum": {"source": "forum", "type": "forum_post"},
        "web_personal": {"source": "website", "type": "webpage"},
        "web_linkedin": {"source": "linkedin", "type": "profile"},
        "web_twitter": {"source": "twitter", "type": "tweet"},
    }

    def generate(
        self,
        raw_doc: Dict[str, Any],
        source_type: str,
        chunk_index: int,
        total_chunks: int,
        token_count: int,
        text_length: int,
        chunk_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate standardized metadata for a chunk."""
        mapping = self.SOURCE_MAPPINGS.get(
            source_type, {"source": "unknown", "type": "unknown"}
        )

        if chunk_id is None:
            chunk_id = self._generate_chunk_id(
                source=mapping["source"],
                source_id=str(self._extract_source_id(raw_doc, source_type)),
                chunk_index=chunk_index,
            )

        metadata = {
            "chunk_id": chunk_id,
            "source": mapping["source"],
            "source_id": str(self._extract_source_id(raw_doc, source_type)),
            "url": self._extract_url(raw_doc, source_type),
            "date": self._extract_date(raw_doc, source_type),
            "type": mapping["type"],
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "token_count": token_count,
            "text_length": text_length,
        }

        # Optional fields
        optional_fields = {
            "title": self._extract_title(raw_doc, source_type),
            "author": self._extract_author(raw_doc, source_type),
            "tags": self._extract_tags(raw_doc, source_type),
            "language": self._extract_language(raw_doc, source_type),
            "repository": self._extract_repository(raw_doc, source_type),
        }

        # Only include non-None values
        metadata.update({k: v for k, v in optional_fields.items() if v is not None})

        return metadata

    def _generate_chunk_id(self, source: str, source_id: str, chunk_index: int) -> str:
        """Generate deterministic chunk ID."""
        return f"{source}:{source_id}:{chunk_index}"

    def _extract_source_id(self, raw_doc: Dict[str, Any], source_type: str) -> Any:
        """Extract unique source identifier."""
        if source_type.startswith("github"):
            if "full_name" in raw_doc:
                return raw_doc["full_name"]
            elif "sha" in raw_doc:
                return raw_doc["sha"][:12]
            elif "id" in raw_doc:
                return raw_doc["id"]
            elif "number" in raw_doc:
                return raw_doc["number"]
        elif source_type == "twitter":
            return raw_doc.get("username", "unknown")
        elif source_type == "linkedin":
            return raw_doc.get("username", raw_doc.get("url", "unknown").split("/")[-1])
        else:
            url = raw_doc.get("url", "")
            if "//" in url:
                path = (
                    url.split("//", 1)[-1].split("/", 1)[-1]
                    if "/" in url.split("//", 1)[-1]
                    else ""
                )
            else:
                path = url
            return path.replace("/", "_")[:100] if path else "unknown"

        return "unknown"

    def _extract_url(self, raw_doc: Dict[str, Any], source_type: str) -> str:
        """Extract permanent URL."""
        return raw_doc.get("url", "")

    def _extract_date(self, raw_doc: Dict[str, Any], source_type: str) -> str:
        """Extract ISO 8601 date."""
        for field in ["created_at", "date", "updated_at", "published"]:
            if field in raw_doc and raw_doc[field]:
                return raw_doc[field]
        return datetime.utcnow().isoformat()

    def _extract_title(
        self, raw_doc: Dict[str, Any], source_type: str
    ) -> Optional[str]:
        """Extract title if available."""
        return raw_doc.get("title")

    def _extract_author(
        self, raw_doc: Dict[str, Any], source_type: str
    ) -> Optional[str]:
        """Extract author/creator."""
        if source_type.startswith("github"):
            if "owner" in raw_doc and isinstance(raw_doc["owner"], dict):
                return raw_doc["owner"].get("login")
            elif "user" in raw_doc and isinstance(raw_doc["user"], dict):
                return raw_doc["user"].get("login")
        elif source_type in ["blog", "forum", "personal"]:
            return raw_doc.get("author")
        elif source_type == "linkedin":
            return raw_doc.get("name")
        elif source_type == "twitter":
            return raw_doc.get("display_name") or raw_doc.get("username")
        return None

    def _extract_tags(
        self, raw_doc: Dict[str, Any], source_type: str
    ) -> Optional[List[str]]:
        """Extract tags/keywords."""
        for field in ["tags", "labels", "topics", "skills"]:
            if field in raw_doc and raw_doc[field]:
                return raw_doc[field]
        return None

    def _extract_language(
        self, raw_doc: Dict[str, Any], source_type: str
    ) -> Optional[str]:
        """Extract programming language or content language."""
        if source_type.startswith("github"):
            return raw_doc.get("language")
        return None

    def _extract_repository(
        self, raw_doc: Dict[str, Any], source_type: str
    ) -> Optional[str]:
        """Extract repository name (for GitHub sources)."""
        if source_type.startswith("github"):
            if "repo" in raw_doc:
                return raw_doc["repo"]
            elif "full_name" in raw_doc:
                return raw_doc["full_name"]
        return None


class Preprocessor:
    """
    Main preprocessing pipeline for RAG document chunking.

    Integrates:
    - Text extraction from raw JSON
    - Text cleaning and normalization
    - Recursive chunking with token limits
    - Metadata generation
    - JSONL output
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 100,
        min_chunk_size: int = 100,
        max_chunk_size: int = 768,
        output_dir: Union[str, Path] = "data/processed",
    ):
        """
        Initialize preprocessor.

        Args:
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
            min_chunk_size: Minimum acceptable chunk size
            max_chunk_size: Maximum acceptable chunk size
            output_dir: Directory to save processed chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.token_counter = TokenCounter()
        self.text_cleaner = TextCleaner()
        self.splitter = RecursiveTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            token_counter=self.token_counter,
        )
        self.metadata_generator = MetadataGenerator()

    def process_file(
        self,
        input_path: Union[str, Path],
        source_type: str,
        content_field: str = "content",
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        Process a single raw JSON file into chunks.

        Args:
            input_path: Path to raw JSON file
            source_type: Source type identifier (maps to schema)
            content_field: Field name containing the main text content
            output_filename: Optional output filename (auto-generated if None)

        Returns:
            Path to output JSONL file
        """
        input_path = Path(input_path)

        # Load raw data
        logger.info(f"Loading raw data from {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            try:
                raw_docs = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {input_path}: {e}")
                raise

        if not isinstance(raw_docs, list):
            logger.warning(
                f"Expected list of documents in {input_path}, got {type(raw_docs)}"
            )
            raw_docs = [raw_docs] if raw_docs else []

        # Process each document
        all_chunks = []
        for raw_doc in raw_docs:
            chunks = self.process_document(raw_doc, source_type, content_field)
            all_chunks.extend(chunks)

        # Write output
        if output_filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{source_type}_chunks_{timestamp}.jsonl"

        output_path = self.output_dir / output_filename

        logger.info(f"Writing {len(all_chunks)} chunks to {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            for chunk in all_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        return output_path

    def process_document(
        self, raw_doc: Dict[str, Any], source_type: str, content_field: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        Process a single raw document into chunked documents with metadata.

        Args:
            raw_doc: Raw document dictionary from collector/scraper
            source_type: Source type identifier
            content_field: Field name containing the main text content

        Returns:
            List of chunk dictionaries with 'text' and 'metadata'
        """
        # Extract text content
        text = raw_doc.get(content_field, "")
        if not text:
            logger.warning(
                f"Document missing '{content_field}' field: {raw_doc.get('url', raw_doc.get('full_name', 'unknown'))}"
            )
            return []

        # Clean text
        preserve_code = source_type.startswith("github")
        cleaned_text = self.text_cleaner.clean(text, preserve_code=preserve_code)

        if not cleaned_text:
            logger.warning(
                f"Empty text after cleaning: {raw_doc.get('url', raw_doc.get('full_name', 'unknown'))}"
            )
            return []

        # Determine content type for chunking strategy
        content_type = self._infer_content_type(source_type)

        # Split into chunks
        chunk_texts = self.splitter.split_text(cleaned_text, content_type)

        if not chunk_texts:
            logger.warning(
                f"No chunks produced for document: {raw_doc.get('url', raw_doc.get('full_name', 'unknown'))}"
            )
            return []

        # Generate chunk metadata
        chunks = []
        for i, chunk_text in enumerate(chunk_texts):
            token_count = self.token_counter.count(chunk_text)
            text_length = len(chunk_text)

            metadata = self.metadata_generator.generate(
                raw_doc=raw_doc,
                source_type=source_type,
                chunk_index=i,
                total_chunks=len(chunk_texts),
                token_count=token_count,
                text_length=text_length,
            )

            chunk_doc = {"text": chunk_text, "metadata": metadata}
            chunks.append(chunk_doc)

        logger.debug(
            f"Split document into {len(chunks)} chunks (tokens: {[self.token_counter.count(c['text']) for c in chunks]})"
        )

        return chunks

    def _infer_content_type(self, source_type: str) -> str:
        """Infer content type from source type for chunking strategy."""
        # Map source types to content types
        if source_type.startswith("github"):
            if "commit" in source_type:
                return "commit_message"
            elif "issue" in source_type:
                return "issue_body"
            elif "pr" in source_type:
                return "pr_description"
            elif "gist" in source_type:
                return "gist_file"
            elif "starred" in source_type:
                return "starred_repo_info"
            else:  # github_repo
                return "code"  # Treat repos as code-heavy
        elif source_type == "blog":
            return "blog_post"
        elif source_type == "forum":
            return "forum_post"
        elif source_type == "twitter":
            return "tweet"
        elif source_type == "linkedin":
            return "profile"
        else:
            return "webpage"


def process_all_raw_files(
    raw_dir: Union[str, Path] = "data/raw",
    output_dir: Union[str, Path] = "data/processed",
    pattern: str = "*.json",
) -> List[Path]:
    """
    Process all raw JSON files in a directory.

    Args:
        raw_dir: Directory containing raw JSON files
        output_dir: Directory to save processed chunks
        pattern: Glob pattern for raw files

    Returns:
        List of output file paths
    """
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    preprocessor = Preprocessor(output_dir=str(output_dir))

    output_files = []

    for json_file in raw_dir.glob(pattern):
        # Determine source type from filename
        filename = json_file.stem

        # Map filename patterns to source types
        if "github_" in filename:
            source_type = filename.replace("github_", "").rstrip(
                "s"
            )  # github_repos -> repo
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
        elif "web_" in filename:
            source_type = filename
        else:
            logger.warning(f"Could not determine source type for {filename}, skipping")
            continue

        logger.info(f"Processing {json_file} as {source_type}")

        try:
            output_path = preprocessor.process_file(
                input_path=json_file,
                source_type=source_type,
                output_filename=f"{json_file.stem}_chunks.jsonl",
            )
            output_files.append(output_path)
        except Exception as e:
            logger.error(f"Error processing {json_file}: {e}")
            continue

    logger.info(f"Processed {len(output_files)} files")
    return output_files


def process_document(
    raw_doc: Dict[str, Any],
    source_type: str,
    output_dir: Union[str, Path] = "data/processed",
) -> List[Dict[str, Any]]:
    """
    Process a single document (not from file).

    Args:
        raw_doc: Raw document dictionary
        source_type: Source type identifier
        output_dir: Directory to optionally save output

    Returns:
        List of chunk dictionaries
    """
    preprocessor = Preprocessor(output_dir=str(output_dir))
    return preprocessor.process_document(raw_doc, source_type)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    output_files = process_all_raw_files(
        raw_dir="data/raw", output_dir="data/processed", pattern="*.json"
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Preprocessing complete. Generated {len(output_files)} chunk files:")
    for output_file in output_files:
        with open(output_file, "r") as f:
            line_count = sum(1 for _ in f)
        logger.info(f"  {output_file}: {line_count} chunks")
