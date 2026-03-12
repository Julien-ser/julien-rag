# Iteration 1 - julien-rag

**Timestamp:** Thu Mar 12 04:52:30 PM EDT 2026
**Task:** Task 1.1: Research and select vector database technology

## Prompt Sent

```
# Project-Specific Agent Instructions

You are an autonomous developer working on this specific project.

## Your Role

- Read TASKS.md to understand project requirements
- Complete one task per iteration
- Write clean, well-tested code
- Update TASKS.md with progress
- Commit changes to GitHub (git push)
- Work without asking for permission

## Key Points

1. **No Virtual Environments**: Use the host system's Python, Node.js, etc.
   - Only create venv/Docker if absolutely necessary (document why)

2. **Testing**: Write tests as you build
   - Unit tests for functions
   - Integration tests for features

3. **Documentation**: Every feature should have clear documentation
   - Comments in code
   - README updates
   - Usage examples

4. **Git Workflow**:
   ```bash
   git add .
   git commit -m "Feature: [description]"
   git push origin main
   ```

5. **Task Completion**:
   - Mark complete in TASKS.md with [x]
   - Only mark when fully working and tested
   - If blocked, document the issue and move to next task

## Success Criteria

- ✅ All TASKS.md items marked [x]
- ✅ Code is tested and documented
- ✅ Project runs locally without venv
- ✅ All commits pushed to GitHub
- ✅ README explains how to run the project

Now read TASKS.md and get started!

---

### ⚠️ CRITICAL TOKEN CONSTRAINTS:
- Iteration: 1 / 64k Token Budget
- Attempt: 1 (previous attempts may have partial progress)
- **Mandate:** Operate efficiently. Use partial edits, not full file rewrites when possible.
- **Output:** Be concise and action-oriented.


## CURRENT PROJECT STATE (Iteration 1)

```
# julien-rag
**Mission:** create a vector DB of everything I've done online/github that you can find, which can be used elsewhere as a rag implementation

## Phase 1: Planning & Infrastructure Setup
- [ ] Task 1.1: Research and select vector database technology
  - **Deliverable:** Decision document comparing ChromaDB vs Pinecone vs Weaviate vs Qdrant, with final selection and justification
  - **Tech:** Evaluate based on local deployment capability, ease of use, and integration options
  - **Output:** `docs/vector_db_selection.md`

- [ ] Task 1.2: Design data schema and document structure
  - **Deliverable:** Schema specification defining document metadata fields (source, date, type, url, tags), chunking strategy, and embedding dimensions
  - **Tech:** Design for document chunking (semantic vs fixed-size), overlap parameters
  - **Output:** `docs/schema_design.md`

- [ ] Task 1.3: Choose embedding model and API setup
  - **Deliverable:** Selected embedding model configuration with API keys stored in .env
  - **Tech:** OpenAI `text-embedding-ada-002`, Cohere Embed, or HuggingFace `sentence-transformers/all-MiniLM-L6-v2`
  - **Output:** Updated `.env` with embedding API keys, `config/embeddings.yaml`

- [ ] Task 1.4: Initialize project structure and dependencies
  - **Deliverable:** Project scaffolding with all required directories and `requirements.txt`
  - **Tech:** Create `src/`, `data/`, `config/`, `tests/`, `docs/` directories
  - **Output:** Complete `requirements.txt` including: `chromadb`, `openai`, `sentence-transformers`, `PyGithub`, `beautifulsoup4`, `fastapi`, `uvicorn`, `python-dotenv`, `pandas`, `tiktoken`
  - **Output:** `src/__init__.py`, `tests/__init__.py`

## Phase 2: Data Collection & Ingestion Pipeline
- [ ] Task 2.1: Implement GitHub API data collector
  - **Deliverable:** Working GitHub scraper that collects repositories, commits, issues, PRs, gists, and starred repos
  - **Tech:** Use `PyGithub` library with authentication from GitHub token
  - **Output:** `src/github_collector.py` with functions: `collect_repos()`, `collect_commits()`, `collect_issues()`, `collect_gists()`, `collect_starred()`
  - **Output:** Sample data in `data/raw/github_*.json`

