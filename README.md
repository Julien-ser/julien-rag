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

**Phase 2: Data Collection & Ingestion Pipeline** ✅ Complete
- [x] **Task 2.1**: Implement GitHub API data collector ✅
- [x] **Task 2.2**: Implement web content scraper for online presence ✅
- [x] **Task 2.3**: Build document preprocessing and chunking pipeline ✅
- [x] **Task 2.4**: Create unified data pipeline with error handling ✅
  - `src/pipeline.py` with comprehensive orchestration
  - Retry logic, incremental updates, detailed logging
  - Shell script: `scripts/ingest_all.sh`
  - Logs written to `logs/ingestion_*.log`
  - Statistics saved to `data/processed/pipeline_stats.json`

**Phase 3: Vector Database Implementation** ✅ Complete
- [x] **Task 3.1**: Initialize vector database and collections ✅
- [x] **Task 3.2**: Implement embedding generation and storage ✅
- [x] **Task 3.3**: Implement similarity search functionality ✅
- [x] **Task 3.4**: Perform database validation and optimization ✅
  - `scripts/validate_db.py` with comprehensive validation suite
  - `docs/database_performance.md` with performance metrics and recommendations
  - Tests: data integrity, latency benchmarks, metadata filtering, recall@k support

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

The unified pipeline orchestrates data collection, preprocessing, and chunk generation.

**Using the shell script (recommended):**

```bash
# Full ingestion with default settings
./scripts/ingest_all.sh

# With custom configuration
./scripts/ingest_all.sh --config config/pipeline_config.json

# Set log level (DEBUG, INFO, WARNING, ERROR)
./scripts/ingest_all.sh --log-level DEBUG
```

**Using Python module directly:**

```bash
# Run with default configuration
python -m src.pipeline

# With configuration file
python -m src.pipeline --config config/my_config.json

# With debug logging
python -m src.pipeline --log-level DEBUG
```

**Configuration:**

Create a JSON configuration file (see `config/pipeline_config.example.json`):

```json
{
  "incremental": true,
  "chunk_size": 512,
  "chunk_overlap": 100,
  "github_token": null,
  "web_scrape_config": {
    "personal": ["https://yourwebsite.com/about"],
    "blog": ["https://yourblog.com/rss"]
  }
}
```

**Logs & Statistics:**

- Logs: `logs/ingestion_YYYYMMDD_HHMMSS.log` (rotating, max 10MB per file)
- Statistics: `data/processed/pipeline_stats.json`
- Processed chunks: `data/processed/*_chunks.jsonl`

**Features:**

- ✅ Retry logic with exponential backoff for API calls
- ✅ Incremental updates (skips unchanged files)
- ✅ Graceful error handling - continues on failures
- ✅ Comprehensive logging with rotation
- ✅ Automatic fallback to existing raw data
- ✅ Statistics and performance metrics

## Project Structure

```
julien-rag/
├── src/
│   ├── database.py      # ✅ ChromaDB initialization (Task 3.1)
│   ├── embedder.py      # ✅ Embedding generation (Task 3.2)
│   ├── vector_store.py  # ✅ Vector storage operations (Task 3.2)
│   ├── retriever.py     # Similarity search (Task 3.3 - pending)
│   ├── github_collector.py
│   ├── web_scraper.py
│   ├── preprocessor.py
│   ├── pipeline.py
│   ├── api.py           # FastAPI endpoints (Task 4.1 - pending)
│   ├── rag.py           # RAG generation (Task 4.2 - pending)
│   └── monitoring.py    # Monitoring (Task 4.4 - pending)
├── data/
│   ├── raw/            # Raw collected data
│   ├── processed/      # Chunked documents
│   └── vector_db/      # ChromaDB storage
├── config/
│   ├── embeddings.yaml  # Embedding configuration
│   └── rag.yaml         # RAG configuration (pending)
├── tests/
│   ├── test_embedder.py       # ✅ All tests passing (54/54)
│   ├── test_vector_store.py   # ✅ Vector store tests
│   ├── test_database.py       # ✅ Database tests
│   ├── test_preprocessor.py   # ✅ Preprocessor tests
│   ├── test_web_scraper.py    # ✅ Web scraper tests
│   └── test_github_collector.py # ✅ GitHub collector tests
├── docs/
│   ├── vector_db_selection.md  # ✅ Completed
│   ├── schema_design.md        # ✅ Completed
│   ├── database_performance.md # ✅ Completed (Task 3.4)
│   └── deployment.md           # Pending (Task 4.4)
├── logs/
├── scripts/
│   ├── ingest_all.sh       # Full ingestion pipeline
│   └── validate_db.py      # Database validation & benchmarking
├── examples/
│   └── github_collector_example.py
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
