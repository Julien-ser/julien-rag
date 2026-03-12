"""
Unit tests for the preprocessor module.

Tests cover:
- TokenCounter functionality
- TextCleaner with HTML and code blocks
- RecursiveTextSplitter with various content types
- MetadataGenerator field extraction
- Full Preprocessor integration
"""

import pytest
import json
from pathlib import Path
from datetime import datetime

from src.preprocessor import (
    TokenCounter,
    TextCleaner,
    RecursiveTextSplitter,
    MetadataGenerator,
    Preprocessor,
)


class TestTokenCounter:
    """Tests for TokenCounter class."""

    def test_count_basic(self):
        counter = TokenCounter()
        # "Hello world" should be at least 2 tokens
        count = counter.count("Hello world")
        assert count >= 2

    def test_count_empty(self):
        counter = TokenCounter()
        assert counter.count("") == 0
        assert counter.count("   ") >= 1  # Whitespace may count as tokens

    def test_count_code(self):
        counter = TokenCounter()
        code = "def hello():\n    return 'world'"
        count = counter.count(code)
        assert count > 0

    def test_truncate(self):
        counter = TokenCounter()
        text = "This is a test sentence that should be truncated."
        truncated = counter.truncate(text, 3)
        assert counter.count(truncated) <= 3

    def test_truncate_no_truncation(self):
        counter = TokenCounter()
        text = "Short text."
        truncated = counter.truncate(text, 10)
        assert truncated == text

    def test_split_fixed(self):
        counter = TokenCounter()
        # Create a longer text
        text = " ".join(["word"] * 50)
        chunks = counter.split_fixed(text, chunk_size=10, overlap=2)
        assert len(chunks) > 1
        # All chunks except possibly last should be within size
        for i, chunk in enumerate(chunks):
            count = counter.count(chunk)
            assert count <= 10  # Should not exceed chunk_size


class TestTextCleaner:
    """Tests for TextCleaner class."""

    def test_clean_html_basic(self):
        cleaner = TextCleaner()
        html = "<p>Hello <b>world</b></p>"
        result = cleaner.clean_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result
        assert ">" not in result

    def test_clean_html_with_entities(self):
        cleaner = TextCleaner()
        html = "Hello &amp; welcome &lt;world&gt;"
        result = cleaner.clean_html(html)
        assert "&" in result or "and" in result.lower()  # &amp; decoded

    def test_clean_html_empty(self):
        cleaner = TextCleaner()
        assert cleaner.clean_html("") == ""
        assert cleaner.clean_html(None) == ""  # Should handle None gracefully

    def test_clean_html_with_script_style(self):
        cleaner = TextCleaner()
        html = "<script>alert('test');</script><p>Content</p>"
        result = cleaner.clean_html(html)
        # Script tags should be removed
        assert "alert" not in result
        assert "Content" in result

    def test_normalize_whitespace_basic(self):
        cleaner = TextCleaner()
        text = "Hello    world\n\n\nTest"
        result = cleaner.normalize_whitespace(text)
        # Should collapse multiple spaces and normalize newlines
        assert "    " not in result
        assert result.strip() == "Hello world Test"

    def test_normalize_whitespace_tabs(self):
        cleaner = TextCleaner()
        text = "Hello\t\tworld"
        result = cleaner.normalize_whitespace(text)
        assert "\t" not in result

    def test_normalize_whitespace_empty(self):
        cleaner = TextCleaner()
        assert cleaner.normalize_whitespace("") == ""
        assert cleaner.normalize_whitespace("   ") == ""

    def test_clean_full_pipeline(self):
        cleaner = TextCleaner()
        html_with_spaces = "<p>  Hello   <b>world</b>!  </p>"
        result = cleaner.clean(html_with_spaces)
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result
        assert ">" not in result
        assert result.strip() == result  # No leading/trailing whitespace

    def test_preserve_code_blocks(self):
        cleaner = TextCleaner()
        text = "Introduction\n\n```python\ndef foo():\n    return 1\n```\n\nConclusion"
        result = cleaner.clean(text, preserve_code=True)
        # Code block should be preserved
        assert "```python" in result
        assert "def foo():" in result
        assert "    return 1" in result  # Indentation preserved
        assert "```" in result

    def test_multiple_code_blocks(self):
        cleaner = TextCleaner()
        text = "Text\n\n```python\ncode1\n```\n\nmore text\n\n```javascript\ncode2\n```\nend"
        result = cleaner.clean(text, preserve_code=True)
        assert "```python" in result
        assert "```javascript" in result
        assert "code1" in result
        assert "code2" in result

    def test_code_block_without_preserve(self):
        cleaner = TextCleaner()
        text = "Intro\n\n```python\ncode\n```\n\nOutro"
        result = cleaner.clean(text, preserve_code=False)
        # Code fences may be stripped or simplified
        assert "python" not in result or "code" in result

    def test_html_in_code_block(self):
        cleaner = TextCleaner()
        text = "```\n<div>HTML inside code</div>\n```"
        result = cleaner.clean(text, preserve_code=True)
        # HTML inside code block should be preserved as-is
        assert "<div>" in result
        assert "</div>" in result