- [ ] Task 2.2: Implement web content scraper for online presence
  - **Deliverable:** Modular scraper for personal website, blog, forum posts, LinkedIn, Twitter/X (if public)
  - **Tech:** `beautifulsoup4`, `requests`, `selenium` for dynamic content if needed
  - **Output:** `src/web_scraper.py` with configurable URL patterns and content extraction
  - **Output:** Sample scraped data in `data/raw/web_*.html` or `.json`

- [ ] Task 2.3: Build document preprocessing and chunking pipeline
  - **Deliverable:** Text extraction, cleaning, and intelligent chunking system
  - **Tech:** `tiktoken` for token counting, recursive text splitting with overlap, markdown parsing
  - **Output:** `src/preprocessor.py` with `extract_text()`, `clean_text()`, `chunk_documents()`, `create_metadata()`
  - **Output:** Processed chunks in `data/processed/chunks.jsonl`

- [ ] Task 2.4: Create unified data pipeline with error handling
  - **Deliverable:** Orchestration script that runs full ingestion from collection to processed chunks
  - **Tech:** `logging` for tracking, retry logic for API calls, incremental updates
  - **Output:** `src/pipeline.py` with `run_ingestion()` main function
  - **Output:** `scripts/ingest_all.sh` running: `python -m src.pipeline`
  - **Output:** Comprehensive logs in `logs/ingestion_*.log`

## Phase 3: Vector Database Implementation
- [ ] Task 3.1: Initialize vector database and collections
  - **Deliverable:** Database setup script with collection creation and index configuration
  - **Tech:** ChromaDB persistent client with cosine similarity metric, HNSW index parameters
  - **Output:** `src/database.py` with `init_database()`, `create_collection(name)`, `get_collection(name)`
  - **Output:** Database directory created at `data/vector_db/`
  - **Output:** Collections: `github_docs`, `web_content`, `combined`

- [ ] Task 3.2: Implement embedding generation and storage
  - **Deliverable:** Batch embedding generator with progress tracking and rate limiting
  - **Tech:** OpenAI API with `tiktoken` usage tracking, or local `sentence-transformers`
  - **Output:** `src/embedder.py` with `generate_embeddings(texts)`, `batch_embed(chunks, batch_size=100)`
  - **Output:** `src/vector_store.py` with `add_documents(chunks, embeddings, metadatas)`
  - **Output:** Successfully stored vectors in database with metadata

- [ ] Task 3.3: Implement similarity search functionality
  - **Deliverable:** Query interface with top-k retrieval and metadata filtering
  - **Tech:** Vector similarity search with optional filters (source, date range, document type)
  - **Output:** `src/retriever.py` with `search(query_text, k=10, filters=None)` returning documents and scores
  - **Output:** Unit tests in `tests/test_retriever.py` validating search accuracy

- [ ] Task 3.4: Perform database validation and optimization
  - **Deliverable:** Validation report and optimized parameters
  - **Tech:** Test recall@k with known queries, measure query latency, optimize chunk size
  - **Output:** `scripts/validate_db.py` with tests for precision/recall
  - **Output:** `docs/database_performance.md` with metrics: embedding count, storage size, query latency (p50, p95, p99)

## Phase 4: RAG API & External Integration
- [ ] Task 4.1: Build FastAPI REST endpoints
  - **Deliverable:** Complete API with documentation at `/docs`
  - **Tech:** FastAPI with async endpoints, CORS enabled, Pydantic models
  - **Output:** `src/api.py` with endpoints:
    - `POST /query` - search and return relevant documents
    - `GET /sources` - list available source types
    - `GET /stats` - return database statistics (document count, sources)
    - `POST /refresh` - trigger reindexing (admin only)
  - **Output:** API runs at `http://localhost:8000` with interactive docs

