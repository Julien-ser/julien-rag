# Database Performance Report

This document provides comprehensive performance metrics and validation results for the julien-rag vector database.

## Overview

- **Database Type**: ChromaDB (persistent, local)
- **Vector Similarity**: Cosine similarity
- **Index**: HNSW (Hierarchical Navigable Small World)
- **Embedding Models**: 
  - OpenAI `text-embedding-ada-002` (1536 dimensions)
  - Local `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)

## Current Status

As of the latest validation (see `scripts/validate_db.py`):

### Database Statistics

- **Total Documents**: To be populated after first full ingestion
- **Collections**: 
  - `github_docs`: GitHub-related content (repos, commits, issues, PRs, gists, starred)
  - `web_content`: Web scraped content (blog, forums, LinkedIn, Twitter, personal website)
  - `combined`: Union of all sources (for convenience)

### Performance Benchmarks

Performance metrics are measured using the validation script. Expected ranges based on implementations:

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| Query Latency (p50) | 0.1-0.3s | k=10, cosine search |
| Query Latency (p95) | 0.2-0.5s | 95th percentile |
| Queries Per Second | 3-10 QPS | Single-threaded |
| Storage per 1k docs | 5-15 MB | Depends on embedding size |

#### Storage Breakdown

```
Chromadb storage consists of:
- chroma.sqlite3: SQLite database with metadata and index pointers
- index/ (within sqlite): HNSW graph structure
- embeddings stored in binary format
```

### Validation Tests

The validation script (`scripts/validate_db.py`) performs:

1. **Data Integrity**:
   - Collection existence and accessibility
   - Document counts
   - Embedding dimension consistency
   - Metadata completeness (chunk_id, source, etc.)

2. **Performance Benchmarks**:
   - Latency distribution (p50, p90, p95, p99)
   - Throughput (queries per second)
   - Multiple k values tested (5, 10, 20)

3. **Recall@k** (optional):
   - Requires labeled test cases with known relevant documents
   - Produces precision/recall metrics for different k values

4. **Metadata Filtering**:
   - Tests correctness of source, type, date_range filters
   - Measures filtered query performance

## Optimization Recommendations

Based on validation results, here are standard recommendations:

### 1. Chunk Size Optimization

- **Current default**: 512 tokens with 100 token overlap
- **Consider smaller chunks (256-384)** if:
  - Queries are highly specific
  - You need more precise matching
- **Consider larger chunks (768-1024)** if:
  - Latency is acceptable but recall is low
  - Documents are very short

### 2. Embedding Model Choice

| Model | Dimensions | Latency | Quality | Use Case |
|-------|------------|---------|---------|----------|
| OpenAI ada-002 | 1536 | ~100ms/100 docs | High | Best accuracy, network latency |
| all-MiniLM-L6-v2 | 384 | ~50ms/100 docs (local) | Good | Offline, faster, lower cost |

**Recommendation**: Use local embeddings for development, OpenAI for production if accuracy is critical.

### 3. Index Parameters (if manually configurable)

ChromaDB uses HNSW with default parameters:
- EFConstruction: 200 (build-time)
- EFSearch: 100 (query-time)

**Tuning**:
- Increase EFSearch (up to 200-400) for higher recall at cost of latency
- Decrease EFSearch (down to 50) for lower latency if recall is acceptable

### 4. Batch Processing

- **Embedding generation**: Batch size 100 is optimal for OpenAI API
- **Storage operations**: Batch size 100 for upsert operations
- **Querying**: Single queries are fine for real-time use

### 5. Database Maintenance

- **Regular backups**: Copy `data/vector_db/chroma.sqlite3` periodically
- **Size monitoring**: Database grows linearly with document count
- **Collection cleanup**: Remove unused collections to reclaim space
- **Re-indexing**: Consider if >50% data has changed

## How to Run Validation

```bash
# Quick validation (basic checks, small benchmark)
python scripts/validate_db.py

# Full validation with extensive benchmarking
python scripts/validate_db.py --benchmark 500

# Include recall@k tests (requires test cases)
python scripts/validate_db.py --test-recall

# Verbose output
python scripts/validate_db.py --verbose --output reports/validation.json
```

## Interpreting Results

### Good Performance Indicators

- ✅ Total documents > 1000
- ✅ p95 latency < 0.5s for k=10
- ✅ Recall@10 > 0.7 (if tested)
- ✅ No metadata issues
- ✅ Consistent embedding dimensions

### Warning Signs

- ⚠️ No documents in database → Run ingestion pipeline
- ⚠️ High latency (>1s p95) → Reduce chunk size or use local embeddings
- ⚠️ Low recall (<0.5) → Consider re-embedding with better model
- ⚠️ Inconsistent dimensions → Re-process with single embedding model

### Error Conditions

- ❌ Database corruption → Reset and re-ingest: `python -c "from src.database import init_database; init_database('data/vector_db').reset_database()"`
- ❌ Missing embeddings → Re-run embedding generation
- ❌ Metadata missing → Fix preprocessor output

## Future Optimization Areas

1. **Query Caching**: Cache frequent query embeddings and results
2. **Hybrid Search**: Combine vector + lexical (BM25) search
3. **Multi-stage Retrieval**: Two-phase retrieval with coarse then fine search
4. **Compression**: Use PCA or binary embeddings for large datasets
5. **Distributed**: Shard across multiple ChromaDB instances for scale

## Appendix: Running Full Pipeline

If database is empty or needs optimization:

```bash
# 1. Re-ingest all data
./scripts/ingest_all.sh

# 2. Validate results
python scripts/validate_db.py

# 3. Review this document for recommendations
```

---

**Last Updated**: 2026-03-12  
**Validation Script Version**: 1.0  
**Project**: julien-rag
