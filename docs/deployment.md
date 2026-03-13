# Deployment Guide

This guide covers deploying the RAG (Retrieval-Augmented Generation) system in various environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Configuration](#configuration)
- [Manual Deployment](#manual-deployment)
- [Health Checks & Monitoring](#health-checks--monitoring)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

---

## Prerequisites

### Required

- Python 3.11 or higher (for manual deployment)
- Docker & Docker Compose (for containerized deployment)
- OpenAI API key (if using OpenAI embeddings/LLM) or local model files
- GitHub Personal Access Token (for data ingestion)

### Optional

- NVIDIA GPU + CUDA (for local LLM inference)
- Prometheus & Grafana (for advanced monitoring)
- Nginx/Traefik (for reverse proxy)

---

## Quick Start (Docker)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd julien-rag
cp .env.example .env
# Edit .env with your API keys
```

### 2. Configure Environment

Edit `.env` file:

```bash
OPENAI_API_KEY=your-openai-key-here
ADMIN_TOKEN=your-secure-admin-token-here
EMBEDDING_PROVIDER=openai  # or "local" for sentence-transformers
RAG_CONFIG=config/rag.yaml
```

### 3. Build and Run

```bash
# Start the API service
docker-compose up -d rag-api

# Or start everything including monitoring stack
docker-compose --profile monitoring up -d
```

### 4. Verify Deployment

```bash
# Check API health
curl http://localhost:8000/health

# Access interactive API docs
open http://localhost:8000/docs

# View metrics
curl http://localhost:8000/metrics
```

### 5. Ingest Data

Run the ingestion pipeline:

```bash
docker-compose exec rag-api python -m src.pipeline
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No* | - | OpenAI API key for embeddings/LLM |
| `ADMIN_TOKEN` | No | - | Admin token for refresh endpoint |
| `EMBEDDING_PROVIDER` | No | `openai` | Embedding provider: `openai` or `local` |
| `EMBEDDING_MODEL` | No | `text-embedding-ada-002` | Model name for embeddings |
| `RAG_CONFIG` | No | `config/rag.yaml` | Path to RAG configuration file |
| `API_HOST` | No | `0.0.0.0` | API bind host |
| `API_PORT` | No | `8000` | API bind port |
| `API_LOG_LEVEL` | No | `info` | Logging level |
| `CHROMA_PERSIST_DIR` | No | `data/vector_db` | Vector DB persistence directory |

*Required if using OpenAI embeddings or GPT-4

### Configuration Files

#### `config/embeddings.yaml`

```yaml
provider: openai  # or "local"
model: text-embedding-ada-002
batch_size: 100
rate_limit_rpm: 1000
```

#### `config/rag.yaml`

```yaml
provider: openai  # or "local"
openai:
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  temperature: 0.7
  max_tokens: 1000
generation:
  system_prompt: "You are a helpful assistant..."
  max_context_length: 4000
  min_context_chunks: 3
```

---

## Manual Deployment

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Create and edit `.env` file as shown above.

### 3. Initialize Database

```bash
python -m src.database
```

### 4. Run Ingestion (Optional)

```bash
python -m src.pipeline
```

### 5. Start API

```bash
# Development (with auto-reload)
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

# Production (with multiple workers)
gunicorn src.api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

---

## Health Checks & Monitoring

### Health Endpoint

```
GET /health
```

Returns:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Metrics Endpoint

```
GET /metrics
```

Returns Prometheus-formatted metrics:

- `rag_api_requests_total` - Total API requests by endpoint
- `rag_request_duration_seconds` - Request latency histogram
- `rag_errors_total` - Total errors by type
- `db_document_count` - Total documents in database
- `db_collection_count` - Number of collections

### Monitoring Stack (Optional)

Enable Prometheus + Grafana:

```bash
docker-compose --profile monitoring up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

Grafana dashboards are auto-provisioned from `docker/grafana/provisioning/`.

---

## SSL/TLS Configuration

### Using Nginx Reverse Proxy

Create `nginx.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Update `docker-compose.yml` to include Nginx:

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
    - "80:80"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf:ro
    - ./ssl:/etc/nginx/ssl:ro
  depends_on:
    - rag-api
```

---

## Scaling

### Horizontal Scaling

Scale API replicas:

```bash
docker-compose up -d --scale rag-api=3
```

Configure a load balancer (Nginx, Traefik, HAProxy) to distribute traffic.

### Database Optimization

For large datasets (>100k documents):

1. Increase ChromaDB HNSW index parameters in `src/database.py`:
   ```python
   hnsw_config = {
       "M": 32,  # Increase from default 16
       "ef_construction": 200,  # Increase from default 100
   }
   ```

2. Use SSD storage for vector database persistence

3. Enable caching layer (Redis) for frequent queries

---

## Troubleshooting

### API Won't Start

**Check logs:**

```bash
docker-compose logs rag-api
```

**Common issues:**
- Missing API keys in `.env`: Ensure all required keys are set
- Port 8000 already in use: Change `API_PORT` or stop conflicting service
- Permission errors: Check that `data/` and `logs/` are writable

### Ingestion Fails

**Check collector authentication:**

```bash
# Verify GitHub token has correct scopes
# Required: repo, public_repo, read:user, user:email
```

**Check API rate limits:**

- OpenAI: 300-3000 RPM depending on tier
- GitHub: 5000 requests/hour for authenticated requests

### Database Corruption

If ChromaDB becomes corrupted:

```bash
# Backup current data
mv data/vector_db data/vector_db.backup

# Reinitialize and re-ingest
python -m src.database
python -m src.pipeline
```

### Memory Issues

For large ingestion jobs:

```bash
# Increase Docker memory limit (Docker Desktop)
# Settings → Resources → Memory → 8GB+

# Or use smaller batch size
# Set EMBEDDING_BATCH_SIZE=50 in .env
```

---

## Security Considerations

### API Security

1. **Always set `ADMIN_TOKEN` in production** for refresh endpoint
2. **Use HTTPS** in production (SSL/TLS termination at load balancer)
3. **Enable CORS carefully** - restrict to known origins
4. **Rate limiting** - add middleware like `slowapi` if needed

### Secrets Management

- Never commit `.env` files (already in `.gitignore`)
- Use Docker secrets or Kubernetes secrets in production
- Rotate API keys regularly

### Data Privacy

- Scraped data may contain personal information
- Comply with GDPR/CCPA if storing user data
- Implement data retention policies
- Encrypt sensitive data at rest if required

### Network Security

- Deploy in private VPC/subnet when possible
- Use firewalls to restrict access to API ports
- Enable monitoring for unusual access patterns

---

## Backup and Restore

### Backup

```bash
# Backup vector database
tar -czf vector_db_backup_$(date +%Y%m%d).tar.gz data/vector_db/

# Backup configuration
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/
```

### Restore

```bash
# Stop API
docker-compose down

# Restore database
tar -xzf vector_db_backup_YYYYMMDD.tar.gz -C .

# Restore config if needed
tar -xzf config_backup_YYYYMMDD.tar.gz -C .

# Restart
docker-compose up -d
```

---

## Performance Tuning

### Database Queries

- Use appropriate `k` values (10-50 for most use cases)
- Apply metadata filters to reduce search space
- Adjust ChromaDB `hnsw_config` for your hardware

### Embedding Generation

- Use batch embedding for bulk operations
- Cache embeddings to avoid re-computation
- Consider local models for offline/low-budget deployments

### LLM Generation

- Use GPT-4 for quality, GPT-3.5-turbo for speed/cost
- Adjust `temperature` (0.0-1.0) based on use case
- Set appropriate `max_tokens` to control response length

---

## Support

For issues, questions, or contributions:

- GitHub Issues: [Repository Issues Page]
- Documentation: See `/docs` directory
- API Reference: http://localhost:8000/docs (when running)

---

**Last Updated:** 2024-01-15