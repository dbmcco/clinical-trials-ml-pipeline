#!/bin/bash
# ABOUTME: Run complete clinical trials ML pipeline (all 4 stages)

set -e  # Exit on error

echo "=========================================="
echo "CLINICAL TRIALS ML PIPELINE - FULL RUN"
echo "=========================================="

# Check environment
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found"
    echo "Copy .env.example to .env and configure your credentials"
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "❌ ERROR: venv not found. Run: python3.11 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate

# Stage 1: Extract from AACT
echo ""
echo "[Stage 1/4] Extracting Phase 1 terminated trials from AACT..."
python src/extract_aact_bulk.py \
    --output data/clinical_trials.json \
    --start-year 2010 \
    --stats

# Stage 2: Incremental enrichment
echo ""
echo "[Stage 2/4] Enriching trials with targets, PPI, and failure details..."
python src/enrich_incremental.py \
    --db data/clinical_trials.json \
    --queue data/enrichment_queue.json

# Stage 3: LLM failure classification
echo ""
echo "[Stage 3/4] Analyzing failure reasons with Claude SDK..."
python src/analyze_failures_llm.py \
    --db data/clinical_trials.json \
    --cache data/llm_analysis_cache.json

# Stage 4: Export ML dataset
echo ""
echo "[Stage 4/4] Exporting ML dataset..."
python src/export_ml_dataset.py \
    --db data/clinical_trials.json \
    --output data/ml_dataset.json

# Also export Synthyra-specific dataset
python src/export_ml_dataset.py \
    --db data/clinical_trials.json \
    --output data/ml_dataset_synthyra.json \
    --synthyra-ppi

echo ""
echo "=========================================="
echo "✅ PIPELINE COMPLETE"
echo "=========================================="
echo ""
echo "Output files:"
echo "  - data/clinical_trials.json (enriched database)"
echo "  - data/ml_dataset.json (ML dataset)"
echo "  - data/ml_dataset_synthyra.json (Synthyra PPI dataset)"
echo ""
