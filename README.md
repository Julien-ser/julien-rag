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

**Phase 4: RAG API & External Integration** ✅ Complete
- [x] **Task 4.1**: Build FastAPI REST endpoints ✅
  - Complete API with interactive docs at `/docs`
  - All endpoints: `/query`, `/sources`, `/stats`, `/refresh`, `/health`, `/metrics`, `/collections`
  - Async support, CORS enabled, admin authentication, comprehensive error handling
  - 22/22 API unit tests passing

- [x] **Task 4.2**: Implement RAG generation pipeline ✅
  - `src/rag.py` with `RAGPipeline` class supporting OpenAI and local providers
  - API endpoint `/rag-query` returns `{answer, confidence, sources, stats}`
  - Configuration in `config/rag.yaml` with LLM settings and prompts
  - 22/23 tests passing (1 requires optional dependency)

- [x] **Task 4.3**: Create SDK/client library for external use ✅
  - Complete Python package `julien_rag` with `RAGClient` class
  - Supports all API endpoints with typed Pydantic models
  - Full test suite (15/15 passing)
  - Usage examples in `examples/usage_example.py`
  - Documentation in README and package

- [x] **Task 4.4**: Add monitoring, logging, and deployment configuration ✅
  - `src/monitoring.py` with Prometheus metrics (Counter, Histogram, Gauge) and `/metrics` endpoint
  - Metrics middleware for automatic request tracking (latency, status codes, endpoints)
  - Database query metrics (operation duration, document counts)
  - Embedding generation metrics (token count, duration, provider)
  - RAG pipeline metrics (query count, confidence scores)
  - Optional system metrics (CPU, memory) when psutil available
  - Production-ready `docker/Dockerfile` with multi-stage build, health checks, non-root user
  - `docker/docker-compose.yml` with API service and optional monitoring stack (Prometheus, Grafana)
  - Comprehensive integration test suite in `tests/integration/test_full_flow.py`
  - Deployment guide in `docs/deployment.md`

**MISSION ACCOMPLISHED** ✅
Vector DB with full RAG implementation ready for external use.

## Getting Started

### Prerequisites

- Python 3.9+
- Git
- (Optional) GitHub API token for data collection: `GITHUB_TOKEN`
- (Optional) OpenAI API key for embeddings: `OPENAI_API_KEY`
- (Optional) For Docker deployment: Docker and Docker Compose

### Option 1: Local Python Installation

```bash
# Clone and navigate
cd projects/julien-rag

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # if .env.example exists
# Edit .env with your API keys:
# - GITHUB_TOKEN (optional, for GitHub data collection)
# - OPENAI_API_KEY (optional, for embeddings and RAG with OpenAI)
# - ADMIN_TOKEN (optional, for protected refresh endpoint)

# Run data ingestion (collect and process data)
./scripts/ingest_all.sh
# Or: python -m src.pipeline

# Start the FastAPI server
uvicorn src.api:app --reload --port 8000

# Visit http://localhost:8000/docs for interactive API documentation
```

### Option 2: Docker Deployment (Recommended for Production)

```bash
# Build and run using Docker Compose
docker-compose up -d

# Or build manually:
docker build -t julien-rag -f docker/Dockerfile .
docker run -p 8000:8000 \
  -v $(pwd)/data:/home/app/data \
  -v $(pwd)/logs:/home/app/logs \
  -v $(pwd)/config:/home/app/config:ro \
  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
  -e ADMIN_TOKEN=${ADMIN_TOKEN} \
  julien-rag

# Access API at http://localhost:8000/docs
```

**Optional Monitoring Stack:**

```bash
# Deploy with Prometheus and Grafana for metrics
docker-compose --profile monitoring up -d

# Access services:
# - API: http://localhost:8000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
```

For detailed deployment options, see [docs/deployment.md](docs/deployment.md).

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

The SDK is now available as a Python package! Install it and use the RAG API in any project.

### SDK Installation

```bash
# Install the SDK from the local package
pip install -e .

# Or install from a published package (once available)
# pip install julien_rag
```

### SDK Usage

See [docs/deployment.md](docs/deployment.md) for detailed deployment options including:
- Docker deployment with docker-compose
- Production configuration
- Monitoring with Prometheus/Grafana
- Security best practices
- Troubleshooting

---

## Project Structure
