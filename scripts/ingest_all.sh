#!/bin/bash

# Unified Data Ingestion Pipeline Script
# This script runs the complete RAG ingestion pipeline

set -e  # Exit on error
set -u  # Error on undefined variable

echo "========================================"
echo "  RAG Data Ingestion Pipeline"
echo "========================================"
echo ""

# Check Python environment
echo "[1/4] Checking Python environment..."
python3 --version || python --version

# Ensure required directories exist
echo "[2/4] Ensuring directory structure..."
mkdir -p data/raw data/processed logs

# Install dependencies if needed (uncomment if needed)
# echo "[3/4] Checking dependencies..."
# pip install -r requirements.txt

# Run the pipeline
echo "[3/4] Running ingestion pipeline..."
if [ -f ".env" ]; then
    echo "Loading environment from .env"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Run the pipeline module
PYTHONPATH="${PYTHONPATH:-.}" python -m src.pipeline "$@"

PIPELINE_EXIT_CODE=$?

if [ $PIPELINE_EXIT_CODE -eq 0 ]; then
    echo "[4/4] Pipeline completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  - Check logs/ingestion_*.log for details"
    echo "  - Check data/processed/ for chunk files"
    echo "  - Run database initialization and embedding (Phase 3)"
else
    echo "[4/4] Pipeline failed with exit code $PIPELINE_EXIT_CODE"
    echo "Check logs/ingestion_*.log for error details"
fi

exit $PIPELINE_EXIT_CODE
