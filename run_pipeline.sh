#!/bin/bash
# ABOUTME: Master pipeline runner for clinical trials analysis

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Clinical Trials Analysis Pipeline ===${NC}\n"

# Activate venv
source venv/bin/activate

# Create data directory
mkdir -p data

# Default values
PHASE="PHASE1"
LIMIT=""
TEST_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --phase)
            PHASE="$2"
            shift 2
            ;;
        --limit)
            LIMIT="--limit $2"
            shift 2
            ;;
        --test)
            TEST_MODE=true
            LIMIT="--limit 10"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--phase PHASE1|PHASE2|PHASE3] [--limit N] [--test]"
            exit 1
            ;;
    esac
done

if [ "$TEST_MODE" = true ]; then
    echo -e "${YELLOW}Running in TEST MODE (limited to 10 trials)${NC}\n"
fi

# File naming
PHASE_LOWER=$(echo "$PHASE" | tr '[:upper:]' '[:lower:]')
TRIALS_FILE="data/${PHASE_LOWER}_trials.json"
ENRICHED_FILE="data/${PHASE_LOWER}_enriched.json"
CLASSIFIED_FILE="data/${PHASE_LOWER}_classified.json"
DETAILED_FILE="data/${PHASE_LOWER}_detailed.json"
PPI_FILE="data/${PHASE_LOWER}_ppi.json"
ML_CSV="data/${PHASE_LOWER}_ml_dataset.csv"
ML_JSON="data/${PHASE_LOWER}_ml_dataset.json"

# Stage 1: Extract trials from AACT
echo -e "${GREEN}Stage 1: Extracting ${PHASE} trials from AACT${NC}"
if [ ! -f "$TRIALS_FILE" ]; then
    python query_trials.py --phase "$PHASE" --output "$TRIALS_FILE"
    echo -e "✓ Saved to $TRIALS_FILE\n"
else
    echo -e "${YELLOW}⚠ $TRIALS_FILE already exists, skipping extraction${NC}\n"
fi

# Stage 2: Enrich with ChEMBL targets
echo -e "${GREEN}Stage 2: Enriching with drug targets from ChEMBL${NC}"
if [ ! -f "$ENRICHED_FILE" ]; then
    python enrich_targets.py --input "$TRIALS_FILE" --output "$ENRICHED_FILE" $LIMIT
    echo -e "✓ Saved to $ENRICHED_FILE\n"
else
    echo -e "${YELLOW}⚠ $ENRICHED_FILE already exists, skipping enrichment${NC}\n"
fi

# Stage 3: Classify failure reasons
echo -e "${GREEN}Stage 3: Classifying failure reasons${NC}"
if [ ! -f "$CLASSIFIED_FILE" ]; then
    python classify_failures.py --input "$ENRICHED_FILE" --output "$CLASSIFIED_FILE"
    echo -e "✓ Saved to $CLASSIFIED_FILE\n"
else
    echo -e "${YELLOW}⚠ $CLASSIFIED_FILE already exists, skipping classification${NC}\n"
fi

# Stage 4: Search for detailed failure information
echo -e "${GREEN}Stage 4: Searching for detailed failure information${NC}"
if [ ! -f "$DETAILED_FILE" ]; then
    python search_failure_details.py --input "$CLASSIFIED_FILE" --output "$DETAILED_FILE" $LIMIT
    echo -e "✓ Saved to $DETAILED_FILE\n"
else
    echo -e "${YELLOW}⚠ $DETAILED_FILE already exists, skipping detail search${NC}\n"
fi

# Stage 5: Enrich with PPI data
echo -e "${GREEN}Stage 5: Enriching with PPI data from UniProt/STRING${NC}"
if [ ! -f "$PPI_FILE" ]; then
    python enrich_ppi.py --input "$DETAILED_FILE" --output "$PPI_FILE" $LIMIT
    echo -e "✓ Saved to $PPI_FILE\n"
else
    echo -e "${YELLOW}⚠ $PPI_FILE already exists, skipping PPI enrichment${NC}\n"
fi

# Stage 6: Prepare ML dataset
echo -e "${GREEN}Stage 6: Preparing final ML dataset${NC}"
python prepare_ml_dataset.py --input "$PPI_FILE" --output-csv "$ML_CSV" --output-json "$ML_JSON"
echo -e "✓ Saved to $ML_CSV and $ML_JSON\n"

# Summary
echo -e "${BLUE}=== Pipeline Complete ===${NC}"
echo -e "Final ML dataset: ${GREEN}$ML_CSV${NC}"
echo -e "\nData files created:"
ls -lh data/${PHASE_LOWER}* | awk '{print "  " $9 " (" $5 ")"}'