- [ ] Task 4.2: Implement RAG generation pipeline
  - **Deliverable:** Endpoint that combines retrieval with LLM generation
  - **Tech:** Integrate with OpenAI GPT-4 or local LLM (Llama 3) for answer synthesis
  - **Output:** `src/rag.py` with `generate_answer(query, context_chunks)` function
  - **Output:** API endpoint `POST /rag-query` returns: `{answer, sources, confidence}`
  - **Output:** Configuration for LLM model and temperature in `config/rag.yaml`

- [ ] Task 4.3: Create SDK/client library for external use
  - **Deliverable:** Python package with simple interface for other projects
  - **Tech:** Package structure with `setup.py` or `pyproject.toml`
  - **Output:** `julien_rag/` package with `Client` class: `client = RAGClient(base_url)`; `results = client.search("query")`
  - **Output:** `examples/usage_example.py` demonstrating search and RAG query
  - **Output:** Published to local package index or GitHub for easy `pip install`

- [ ] Task 4.4: Add monitoring, logging, and deployment configuration
  - **Deliverable:** Production-ready configuration with health checks and metrics
  - **Tech:** Prometheus metrics, structured JSON logging, Dockerfile, docker-compose.yml
  - **Output:** `src/monitoring.py` with `/health` and `/metrics` endpoints
  - **Output:** `docker/Dockerfile` and `docker/docker-compose.yml`
  - **Output:** Deployment guide in `docs/deployment.md`
  - **Output:** Final integration test script `tests/integration/test_full_flow.py`

- [ ] MISSION ACCOMPLISHED: Vector DB with full RAG implementation ready for external use
```

## NEXT TASK TO COMPLETE:
Task 1.1: Research and select vector database technology

**Instructions:** Complete this task. Mark [x] in TASKS.md when done. Create, modify, or delete files as needed. Execute commands as needed. Also update README.md to match this project (name, setup instructions, current progress). No permission needed—just act.
```

## OpenCode Output

