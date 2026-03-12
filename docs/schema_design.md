# Data Schema and Document Structure Design

## Overview

This document defines the data schema, document chunking strategy, and embedding configuration for the julien-rag project. The design supports heterogeneous data sources (GitHub, web content) while maintaining consistency for vector storage and retrieval.

---

## 1. Document Metadata Schema

### 1.1 Core Metadata Fields

Every document chunk stored in ChromaDB will include the following metadata fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chunk_id` | string | Yes | Unique identifier: `{source}:{source_id}:{chunk_index}` |
| `source` | string | Yes | Data source type (see section 1.2) |
| `source_id` | string | Yes | Unique identifier from the original source |
| `url` | string | Yes | Permanent URL/link to the original content |
| `date` | string | Yes | ISO 8601 date/time when content was created |
| `type` | string | Yes | Content type/category (see section 1.3) |
| `title` | string | No | Title of the document (if available) |
| `author` | string | No | Author/creator username or name |
| `tags` | list[string] | No | Keywords/tags associated with the content |
| `language` | string | No | Programming language (for code) or content language |
| `repository` | string | No | Repository name in format `owner/repo` (GitHub only) |
| `chunk_index` | int | Yes | Index of this chunk within the parent document |
| `total_chunks` | int | Yes | Total number of chunks for this document |
| `token_count` | int | Yes | Number of tokens in this chunk |
| `text_length` | int | Yes | Character length of the chunk text |

### 1.2 Source Types

Valid values for the `source` field:

| Source | Description | Example `source_id` |
|--------|-------------|---------------------|
| `github_repo` | GitHub repository metadata (README, description) | `octocat/hello-world` |
| `github_commit` | Individual commit | `a1b2c3d` (commit SHA) |
| `github_issue` | GitHub issue (open or closed) | `123` (issue number) |
| `github_pr` | GitHub pull request | `456` (PR number) |
| `github_gist` | GitHub gist | `abc123` (gist ID) |
| `github_starred` | Starred repository | `octocat/hello-world` |
| `website` | Personal website page | `about` |
| `blog` | Blog post/article | `2024-01-15-my-post` |
| `forum` | Forum post/thread | `thread-9876` |
| `twitter` | Twitter/X post | `1234567890123456789` |
| `linkedin` | LinkedIn profile/post | `profile-12345` |

### 1.3 Content Types

Valid values for the `type` field:

| Type | Description | Applicable Sources |
|------|-------------|-------------------|
| `readme` | Repository README file | github_repo |
| `code` | Source code file content | github_repo |
| `commit_message` | Git commit message | github_commit |
| `commit_diff` | Code diff from commit | github_commit |
| `issue_body` | Issue description | github_issue |
| `issue_comment` | Comment on issue | github_issue |
| `pr_description` | PR description | github_pr |
| `pr_comment` | Comment on PR | github_pr |
| `gist_description` | Gist description | github_gist |
| `gist_file` | Individual file in gist | github_gist |
| `starred_repo_info` | Metadata about starred repo | github_starred |
| `webpage` | General web page content | website, blog, forum |
| `blog_post` | Blog article/post | blog |
| `forum_post` | Forum message/thread | forum |
| `tweet` | Twitter/X post | twitter |
| `profile` | Social media profile | linkedin |
| `unknown` | Fallback for unclassified content | any |

---

## 2. Chunking Strategy

### 2.1 Philosophy

Given the heterogeneous content types (code, markdown, plain text, forum posts), we need a flexible chunking approach that:
- Preserves semantic coherence where possible
- Handles code blocks appropriately (minimize splitting in the middle of functions/classes)
- Creates chunks of consistent size for embedding generation
- Maintains sufficient overlap to preserve context across chunk boundaries

### 2.2 Primary Strategy: Recursive Character Splitting with Semantic Awareness

We will use ** recursive text splitting** with the following characteristics:

#### Configuration Parameters

```yaml
chunking:
  strategy: "recursive_character"
  
  # Delimiters in order of priority (higher priority = try to split on these first)
  separators: [
    "\n\n\n",  # Triple newline (major section breaks)
    "\n\n",    # Double newline (paragraphs, code block separation)
    "\n",      # Single newline (code lines, list items)
    ". ",      # Sentence boundary
    "! ",      # Sentence boundary
    "? ",      # Sentence boundary
    "; ",      # Clause boundary
    ", ",      # Phrase boundary
    " ",        # Word boundary (last resort)
    ""          # Character boundary (fallback)
  ]
  
  # Target chunk size in tokens
  chunk_size: 512
  
  # Overlap between consecutive chunks (in tokens)
  chunk_overlap: 100
  
  # Minimum chunk size (chunks smaller than this are merged with previous)
  min_chunk_size: 100
  
  # Maximum chunk size (chunks larger than this are split)
  max_chunk_size: 768
