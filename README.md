# julien-rag

**Mission:** Create a vector database of everything I've done online/GitHub that can be used elsewhere as a RAG implementation.

## Overview

This project builds a Retrieval-Augmented Generation (RAG) system that:
- Collects data from GitHub (repos, commits, issues, PRs, gists, starred)
- Scrapes web presence (blog, forums, social media)
- Processes and chunks documents intelligently
- Stores embeddings in a vector database
- Provides a FastAPI REST interface for semantic search and Q&A
- Can be used as a Python SDK in other projects

## Technology Stack

- **Vector Database**: ChromaDB (local, persistent)
- **Embeddings**: OpenAI `text-embedding-ada-002` or `sentence-transformers/all-MiniLM-L6-v2`
- **API**: FastAPI with async endpoints
- **Data Collection**: PyGithub, beautifulsoup4, requests
- **Processing**: tiktoken for token counting, recursive text splitting

## Current Status

**Phase 1: Planning & Infrastructure Setup** ✅ Complete
- [x] **Task 1.1**: Vector database selection (ChromaDB chosen for local-first, zero-config approach)
- [x] **Task 1.2**: Design data schema and document structure
- [x] **Task 1.3**: Choose embedding model and API setup
- [x] **Task 1.4**: Initialize project structure and dependencies

**Phase 2: Data Collection & Ingestion Pipeline** 🔄 In Progress
- [x] **Task 2.1**: Implement GitHub API data collector ✅
  - `src/github_collector.py` with full collection capabilities
  - Collects repos, commits, issues, gists, and starred repos
  - Unit tests in `tests/test_github_collector.py`
- [x] **Task 2.2**: Implement web content scraper for online presence ✅
  - `src/web_scraper.py` with modular scrapers for multiple platforms
  - Supports: personal websites, blogs (HTML/RSS), forums, LinkedIn, Twitter/X
  - Uses beautifulsoup4 for static content and selenium for dynamic pages
  - Sample data in `data/raw/web_*_sample.json`
  - Unit tests in `tests/test_web_scraper.py`
- [ ] Task 2.3: Build document preprocessing and chunking pipeline
- [ ] Task 2.4: Create unified data pipeline with error handling

See [TASKS.md](TASKS.md) for complete task list.

## Getting Started

### Prerequisites

- Python 3.9+
- Git
- (Optional) GitHub API token for data collection
- (Optional) OpenAI API key for embeddings

### Installation

```bash
# Clone and navigate
cd projects/julien-rag

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys
```

### Running the API

```bash
# Start the FastAPI server (will be created in Task 4.1)
uvicorn src.api:app --reload --port 8000

# Visit http://localhost:8000/docs for interactive API documentation
```

### Running the Ingestion Pipeline

```bash
# Collect all data and populate vector database (will be created in Task 2.4)
python -m src.pipeline

# View logs in logs/ingestion_*.log
```

## Project Structure

```
julien-rag/
├── src/
│   ├── database.py      # ChromaDB initialization
│   ├── embedder.py      # Embedding generation
│   ├── vector_store.py  # Vector storage operations
│   ├── retriever.py     # Similarity search
│   ├── github_collector.py
│   ├── web_scraper.py
│   ├── preprocessor.py
│   ├── pipeline.py
│   ├── api.py           # FastAPI endpoints
│   ├── rag.py           # RAG generation
│   └── monitoring.py
├── data/
│   ├── raw/            # Raw collected data
│   ├── processed/      # Chunked documents
│   └── vector_db/      # ChromaDB storage
├── config/
│   ├── embeddings.yaml
│   └── rag.yaml
├── tests/
├── docs/
│   ├── vector_db_selection.md  # ✅ Completed
│   ├── schema_design.md
│   ├── database_performance.md
│   └── deployment.md
├── logs/
├── scripts/
│   └── ingest_all.sh
├── examples/
├── requirements.txt
├── TASKS.md
└── README.md
```

## Using the SDK

Once completed, you'll be able to use this RAG system in other projects:

```python
from julien_rag import RAGClient

client = RAGClient(base_url="http://localhost:8000")

# Semantic search
results = client.search("What projects use FastAPI?")
for doc in results:
    print(f"{doc['source']}: {doc['content'][:100]}...")

# RAG query with LLM generation
response = client.rag_query("Explain the key architectural decisions")
print(f"Answer: {response['answer']}")
print(f"Sources: {response['sources']}")
```

## Decision Documentation

Key decisions are documented in `docs/`:
- [Vector Database Selection](docs/vector_db_selection.md) - Why ChromaDB was chosen
- [Schema Design](docs/schema_design.md) - Document metadata, chunking strategy, and embedding configuration (completed)

## License

MIT (to be determined)
