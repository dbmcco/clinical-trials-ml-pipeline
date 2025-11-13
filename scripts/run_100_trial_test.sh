#!/bin/bash
# ABOUTME: Run 100-trial validation test before full pipeline

set -e

echo "=========================================="
echo "100-TRIAL VALIDATION TEST"
echo "=========================================="

# Check environment
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found"
    exit 1
fi

source venv/bin/activate

# Create test directory
mkdir -p data/test

# Stage 1: Extract 100 trials
echo ""
echo "[1/4] Extracting 100 trials for testing..."
python src/extract_aact_bulk.py \
    --output data/test/test_trials.json \
    --start-year 2015 \
    --limit 100 \
    --stats

# Stage 2: Enrich
echo ""
echo "[2/4] Enriching test trials..."
python src/enrich_incremental.py \
    --db data/test/test_trials.json \
    --queue data/test/test_queue.json

# Stage 3: LLM Analysis (limit to 10 trials to save cost)
echo ""
echo "[3/4] LLM analysis (10 trials to estimate cost)..."
python src/analyze_failures_llm.py \
    --db data/test/test_trials.json \
    --cache data/test/test_cache.json \
    --limit 10

# Stage 4: Export
echo ""
echo "[4/4] Exporting test dataset..."
python src/export_ml_dataset.py \
    --db data/test/test_trials.json \
    --output data/test/test_ml_dataset.json

echo ""
echo "✅ VALIDATION TEST COMPLETE"
echo ""
echo "Review data/test/ directory for results"
echo ""
