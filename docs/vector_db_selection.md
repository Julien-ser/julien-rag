# Vector Database Selection Decision

## Project Requirements
- **Local deployment**: Must run without external cloud services
- **Ease of use**: Minimal setup, good Python SDK
- **Integration**: Compatible with embedding models (OpenAI, sentence-transformers)
- **Performance**: Fast similarity search for RAG queries
- **Scalability**: Handle thousands of documents from GitHub + web scraping

## Comparison Matrix

| Feature | ChromaDB | Pinecone | Weaviate | Qdrant |
|---------|----------|----------|----------|--------|
| **Deployment** | Local only (in-memory/persistent) | Cloud-only | Cloud/Self-hosted | Self-hosted (Docker) |
| **Setup Complexity** | Very low (pip install) | Medium (cloud account) | High (Docker/K8s) | Medium (Docker) |
| **Python SDK** | Excellent | Good | Good | Good |
| **Embedding Support** | Automatic | Manual | Automatic | Manual |
| **Performance** | Good (HNSW) | Excellent | Excellent | Excellent |
| **Storage** | Local files | Cloud | Local/Cloud | Local |
| **Cost** | Free | Paid | Free/Paid | Free |
| **RAG Ready** | Yes | Yes | Yes | Yes |
| **Community** | Growing | Large | Medium | Medium |

## Detailed Analysis

### ChromaDB
**Pros:**
- Zero-configuration, pure Python library
- Built-in embedding management
- Simple API: `chromadb.Client()`, `collection.add()`
- Supports both in-memory (dev) and persistent (prod) modes
- Good for prototyping and production at moderate scale
- Actively maintained with strong RAG use case focus

**Cons:**
- Less battle-tested than Pinecone at massive scale
- Limited advanced features compared to others

### Pinecone
**Pros:**
- Industry leader in managed vector databases
- Excellent performance and reliability
- Rich features: filtering, sparse+dense vectors

**Cons:**
- Cloud-only violates local deployment requirement
- Costs money ($0.24/GB/month + API calls)
- External dependency, data leaves local machine

### Weaviate
**Pros:**
- Powerful hybrid search (vector + keyword)
- GraphQL API
- Built-in vectorization modules

**Cons:**
- Complex setup (requires separate server process)
- Heavyweight for simple RAG use case
- More operational overhead

### Qdrant
**Pros:**
- High performance (Rust implementation)
- Good for production deployments
- Supports advanced filtering

**Cons:**
- Requires running separate server (Docker)
- More complex than ChromaDB for simple use case
- Manual embedding management needed

## Final Selection: ChromaDB

### Justification

1. **Local-First Design**: ChromaDB runs entirely locally, aligning with the project's requirement for a self-contained vector database. No external services, no API calls to cloud databases, complete data sovereignty.

2. **Minimal Setup**: `pip install chromadb` is all that's needed. No Docker containers, no external processes, no cloud accounts. This gets us from zero to working database in seconds.

3. **Perfect for RAG**: ChromaDB's collection-based model with automatic document storage and retrieval matches exactly what a RAG system needs:
   - Store documents with embeddings and metadata
   - Fast similarity search
   - Simple query interface: `collection.query(query_texts=...)`

4. **Python-Native**: As a Python library, it integrates seamlessly with our planned tech stack (FastAPI, sentence-transformers, OpenAI embeddings). No separate service to manage, no connection strings, no network serialization overhead.

5. **Development Experience**: In-memory mode for development/testing, persistent mode for production with the same API. Enables rapid iteration without infrastructure concerns.

6. **Scalability Sufficient**: For this project's scope (personal GitHub history + web content), we expect <100K documents. ChromaDB handles this easily on a single machine. If outgrew it, could migrate to Qdrant or Pinecone later.

7. **Embedding Management**: ChromaDB can optionally manage embedding generation, but we'll keep control in our `embedder.py` component for flexibility. The integration is clean either way.

### Alternatives Considered and Rejected

- **Pinecone**: Rejected due to cloud-only and costs. Would create external dependency and monthly expenses for a personal project.
- **Weaviate**: Overkill. The additional features (GraphQL, hybrid search) aren't needed for this use case, but adds significant operational complexity.
- **Qdrant**: Good performance but requires separate server. The added complexity of managing a Docker container isn't justified when ChromaDB provides all needed functionality in a single library.

## Implementation Plan

1. Add `chromadb` to `requirements.txt`
2. Create `src/database.py` with initialization functions:
   - `init_database()` - creates persistent client at `data/vector_db/`
   - `create_collection(name)` - creates collection with cosine similarity
   - `get_collection(name)` - retrieves existing collection
3. Create collections: `github_docs`, `web_content`, `combined`
4. Use HNSW index parameters for optimal performance
5. Integrate with `src/embedder.py` and `src/vector_store.py`

## Expected Benefits

- **Fast Development**: No infrastructure to set up, can focus on data pipeline and RAG logic
- **Easy Testing**: In-memory database can be created/destroyed in test fixtures
- **Production Ready**: Persistent mode provides durability with same codebase
- **Maintainable**: Single dependency, no operational overhead

---

**Decision Date**: 2026-03-12
**Decision Maker**: Autonomous Developer (opencode)
**Status**: Approved for implementation