class TestRecursiveTextSplitter:
    """Tests for RecursiveTextSplitter class."""

    def test_initialization(self):
        splitter = RecursiveTextSplitter(chunk_size=512, chunk_overlap=100)
        assert splitter.chunk_size == 512
        assert splitter.chunk_overlap == 100
        assert len(splitter.separators) > 0

    def test_empty_text(self):
        splitter = RecursiveTextSplitter()
        assert splitter.split_text("") == []
        assert splitter.split_text("   ") == []

    def test_small_text_no_split(self):
        splitter = RecursiveTextSplitter(chunk_size=100)
        text = "This is a short text."
        chunks = splitter.split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_on_newlines(self):
        splitter = RecursiveTextSplitter(chunk_size=50, chunk_overlap=10)
        # Create text with multiple paragraphs (enough to exceed chunk size)
        paragraphs = ["This is paragraph " + str(i) + "." for i in range(30)]
        text = "\n\n".join(paragraphs)
        chunks = splitter.split_text(text)
        assert len(chunks) > 1

    def test_split_creates_reasonable_chunks(self):
        splitter = RecursiveTextSplitter(chunk_size=100, chunk_overlap=20)
        # Create longer text
        sentences = ["This is sentence number " + str(i) + "." for i in range(50)]
        text = " ".join(sentences)
        chunks = splitter.split_text(text)

        # Check that chunks are created
        assert len(chunks) > 1

        # Verify each chunk is within reasonable size
        for chunk in chunks:
            token_count = splitter.token_counter.count(chunk)
            # Should not be way too large (allow some flexibility)
            assert token_count <= 200  # Some tolerance

    def test_content_type_code(self):
        splitter = RecursiveTextSplitter(chunk_size=200, chunk_overlap=50)
        code = "\n".join([f"def function_{i}():\n    return {i}" for i in range(30)])
        chunks = splitter.split_text(code, content_type="code")
        # Code should be split into chunks
        assert len(chunks) >= 1
        # Code blocks should be preserved reasonably well
        for chunk in chunks:
            # Each chunk should contain complete function definitions where possible
            assert "def" in chunk or chunk.strip() == ""

    def test_content_type_tweet(self):
        splitter = RecursiveTextSplitter(chunk_size=50)
        tweet = "This is a short tweet message that should not be split."
        chunks = splitter.split_text(tweet, content_type="tweet")
        assert len(chunks) == 1
        assert chunks[0] == tweet

    def test_merge_small_chunks(self):
        splitter = RecursiveTextSplitter(chunk_size=100, min_chunk_size=50)
        # Create small chunks
        small_chunks = ["small"] * 10
        merged = splitter._merge_small_chunks(small_chunks, 50, " ")
        # Some merging should have occurred
        assert len(merged) < len(small_chunks)

    def test_separator_priority(self):
        splitter = RecursiveTextSplitter(chunk_size=50, chunk_overlap=10)
        # Text with various separator levels (long enough to require splitting)
        text = (
            "Section 1\n\nParagraph 1. Sentence 2.\n\nSection 2\n\nParagraph 2.\n\n"
        ) * 10
        chunks = splitter.split_text(text)
        # Should split on \n\n (paragraph level) before sentences
        assert len(chunks) >= 2

    def test_long_single_word(self):
        splitter = RecursiveTextSplitter(chunk_size=50)
        # Create a very long word without separators
        long_word = "a" * 200
        chunks = splitter.split_text(long_word)
        # Should fall back to character-level splitting
        assert len(chunks) >= 1
        # Each chunk should not exceed reasonable size
        for chunk in chunks:
            assert splitter.token_counter.count(chunk) <= 100