```

#### How It Works

1. **Preprocessing**: For each document, extract clean text and preserve structural markers (markdown headers, code fences, indentation).

2. **Recursive Splitting**:
   - Start with the full text
   - Try to split on the first separator in the list
   - If resulting pieces are still larger than `chunk_size`, recursively split those pieces using the next separator
   - Continue until all pieces are ≤ `max_chunk_size`

3. **Overlap Generation**:
   - When a chunk is created, the next chunk starts `chunk_size - chunk_overlap` tokens into the previous chunk
   - This ensures 100 tokens of shared context between adjacent chunks
   - Overlap helps with retrieval: relevant content near chunk boundaries won't be missed

4. **Code-Aware Processing**:
   - Detect code blocks (fenced with ` ``` ` or indented)
   - Prefer splitting at code block boundaries to avoid mid-function splits
   - For very large code files (> 3KB), split at logical boundaries (functions, classes) using additional heuristics

### 2.3 Alternative: Fixed-Size Token Splitting

For content without clear semantic boundaries (e.g., log files, plain text), we may fall back to:

```yaml
chunking:
  strategy: "fixed_token"
  chunk_size: 512
  chunk_overlap: 100
  encoding: "cl100k_base"  # tokenizer for OpenAI embeddings
```

This simply splits text into fixed-size token windows without regard for structure.

### 2.4 Special Handling by Content Type

| Content Type | Strategy | Chunk Size | Overlap | Notes |
|--------------|----------|-------------|---------|-------|
| `code` | recursive + special code detection | 768 | 150 | Larger chunks to capture function context, higher overlap |
| `readme` | recursive (markdown-aware) | 512 | 100 | Preserve markdown headings |
| `commit_message` | no chunking (small) | - | - | Store as single chunk |
| `issue_body` | recursive | 512 | 100 | Include comments as separate chunks linked to issue |
| `blog_post` | recursive (paragraph-aware) | 512 | 100 | Prefer paragraph boundaries |
| `forum_post` | recursive | 512 | 100 | May need thread-level grouping |
| `tweet` | no chunking | - | - | Single tweet per chunk |
| `webpage` | recursive | 512 | 100 | Distill main content, remove nav/ads/scripts |

---

## 3. Embedding Configuration

### 3.1 Recommended Model: `sentence-transformers/all-MiniLM-L6-v2`

**Why this model:**
- **Free & Local**: No API costs, runs offline, no rate limits
- **Fast**: 384-dimensional embeddings, optimized for CPU
- **Good Quality**: Trained on massive dataset, strong semantic search performance
- **Size**: Only ~80MB, easy to distribute
- **Compatibility**: Works with all standard vector distance metrics (cosine, L2, dot)

**Specs:**
- Dimensions: 384
- Max sequence length: 512 tokens
- Model type: BERT-based (all-MiniLM-L6-v2)
- Storage: `models/all-MiniLM-L6-v2/` (cached after first download)