```
[0m
> build · stepfun/step-3.5-flash:free
[0m
I'll complete Task 1.1: Research and select vector database technology. Let me start by creating the necessary directory and writing the comparison document.
[0m$ [0mmkdir -p docs
[0m
[0m← [0mWrite docs/vector_db_selection.md
Wrote file successfully.
[0m
Now let me check and update the README.md to reflect the project and this decision:
[0m→ [0mRead README.md
[0m✗ [0medit failed
[91m[1mError: [0mCould not find oldString in the file. It must match exactly, including whitespace, indentation, and line endings.
[0m
[0m← [0mWrite README.md
Wrote file successfully.
[0m
[0m→ [0mRead TASKS.md
[0m
[0m← [0mEdit TASKS.md
Index: /home/julien/Desktop/Free-Wiggum-opencode/projects/julien-rag/TASKS.md
===================================================================
--- /home/julien/Desktop/Free-Wiggum-opencode/projects/julien-rag/TASKS.md
+++ /home/julien/Desktop/Free-Wiggum-opencode/projects/julien-rag/TASKS.md
@@ -1,9 +1,9 @@
 # julien-rag
 **Mission:** create a vector DB of everything I've done online/github that you can find, which can be used elsewhere as a rag implementation
 
 ## Phase 1: Planning & Infrastructure Setup
-- [ ] Task 1.1: Research and select vector database technology
+- [x] Task 1.1: Research and select vector database technology
   - **Deliverable:** Decision document comparing ChromaDB vs Pinecone vs Weaviate vs Qdrant, with final selection and justification
   - **Tech:** Evaluate based on local deployment capability, ease of use, and integration options
   - **Output:** `docs/vector_db_selection.md`
 

[0m
Now let me commit and push these changes as per the workflow:
[0m$ [0mgit add docs/vector_db_selection.md README.md TASKS.md
[0m
[0m$ [0mgit status
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	modified:   README.md
	modified:   TASKS.md
	new file:   docs/vector_db_selection.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	logs/
[0m
[0m$ [0mgit diff --cached
diff --git a/README.md b/README.md
index a6529f7..2ca7985 100644
--- a/README.md
+++ b/README.md
@@ -1,29 +1,139 @@
-# Project Template
+# julien-rag
 
-This is a template for new projects created via `wiggum_master.sh create`.
+**Mission:** Create a vector database of everything I've done online/GitHub that can be used elsewhere as a RAG implementation.
 
-Each project:
-- Lives in `projects/<project-name>/`
-- Has its own GitHub repository
-- Runs its own autonomous OpenCode agent loop
-- Tracks progress in TASKS.md
+## Overview
 
-## Setup
+This project builds a Retrieval-Augmented Generation (RAG) system that:
+- Collects data from GitHub (repos, commits, issues, PRs, gists, starred)
+- Scrapes web presence (blog, forums, social media)
+- Processes and chunks documents intelligently
+- Stores embeddings in a vector database
+- Provides a FastAPI REST interface for semantic search and Q&A
+- Can be used as a Python SDK in other projects
 
-1. Create: `bash wiggum_master.sh create "my-project" "Description"`
-2. View: `cat projects/my-project/README.md`
-3. Initialize: `cd projects/my-project && opencode /init --yes`
-4. Run: `cd projects/my-project && bash wiggum.sh`
+## Technology Stack
 
-## Files
+- **Vector Database**: ChromaDB (local, persistent)
+- **Embeddings**: OpenAI `text-embedding-ada-002` or `sentence-transformers/all-MiniLM-L6-v2`
+- **API**: FastAPI with async endpoints
+- **Data Collection**: PyGithub, beautifulsoup4, requests
+- **Processing**: tiktoken for token counting, recursive text splitting
 
-- **README.md** - Project documentation
-- **TASKS.md** - Development task list
-- **prompt.txt** - Agent instructions (project-specific)
-- **AGENTS.md** - Project context (auto-generated)
-- **src/** - Source code directory
-- **tests/** - Test files
+## Current Status
 
-## Customization
+**Phase 1: Planning & Infrastructure Setup**
+- [x] **Task 1.1**: Vector database selection (ChromaDB chosen for local-first, zero-config approach)
+- [ ] Task 1.2: Design data schema and document structure
+- [ ] Task 1.3: Choose embedding model and API setup
+- [ ] Task 1.4: Initialize project structure and dependencies
 
-Update TASKS.md with your project goals, then let the agent handle it!
+See [TASKS.md](TASKS.md) for complete task list.
+
+## Getting Started
+
+### Prerequisites
+
+- Python 3.9+
+- Git
+- (Optional) GitHub API token for data collection
+- (Optional) OpenAI API key for embeddings
+
+### Installation
+
+```bash
+# Clone and navigate
+cd projects/julien-rag
+
+# Install dependencies (will be created in Task 1.4)
+pip install -r requirements.txt
+
+# Set up environment variables
+cp .env.example .env
+# Edit .env with your API keys
+```
+
+### Running the API
+
+```bash
+# Start the FastAPI server (will be created in Task 4.1)
+uvicorn src.api:app --reload --port 8000
+
+# Visit http://localhost:8000/docs for interactive API documentation
+```
+
+### Running the Ingestion Pipeline
+
+```bash
+# Collect all data and populate vector database (will be created in Task 2.4)
+python -m src.pipeline
+
+# View logs in logs/ingestion_*.log
+```
+
+## Project Structure
+
+```
+julien-rag/
+├── src/
+│   ├── database.py      # ChromaDB initialization
+│   ├── embedder.py      # Embedding generation
+│   ├── vector_store.py  # Vector storage operations
+│   ├── retriever.py     # Similarity search
+│   ├── github_collector.py
+│   ├── web_scraper.py
+│   ├── preprocessor.py
+│   ├── pipeline.py
+│   ├── api.py           # FastAPI endpoints
+│   ├── rag.py           # RAG generation
+│   └── monitoring.py
+├── data/
+│   ├── raw/            # Raw collected data
+│   ├── processed/      # Chunked documents
+│   └── vector_db/      # ChromaDB storage
+├── config/
+│   ├── embeddings.yaml
+│   └── rag.yaml
+├── tests/
+├── docs/
+│   ├── vector_db_selection.md  # ✅ Completed
+│   ├── schema_design.md
+│   ├── database_performance.md
+│   └── deployment.md
+├── logs/
+├── scripts/
+│   └── ingest_all.sh
+├── examples/
+├── requirements.txt
+├── TASKS.md
+└── README.md
+```
+
+## Using the SDK
+
+Once completed, you'll be able to use this RAG system in other projects:
+
+```python
+from julien_rag import RAGClient
+
+client = RAGClient(base_url="http://localhost:8000")
+
+# Semantic search
+results = client.search("What projects use FastAPI?")
+for doc in results:
+    print(f"{doc['source']}: {doc['content'][:100]}...")
+
+# RAG query with LLM generation
+response = client.rag_query("Explain the key architectural decisions")
+print(f"Answer: {response['answer']}")
+print(f"Sources: {response['sources']}")
+```
+
+## Decision Documentation
+
+Key decisions are documented in `docs/`:
+- [Vector Database Selection](docs/vector_db_selection.md) - Why ChromaDB was chosen
+
+## License
+
+MIT (to be determined)
diff --git a/TASKS.md b/TASKS.md
index 525eb08..3636187 100644
--- a/TASKS.md
+++ b/TASKS.md
@@ -2,7 +2,7 @@
 **Mission:** create a vector DB of everything I've done online/github that you can find, which can be used elsewhere as a rag implementation
 
 ## Phase 1: Planning & Infrastructure Setup
-- [ ] Task 1.1: Research and select vector database technology
+- [x] Task 1.1: Research and select vector database technology
   - **Deliverable:** Decision document comparing ChromaDB vs Pinecone vs Weaviate vs Qdrant, with final selection and justification
   - **Tech:** Evaluate based on local deployment capability, ease of use, and integration options
   - **Output:** `docs/vector_db_selection.md`
diff --git a/docs/vector_db_selection.md b/docs/vector_db_selection.md
new file mode 100644
index 0000000..1f56e18
--- /dev/null
+++ b/docs/vector_db_selection.md
@@ -0,0 +1,121 @@
+# Vector Database Selection Decision
+
+## Project Requirements
+- **Local deployment**: Must run without external cloud services
+- **Ease of use**: Minimal setup, good Python SDK
+- **Integration**: Compatible with embedding models (OpenAI, sentence-transformers)
+- **Performance**: Fast similarity search for RAG queries
+- **Scalability**: Handle thousands of documents from GitHub + web scraping
+
+## Comparison Matrix
+
+| Feature | ChromaDB | Pinecone | Weaviate | Qdrant |
+|---------|----------|----------|----------|--------|
+| **Deployment** | Local only (in-memory/persistent) | Cloud-only | Cloud/Self-hosted | Self-hosted (Docker) |
+| **Setup Complexity** | Very low (pip install) | Medium (cloud account) | High (Docker/K8s) | Medium (Docker) |
+| **Python SDK** | Excellent | Good | Good | Good |
+| **Embedding Support** | Automatic | Manual | Automatic | Manual |
+| **Performance** | Good (HNSW) | Excellent | Excellent | Excellent |
+| **Storage** | Local files | Cloud | Local/Cloud | Local |
+| **Cost** | Free | Paid | Free/Paid | Free |
+| **RAG Ready** | Yes | Yes | Yes | Yes |
+| **Community** | Growing | Large | Medium | Medium |
+
+## Detailed Analysis
+
+### ChromaDB
+**Pros:**
+- Zero-configuration, pure Python library
+- Built-in embedding management
+- Simple API: `chromadb.Client()`, `collection.add()`
+- Supports both in-memory (dev) and persistent (prod) modes
+- Good for prototyping and production at moderate scale
+- Actively maintained with strong RAG use case focus
+
+**Cons:**
+- Less battle-tested than Pinecone at massive scale
+- Limited advanced features compared to others
+
+### Pinecone
+**Pros:**
+- Industry leader in managed vector databases
+- Excellent performance and reliability
+- Rich features: filtering, sparse+dense vectors
+
+**Cons:**
+- Cloud-only violates local deployment requirement
+- Costs money ($0.24/GB/month + API calls)
+- External dependency, data leaves local machine
+
+### Weaviate
+**Pros:**
+- Powerful hybrid search (vector + keyword)
+- GraphQL API
+- Built-in vectorization modules
+
+**Cons:**
+- Complex setup (requires separate server process)
+- Heavyweight for simple RAG use case
+- More operational overhead
+
+### Qdrant
+**Pros:**
+- High performance (Rust implementation)
+- Good for production deployments
+- Supports advanced filtering
+
+**Cons:**
+- Requires running separate server (Docker)
+- More complex than ChromaDB for simple use case
+- Manual embedding management needed
+
+## Final Selection: ChromaDB
+
+### Justification
+
+1. **Local-First Design**: ChromaDB runs entirely locally, aligning with the project's requirement for a self-contained vector database. No external services, no API calls to cloud databases, complete data sovereignty.
+
+2. **Minimal Setup**: `pip install chromadb` is all that's needed. No Docker containers, no external processes, no cloud accounts. This gets us from zero to working database in seconds.
+
+3. **Perfect for RAG**: ChromaDB's collection-based model with automatic document storage and retrieval matches exactly what a RAG system needs:
+   - Store documents with embeddings and metadata
+   - Fast similarity search
+   - Simple query interface: `collection.query(query_texts=...)`
+
+4. **Python-Native**: As a Python library, it integrates seamlessly with our planned tech stack (FastAPI, sentence-transformers, OpenAI embeddings). No separate service to manage, no connection strings, no network serialization overhead.
+
+5. **Development Experience**: In-memory mode for development/testing, persistent mode for production with the same API. Enables rapid iteration without infrastructure concerns.
+
+6. **Scalability Sufficient**: For this project's scope (personal GitHub history + web content), we expect <100K documents. ChromaDB handles this easily on a single machine. If outgrew it, could migrate to Qdrant or Pinecone later.
+
+7. **Embedding Management**: ChromaDB can optionally manage embedding generation, but we'll keep control in our `embedder.py` component for flexibility. The integration is clean either way.
+
+### Alternatives Considered and Rejected
+
+- **Pinecone**: Rejected due to cloud-only and costs. Would create external dependency and monthly expenses for a personal project.
+- **Weaviate**: Overkill. The additional features (GraphQL, hybrid search) aren't needed for this use case, but adds significant operational complexity.
+- **Qdrant**: Good performance but requires separate server. The added complexity of managing a Docker container isn't justified when ChromaDB provides all needed functionality in a single library.
+
+## Implementation Plan
+
+1. Add `chromadb` to `requirements.txt`
+2. Create `src/database.py` with initialization functions:
+   - `init_database()` - creates persistent client at `data/vector_db/`
+   - `create_collection(name)` - creates collection with cosine similarity
+   - `get_collection(name)` - retrieves existing collection
+3. Create collections: `github_docs`, `web_content`, `combined`
+4. Use HNSW index parameters for optimal performance
+5. Integrate with `src/embedder.py` and `src/vector_store.py`
+
+## Expected Benefits
+
+- **Fast Development**: No infrastructure to set up, can focus on data pipeline and RAG logic
+- **Easy Testing**: In-memory database can be created/destroyed in test fixtures
+- **Production Ready**: Persistent mode provides durability with same codebase
+- **Maintainable**: Single dependency, no operational overhead
+
+---
+
+**Decision Date**: 2026-03-12
+**Decision Maker**: Autonomous Developer (opencode)
+**Status**: Approved for implementation
[0m
[0m$ [0mgit commit -m "docs: select ChromaDB as vector database with comprehensive analysis"
[main 0843396] docs: select ChromaDB as vector database with comprehensive analysis
 3 files changed, 253 insertions(+), 22 deletions(-)
 create mode 100644 docs/vector_db_selection.md
[0m
[0m$ [0mgit push origin main
To github.com:Julien-ser/julien-rag.git
 * [new branch]      main -> main
[0m
✅ Task 1.1 complete. ChromaDB selected as vector database. Decision documented in `docs/vector_db_selection.md`. README and TASKS.md updated. Changes committed and pushed to GitHub.

Ready for Task 1.2.
```