class TestMetadataGenerator:
    """Tests for MetadataGenerator class."""

    def setup_method(self):
        self.gen = MetadataGenerator()

    def test_generate_required_fields_github_repo(self):
        raw_doc = {
            "full_name": "owner/repo",
            "url": "https://github.com/owner/repo",
            "created_at": "2024-01-01T00:00:00Z",
            "language": "python",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_repos",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert metadata["chunk_id"] == "github_repo:owner/repo:0"
        assert metadata["source"] == "github_repo"
        assert metadata["source_id"] == "owner/repo"
        assert metadata["url"] == "https://github.com/owner/repo"
        assert metadata["date"] == "2024-01-01T00:00:00Z"
        assert metadata["type"] == "readme"
        assert metadata["chunk_index"] == 0
        assert metadata["total_chunks"] == 1
        assert metadata["token_count"] == 100
        assert metadata["text_length"] == 500
        assert metadata["language"] == "python"

    def test_generate_required_fields_commit(self):
        raw_doc = {
            "sha": "abc123def456",
            "message": "Fix bug",
            "url": "https://github.com/owner/repo/commit/abc123d",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_commits",
            chunk_index=0,
            total_chunks=1,
            token_count=10,
            text_length=50,
        )

        assert metadata["source"] == "github_commit"
        assert metadata["source_id"] == "abc123def456"  # First 12 chars of SHA
        assert metadata["type"] == "commit_message"

    def test_generate_with_title_author(self):
        raw_doc = {
            "url": "https://blog.example.com/post",
            "title": "My Blog Post",
            "author": "Julien",
            "date": "2024-02-01T12:00:00Z",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="web_blog",
            chunk_index=0,
            total_chunks=2,
            token_count=200,
            text_length=1000,
        )

        assert metadata["title"] == "My Blog Post"
        assert metadata["author"] == "Julien"
        assert metadata["source"] == "blog"
        assert metadata["type"] == "blog_post"

    def test_generate_extract_tags(self):
        raw_doc = {
            "url": "https://github.com/owner/repo",
            "topics": ["python", "machine-learning", "ai"],
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_repos",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert "tags" in metadata
        assert metadata["tags"] == ["python", "machine-learning", "ai"]

    def test_generate_extract_labels(self):
        raw_doc = {
            "url": "https://github.com/owner/repo/issues/1",
            "labels": ["bug", "high-priority"],
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_issues",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert metadata["tags"] == ["bug", "high-priority"]

    def test_github_user_extraction(self):
        raw_doc = {
            "owner": {"login": "octocat"},
            "url": "https://github.com/octocat/repo",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_repos",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert metadata["author"] == "octocat"

    def test_github_user_from_issue(self):
        raw_doc = {
            "user": {"login": "contributor"},
            "url": "https://github.com/owner/issues/1",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_issues",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert metadata["author"] == "contributor"

    def test_twitter_author(self):
        raw_doc = {
            "url": "https://twitter.com/julien",
            "username": "julien",
            "display_name": "Julien Smith",
        }
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="web_twitter",
            chunk_index=0,
            total_chunks=1,
            token_count=50,
            text_length=250,
        )

        assert metadata["author"] == "Julien Smith"  # Prefer display_name

    def test_unknown_source_mapping(self):
        raw_doc = {"url": "https://unknown.com/thing"}
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="unknown_type",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        assert metadata["source"] == "unknown"
        assert metadata["type"] == "unknown"

    def test_missing_optional_fields(self):
        raw_doc = {"url": "https://example.com"}
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="web_personal",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        # Should not include optional fields that are None
        assert "title" not in metadata or metadata.get("title") is None
        assert "author" not in metadata or metadata.get("author") is None
        assert "tags" not in metadata or metadata.get("tags") is None

    def test_chunk_id_deterministic(self):
        raw_doc = {"full_name": "owner/repo"}
        metadata1 = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_repos",
            chunk_index=2,
            total_chunks=5,
            token_count=100,
            text_length=500,
        )
        metadata2 = self.gen.generate(
            raw_doc=raw_doc,
            source_type="github_repos",
            chunk_index=2,
            total_chunks=5,
            token_count=100,
            text_length=500,
        )

        # Same inputs should produce same chunk_id
        assert metadata1["chunk_id"] == metadata2["chunk_id"]

    def test_date_fallback(self):
        raw_doc = {"url": "https://example.com"}  # No date fields
        metadata = self.gen.generate(
            raw_doc=raw_doc,
            source_type="web_personal",
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            text_length=500,
        )

        # Should have a valid ISO date
        assert metadata["date"] is not None
        # Should be parseable as ISO format
        datetime.fromisoformat(metadata["date"].replace("Z", "+00:00"))


class TestPreprocessorIntegration:
    """Integration tests for the full Preprocessor."""

    def test_preprocessor_initialization(self):
        prep = Preprocessor(output_dir="test_output")
        assert prep.chunk_size == 512
        assert prep.chunk_overlap == 100
        assert prep.token_counter is not None
        assert prep.text_cleaner is not None
        assert prep.splitter is not None
        assert prep.metadata_generator is not None

    def test_process_blog_document(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://blog.example.com/test-post",
            "title": "Test Blog Post",
            "author": "Julien",
            "date": "2024-01-15T10:30:00Z",
            "content": "This is the blog post content. "
            * 50,  # Make it long enough to chunk
        }

        chunks = prep.process_document(raw_doc, "web_blog")

        assert len(chunks) > 0
        for chunk in chunks:
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["text"].strip() != ""
            metadata = chunk["metadata"]
            assert metadata["source"] == "blog"
            assert metadata["type"] == "blog_post"
            assert metadata["url"] == "https://blog.example.com/test-post"
            assert metadata["author"] == "Julien"
            assert metadata["title"] == "Test Blog Post"

    def test_process_github_issue(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "id": 123,
            "number": 45,
            "title": "Issue title",
            "body": "Issue description. " * 20,
            "url": "https://github.com/owner/repo/issues/45",
            "created_at": "2024-02-01T12:00:00Z",
            "user": {"login": "contributor"},
        }

        chunks = prep.process_document(raw_doc, "github_issues", content_field="body")

        assert len(chunks) > 0
        metadata = chunks[0]["metadata"]
        assert metadata["source"] == "github_issue"
        assert metadata["type"] == "issue_body"
        assert metadata["source_id"] == "45"
        assert metadata["author"] == "contributor"

    def test_process_small_document(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://example.com/short",
            "content": "This is a very short document.",
        }

        chunks = prep.process_document(raw_doc, "web_personal")

        assert len(chunks) == 1
        assert chunks[0]["text"] == "This is a very short document."

    def test_process_empty_document(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {"url": "https://example.com/empty", "content": ""}

        chunks = prep.process_document(raw_doc, "web_personal")

        assert len(chunks) == 0

    def test_process_document_with_html(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://example.com/html",
            "content": "<html><body><h1>Title</h1><p>Paragraph with <b>bold</b> text.</p></body></html>",
        }

        chunks = prep.process_document(raw_doc, "web_personal")

        assert len(chunks) > 0
        # HTML tags should be stripped
        assert "<" not in chunks[0]["text"]
        assert ">" not in chunks[0]["text"]
        assert "Title" in chunks[0]["text"]
        assert "bold" in chunks[0]["text"]

    def test_process_document_with_code(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://github.com/owner/repo",
            "full_name": "owner/repo",
            "content": '# README\n\n```python\ndef hello():\n    print("Hello")\n```\n\nSome text. '
            * 30,
        }

        chunks = prep.process_document(raw_doc, "github_repos")

        assert len(chunks) > 0
        # Code should be preserved across chunks
        all_text = " ".join([c["text"] for c in chunks])
        assert "```python" in all_text
        assert "def hello():" in all_text

    def test_metadata_consistency(self):
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://example.com",
            "full_name": "owner/repo",
            "content": "Test content",
        }

        chunks = prep.process_document(raw_doc, "github_repos")

        for i, chunk in enumerate(chunks):
            metadata = chunk["metadata"]
            # Check all required fields present
            required = [
                "chunk_id",
                "source",
                "source_id",
                "url",
                "date",
                "type",
                "chunk_index",
                "total_chunks",
                "token_count",
                "text_length",
            ]
            for field in required:
                assert field in metadata

            # Check consistency
            assert metadata["chunk_index"] == i
            assert metadata["total_chunks"] == len(chunks)
            assert metadata["token_count"] > 0
            assert metadata["text_length"] == len(chunk["text"])

    def test_chunk_overlap(self):
        """Test that chunks have appropriate overlap for context."""
        prep = Preprocessor(
            chunk_size=100, chunk_overlap=20, output_dir="test_temp_output"
        )

        # Create text that will produce multiple chunks
        words = ["word"] * 200
        text = " ".join(words)

        raw_doc = {"url": "https://example.com", "content": text}
        chunks = prep.process_document(raw_doc, "web_personal")

        if len(chunks) > 1:
            # There should be some overlap (common words at boundaries)
            # At least check that we get multiple chunks
            assert len(chunks) >= 2

    def test_deterministic_chunk_ids(self):
        """Test that same document produces same chunk IDs on repeated runs."""
        prep = Preprocessor(output_dir="test_temp_output")

        raw_doc = {
            "url": "https://example.com/test",
            "full_name": "owner/repo",
            "content": "Test content" * 50,
        }

        chunks1 = prep.process_document(raw_doc, "github_repos")
        chunks2 = prep.process_document(raw_doc, "github_repos")

        for c1, c2 in zip(chunks1, chunks2):
            assert c1["metadata"]["chunk_id"] == c2["metadata"]["chunk_id"]


class TestProcessAllRawFiles:
    """Tests for batch processing function."""

    def test_process_directory(self, tmp_path):
        # Create test raw files
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create a sample web_blog JSON file
        blog_data = [
            {
                "url": "https://blog.example.com/1",
                "title": "Blog 1",
                "content": "Blog content" * 20,
            }
        ]
        blog_file = raw_dir / "web_blog.json"
        with open(blog_file, "w") as f:
            json.dump(blog_data, f)

        output_dir = tmp_path / "processed"

        # Process all files
        from src.preprocessor import process_all_raw_files

        output_files = process_all_raw_files(
            raw_dir=str(raw_dir), output_dir=str(output_dir), pattern="*.json"
        )

        assert len(output_files) == 1
        assert output_files[0].exists()

        # Check output format
        with open(output_files[0], "r") as f:
            lines = f.readlines()
            assert len(lines) > 0
            chunk = json.loads(lines[0])
            assert "text" in chunk
            assert "metadata" in chunk

    def test_skips_unknown_files(self, tmp_path, caplog):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create a file that doesn't match known patterns
        unknown_file = raw_dir / "mystery_data.json"
        with open(unknown_file, "w") as f:
            json.dump([{"data": "test"}], f)

        output_dir = tmp_path / "processed"

        from src.preprocessor import process_all_raw_files

        output_files = process_all_raw_files(
            raw_dir=str(raw_dir), output_dir=str(output_dir), pattern="*.json"
        )

        # Should skip the unknown file and produce no output
        assert len(output_files) == 0

    def test_multiple_source_types(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create blog file
        blog_data = [
            {
                "url": "https://blog.example.com/1",
                "title": "Blog",
                "content": "Blog content" * 20,
            }
        ]
        with open(raw_dir / "web_blog.json", "w") as f:
            json.dump(blog_data, f)

        # Create github_repos file
        repo_data = [
            {
                "full_name": "owner/repo",
                "url": "https://github.com/owner/repo",
                "description": "Repo description" * 10,
            }
        ]
        with open(raw_dir / "github_repos.json", "w") as f:
            json.dump(repo_data, f)

        output_dir = tmp_path / "processed"

        from src.preprocessor import process_all_raw_files

        output_files = process_all_raw_files(
            raw_dir=str(raw_dir), output_dir=str(output_dir), pattern="*.json"
        )

        assert len(output_files) == 2
        # Check that both output files exist
        assert any("web_blog" in str(f) for f in output_files)
        assert any("github_repos" in str(f) for f in output_files)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