**Usage:**
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)
```

### 3.2 Alternative: OpenAI `text-embedding-ada-002`

Use if higher quality embeddings are needed and you have API budget.

**Specs:**
- Dimensions: 1536
- Max sequence length: 8192 tokens
- Pricing: $0.00010 per 1K tokens (~$0.10 per 1M tokens)
- Rate limit: 3000 requests/min

**Usage:**
```python
import openai
response = openai.Embedding.create(
    model="text-embedding-ada-002",
    input=texts
)
embeddings = [item.embedding for item in response.data]
```

**Note**: OpenAI model truncates at 8192 tokens, so documents must be chunked appropriately.

### 3.3 Embedding Storage Format

In ChromaDB, embeddings will be stored as float32 NumPy arrays:
- OpenAI: 1536-dimensional float32 array
- MiniLM: 384-dimensional float32 array

The embedding model choice is stored in `config/embeddings.yaml` and embedded in the ChromaDB collection metadata for future compatibility.

---

## 4. ChromaDB Collection Configuration

### 4.1 Collections

We will maintain three collections:

| Collection Name | Purpose | Content Sources |
|-----------------|---------|-----------------|
| `github_docs` | All GitHub-derived content | Repos, commits, issues, PRs, gists, starred |
| `web_content` | Web scraped content | Websites, blogs, forums, social media |
| `combined` | Unified search across all sources | Union of both collections (read-only) |

The `combined` collection is created as a **virtual collection** (query-only) that searches across both source collections and merges results, avoiding data duplication.

### 4.2 Collection Settings (ChromaDB)

**Configuration:**
```python
{
    "metadata": {
        "hnsw:space": "cosine",  # cosine similarity metric
        "hnsw:M": 16,            # Number of graph connections per node
        "hnsw:construction_ef": 200,  # Size of dynamic candidate list during index construction
        "hnsw:search_ef": 100,   # Size of dynamic candidate list during search
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "created_at": "2026-03-12T00:00:00Z",
        "description": "julien-rag vector database for personal RAG system"
    }
}
```

**HNSW Parameters Explained:**
- `space: "cosine"` - Use cosine similarity (normalize embeddings)
- `M: 16` - Higher values increase recall but use more memory (16 is default)
- `construction_ef: 200` - Higher = better recall, slower indexing (default 100)
- `search_ef: 100` - Higher = better recall, slower queries (default 50)

These parameters are tuned for moderate-scale datasets (<100K vectors) with a balance of recall vs speed.

---

## 5. Data Flow and Processing Pipeline

### 5.1 End-to-End Flow

```
Raw Data Sources
      ↓
[Collection Layer]
  - github_collector.py
  - web_scraper.py
      ↓
Raw JSON/HTML files (data/raw/)
      ↓
[Preprocessing Layer]
  - preprocessor.py
  - extract_text() → clean text
  - chunk_documents() → chunks with overlap
  - create_metadata() → enriched metadata
      ↓
Processed chunks (data/processed/chunks.jsonl)
      ↓
[Embedding Layer]
  - embedder.py
  - batch_embed(chunks, batch_size=32)
      ↓
Embeddings + chunks + metadata
      ↓
[Storage Layer]
  - vector_store.py
  - add_documents(collection, chunks, embeddings, metadata)
      ↓
ChromaDB (data/vector_db/)
```

### 5.2 Idempotency and Updates

To support incremental updates:

1. Each `chunk_id` is deterministic based on:
   ```
   chunk_id = f"{source}:{source_id}:{chunk_index}"
   ```
   This means re-running the pipeline with the same source data will produce identical chunk IDs.

2. ChromaDB's `upsert` operation:
   - If `chunk_id` already exists, update the embedding and metadata
   - If `chunk_id` is new, insert new document
   - No need to delete and recreate collections

3. To detect deleted sources:
   - Maintain a manifest of processed `source_id`s per source type
   - On each run, compare with current source data
   - If a source is no longer present, optionally delete its chunks (soft delete or hard delete)

---

## 6. Tokenization and Counting

### 6.1 Tokenizer Choice

- **OpenAI embeddings**: Use `tiktoken` with encoding `"cl100k_base"`
- **Sentence Transformers**: Use model's built-in tokenizer (from `transformers` library)

Token counts are stored in metadata (`token_count`) for monitoring and debugging.

### 6.2 Chunk Size Rationale

- **512 tokens** chosen as default because:
  - Fits comfortably in most embedding models' context windows (including ada-002's 8192 and MiniLM's 512)
  - ~1-2 paragraphs of text or a small code function
  - Produces embeddings that capture local context without being too broad
  - Efficient for storage and retrieval

- **100 token overlap** (≈20% of chunk size):
  - Sufficient to avoid cutting sentences/statements in half
  - Provides continuity between adjacent chunks
  - Minimal storage overhead (20%)

- **768 tokens** for code:
  - Code often requires more context (e.g., entire functions, class definitions)
  - Allows inclusion of docstrings and related methods

---

## 7. Querying and Retrieval Specifications

### 7.1 Search Parameters

```python
def search(
    query: str,
    k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    collection: str = "combined"
) -> List[SearchResult]:
    """
    Search for relevant document chunks.
    
    Args:
        query: Natural language query string
        k: Number of results to return (must be ≤ collection count)
        filters: Optional metadata filters, e.g.:
            {"source": "github_issue", "date": {"$gte": "2024-01-01"}}
        collection: Which collection to search ("combined", "github_docs", "web_content")
    
    Returns:
        List of SearchResult with fields:
            - chunk_id
            - content (text)
            - metadata (dict)
            - distance (float, 0-1, lower is more similar)
            - similarity_score (1 - distance)
    """