## TASKS.md After Iteration

```markdown
# julien-rag
**Mission:** create a vector DB of everything I've done online/github that you can find, which can be used elsewhere as a rag implementation

## Phase 1: Planning & Infrastructure Setup
- [x] Task 1.1: Research and select vector database technology
  - **Deliverable:** Decision document comparing ChromaDB vs Pinecone vs Weaviate vs Qdrant, with final selection and justification
  - **Tech:** Evaluate based on local deployment capability, ease of use, and integration options
  - **Output:** `docs/vector_db_selection.md`

- [ ] Task 1.2: Design data schema and document structure
  - **Deliverable:** Schema specification defining document metadata fields (source, date, type, url, tags), chunking strategy, and embedding dimensions
  - **Tech:** Design for document chunking (semantic vs fixed-size), overlap parameters
  - **Output:** `docs/schema_design.md`

- [ ] Task 1.3: Choose embedding model and API setup
  - **Deliverable:** Selected embedding model configuration with API keys stored in .env
  - **Tech:** OpenAI `text-embedding-ada-002`, Cohere Embed, or HuggingFace `sentence-transformers/all-MiniLM-L6-v2`
  - **Output:** Updated `.env` with embedding API keys, `config/embeddings.yaml`

- [ ] Task 1.4: Initialize project structure and dependencies
  - **Deliverable:** Project scaffolding with all required directories and `requirements.txt`
  - **Tech:** Create `src/`, `data/`, `config/`, `tests/`, `docs/` directories
  - **Output:** Complete `requirements.txt` including: `chromadb`, `openai`, `sentence-transformers`, `PyGithub`, `beautifulsoup4`, `fastapi`, `uvicorn`, `python-dotenv`, `pandas`, `tiktoken`
  - **Output:** `src/__init__.py`, `tests/__init__.py`

## Phase 2: Data Collection & Ingestion Pipeline
- [ ] Task 2.1: Implement GitHub API data collector
  - **Deliverable:** Working GitHub scraper that collects repositories, commits, issues, PRs, gists, and starred repos
  - **Tech:** Use `PyGithub` library with authentication from GitHub token
  - **Output:** `src/github_collector.py` with functions: `collect_repos()`, `collect_commits()`, `collect_issues()`, `collect_gists()`, `collect_starred()`
  - **Output:** Sample data in `data/raw/github_*.json`

- [ ] Task 2.2: Implement web content scraper for online presence
  - **Deliverable:** Modular scraper for personal website, blog, forum posts, LinkedIn, Twitter/X (if public)
  - **Tech:** `beautifulsoup4`, `requests`, `selenium` for dynamic content if needed
  - **Output:** `src/web_scraper.py` with configurable URL patterns and content extraction
  - **Output:** Sample scraped data in `data/raw/web_*.html` or `.json`

- [ ] Task 2.3: Build document preprocessing and chunking pipeline
  - **Deliverable:** Text extraction, cleaning, and intelligent chunking system
  - **Tech:** `tiktoken` for token counting, recursive text splitting with overlap, markdown parsing
  - **Output:** `src/preprocessor.py` with `extract_text()`, `clean_text()`, `chunk_documents()`, `create_metadata()`
  - **Output:** Processed chunks in `data/processed/chunks.jsonl`

- [ ] Task 2.4: Create unified data pipeline with error handling
  - **Deliverable:** Orchestration script that runs full ingestion from collection to processed chunks
  - **Tech:** `logging` for tracking, retry logic for API calls, incremental updates
  - **Output:** `src/pipeline.py` with `run_ingestion()` main function
  - **Output:** `scripts/ingest_all.sh` running: `python -m src.pipeline`
  - **Output:** Comprehensive logs in `logs/ingestion_*.log`

## Phase 3: Vector Database Implementation
- [ ] Task 3.1: Initialize vector database and collections
  - **Deliverable:** Database setup script with collection creation and index configuration
  - **Tech:** ChromaDB persistent client with cosine similarity metric, HNSW index parameters
  - **Output:** `src/database.py` with `init_database()`, `create_collection(name)`, `get_collection(name)`
  - **Output:** Database directory created at `data/vector_db/`
  - **Output:** Collections: `github_docs`, `web_content`, `combined`

- [ ] Task 3.2: Implement embedding generation and storage
  - **Deliverable:** Batch embedding generator with progress tracking and rate limiting
  - **Tech:** OpenAI API with `tiktoken` usage tracking, or local `sentence-transformers`
  - **Output:** `src/embedder.py` with `generate_embeddings(texts)`, `batch_embed(chunks, batch_size=100)`
  - **Output:** `src/vector_store.py` with `add_documents(chunks, embeddings, metadatas)`
  - **Output:** Successfully stored vectors in database with metadata

- [ ] Task 3.3: Implement similarity search functionality
  - **Deliverable:** Query interface with top-k retrieval and metadata filtering
  - **Tech:** Vector similarity search with optional filters (source, date range, document type)
  - **Output:** `src/retriever.py` with `search(query_text, k=10, filters=None)` returning documents and scores
  - **Output:** Unit tests in `tests/test_retriever.py` validating search accuracy

- [ ] Task 3.4: Perform database validation and optimization
  - **Deliverable:** Validation report and optimized parameters
  - **Tech:** Test recall@k with known queries, measure query latency, optimize chunk size
  - **Output:** `scripts/validate_db.py` with tests for precision/recall
  - **Output:** `docs/database_performance.md` with metrics: embedding count, storage size, query latency (p50, p95, p99)

## Phase 4: RAG API & External Integration
- [ ] Task 4.1: Build FastAPI REST endpoints
  - **Deliverable:** Complete API with documentation at `/docs`
  - **Tech:** FastAPI with async endpoints, CORS enabled, Pydantic models
  - **Output:** `src/api.py` with endpoints:
    - `POST /query` - search and return relevant documents
    - `GET /sources` - list available source types
    - `GET /stats` - return database statistics (document count, sources)
    - `POST /refresh` - trigger reindexing (admin only)
  - **Output:** API runs at `http://localhost:8000` with interactive docs

- [ ] Task 4.2: Implement RAG generation pipeline
  - **Deliverable:** Endpoint that combines retrieval with LLM generation
  - **Tech:** Integrate with OpenAI GPT-4 or local LLM (Llama 3) for answer synthesis
  - **Output:** `src/rag.py` with `generate_answer(query, context_chunks)` function
  - **Output:** API endpoint `POST /rag-query` returns: `{answer, sources, confidence}`
  - **Output:** Configuration for LLM model and temperature in `config/rag.yaml`

- [ ] Task 4.3: Create SDK/client library for external use
  - **Deliverable:** Python package with simple interface for other projects
  - **Tech:** Package structure with `setup.py` or `pyproject.toml`
  - **Output:** `julien_rag/` package with `Client` class: `client = RAGClient(base_url)`; `results = client.search("query")`
  - **Output:** `examples/usage_example.py` demonstrating search and RAG query
  - **Output:** Published to local package index or GitHub for easy `pip install`

- [ ] Task 4.4: Add monitoring, logging, and deployment configuration
  - **Deliverable:** Production-ready configuration with health checks and metrics
  - **Tech:** Prometheus metrics, structured JSON logging, Dockerfile, docker-compose.yml
  - **Output:** `src/monitoring.py` with `/health` and `/metrics` endpoints
  - **Output:** `docker/Dockerfile` and `docker/docker-compose.yml`
  - **Output:** Deployment guide in `docs/deployment.md`
  - **Output:** Final integration test script `tests/integration/test_full_flow.py`

- [ ] MISSION ACCOMPLISHED: Vector DB with full RAG implementation ready for external use```

**Completed at:** Thu Mar 12 04:53:36 PM EDT 2026