```

### 7.2 Metadata Filtering

ChromaDB supports metadata filtering with operators:

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equals | `{"source": "github_repo"}` |
| `$ne` | Not equals | `{"source": {"$ne": "twitter"}}` |
| `$in` | In list | `{"type": {"$in": ["readme", "code"]}}` |
| `$nin` | Not in list | `{"type": {"$nin": ["tweet"]}}` |
| `$gt` | Greater than | `{"date": {"$gt": "2024-01-01"}}` |
| `$gte` | Greater than or equal | `{"date": {"$gte": "2024-01-01"}}` |
| `$lt` | Less than | `{"date": {"$lt": "2025-01-01"}}` |
| `$lte` | Less than or equal | `{"date": {"$lte": "2025-01-01"}}` |

Filters combine with **AND** logic.

### 7.3 Expected Query Latency

With HNSW configuration above:
- **p50 latency**: < 50ms for k=10
- **p95 latency**: < 150ms for k=10
- **p99 latency**: < 300ms for k=10

Measured on modern CPU (Intel i5/i7 or equivalent) with <100K vectors.

---

## 8. Data Integrity and Validation

### 8.1 Schema Validation

All chunks written to the database must pass validation:

```python
REQUIRED_FIELDS = [
    'chunk_id', 'source', 'source_id', 'url', 'date',
    'type', 'chunk_index', 'total_chunks', 'token_count',
    'text_length'
]

VALID_SOURCES = {...}  # from section 1.2
VALID_TYPES = {...}    # from section 1.3
```

Reject any document missing required fields or containing invalid enum values.

### 8.2 Deduplication

- `chunk_id` uniqueness enforced by ChromaDB primary key
- If duplicate `chunk_id` is detected during upsert, the new version overwrites the old
- This allows re-running pipeline to update changed documents

### 8.3 Data Size Expectations

For a typical developer with 5 years of activity:

| Source | Estimated Documents | Est. Storage (embeddings + text) |
|--------|---------------------|----------------------------------|
| GitHub repos (code + READMEs) | 50 repos × 50 files = 2,500 | ~200 MB |
| GitHub commits | 5 years × 2/day × 365 = 3,650 | ~100 MB |
| GitHub issues/PRs | 500 total | ~50 MB |
| GitHub gists | 100 | ~20 MB |
| Starred repos | 1,000 | ~80 MB |
| Web content (blog, forums) | 200 posts/pages | ~40 MB |
| Social media (tweets, etc.) | 5,000 | ~100 MB |
| **Total** | **~13,000 documents** | **~600 MB** |

With 384-dimensional embeddings (4 bytes per dimension):
- Embeddings alone: 13,000 × 384 × 4 bytes ≈ 20 MB
- Text storage dominates (compressed in ChromaDB)

---

## 9. Future Enhancements

These are out of scope for initial implementation but documented for later:

1. **Hybrid Search**: Combine vector + keyword search (BM25) for exact term matching
2. **Multi-modal**: Support images (screenshots, diagrams) with CLIP embeddings
3. **Reranking**: Use cross-encoder models to rerank top-k results
4. **Query Expansion**: Automatically expand queries with synonyms or related terms
5. **Adaptive Chunking**: Dynamically adjust chunk size based on content type and density
6. **Versioning**: Track chunk versions when source documents change
7. **Anonymization**: Option to redact personal information before storage

---

## 10. Implementation Checklist

- [ ] Define Python data classes for metadata in `src/models.py`
- [ ] Implement `preprocessor.py` with recursive text splitter
- [ ] Configure tokenizer (tiktoken for OpenAI, AutoTokenizer for Transformers)
- [ ] Create embedding generation script with batch processing
- [ ] Build validation functions for metadata schemas
- [ ] Write tests for chunking edge cases (code blocks, very long documents, empty documents)
- [ ] Benchmark chunk size and overlap on sample data
- [ ] Document embedding model choice in `config/embeddings.yaml`

---

**Document Version**: 1.0  
**Last Updated**: 2026-03-12  
**Author**: Autonomous Developer (opencode)  
**Status**: Ready for Implementation
