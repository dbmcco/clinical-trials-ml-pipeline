# Quick Start Guide - Clinical Trials Analysis

## What We Built

A multi-stage pipeline to create a machine learning dataset for predicting clinical trial outcomes based on protein-protein interactions.

## Pipeline Overview

```
[AACT DB] → Extract Trials → Enrich Targets → Classify Failures → ML Dataset
             query_trials.py   enrich_targets.py  classify_failures.py
```

## Current Status

✅ **Stage 1: Extract Trials** (query_trials.py)
- Queries AACT PostgreSQL database
- Gets all trials for specified phase
- Labels SUCCESS (progressed to next phase) vs FAILURE (terminated)
- **Running now for Phase 1**

✅ **Stage 2: Enrich with Targets** (enrich_targets.py)
- Queries ChEMBL API for each drug
- Gets drug→target mappings
- Gets IC50 values where available
- Gets UniProt IDs for each target
- **Filters to only trials with known UniProt targets**

✅ **Stage 3: Classify Failures** (classify_failures.py)
- Rule-based NLP on `why_stopped` text
- Categories: EFFICACY, SAFETY, OTHER
- Ready for Logan/David's 3-category model

🔜 **Stage 4: Get PPI Data** (get_protein_interactions.py)
- Query UniProt for protein interaction partners
- Create features for Synthyra's PPI model

🔜 **Stage 5: ML Dataset** (prepare_ml_dataset.py)
- Combine all enrichment data
- Format for training/testing
- Output CSV/JSON for ML pipeline

## Usage

### 1. Extract Trials (All Phases)

```bash
cd cttrials
source venv/bin/activate

# Phase 1
python query_trials.py --phase PHASE1 --output data/phase1_trials.json

# Phase 2
python query_trials.py --phase PHASE2 --output data/phase2_trials.json

# Phase 3
python query_trials.py --phase PHASE3 --output data/phase3_trials.json
```

**Output:** JSON file with trials labeled SUCCESS/FAILURE

### 2. Enrich with Drug Targets

```bash
# This queries ChEMBL API - takes ~1 min per 10 drugs
python enrich_targets.py \
  --input data/phase1_trials.json \
  --output data/phase1_enriched.json
```

**Output:** Same JSON + target info (UniProt IDs, IC50 values)

**Note:** This automatically filters to only trials with known UniProt targets!

### 3. Classify Failure Reasons

```bash
python classify_failures.py \
  --input data/phase1_enriched.json \
  --output data/phase1_classified.json
```

**Output:** Failures categorized as EFFICACY, SAFETY, or OTHER

## Data Flow Example

### Input (from AACT):
```json
{
  "nct_id": "NCT12345678",
  "drug_name": "Pembrolizumab",
  "phase": "PHASE1",
  "overall_status": "TERMINATED",
  "why_stopped": "Lack of efficacy in preliminary analysis",
  "label": "FAILURE"
}
```

### After Enrichment (ChEMBL):
```json
{
  ...same as above...
  "chembl_enrichment": {
    "found": true,
    "chembl_id": "CHEMBL1201585",
    "targets": [
      {
        "chembl_id": "CHEMBL2047",
        "uniprot_id": "Q15116",
        "ic50_values": [
          {"value": 2.5, "units": "nM"}
        ]
      }
    ],
    "has_uniprot_targets": true
  }
}
```

### After Classification:
```json
{
  ...same as above...
  "failure_classification": {
    "category": "EFFICACY",
    "confidence": "high",
    "reason": "Lack of efficacy in preliminary analysis"
  }
}
```

## For Logan/David

### Questions:

1. **Which phase is most valuable?**
   - Phase 1→2 (safety screen)
   - Phase 2→3 (efficacy validation)
   - All phases?

2. **What PPI features does Synthyra's model provide?**
   - We need to know what features to extract from UniProt
   - Interaction probabilities?
   - Off-target predictions?

3. **Therapeutic area focus?**
   - All drugs?
   - Specific areas (oncology, neurology)?

### Next Steps:

1. Wait for Phase 1 extraction to complete
2. Run enrichment on small sample to test ChEMBL integration
3. Build Stage 4 (PPI enrichment) based on Synthyra model requirements
4. Format final ML dataset

## Data Sources

- **AACT:** 500K+ trials from ClinicalTrials.gov
- **ChEMBL:** 2.3M+ compounds, 15K+ targets, IC50 data
- **UniProt:** 220M+ protein sequences, PPI networks

## Notes

- ChEMBL API has rate limits (~10 requests/sec)
- Large extractions take time (Phase 1 = ~15K drugs)
- Enrichment auto-saves progress every 50 trials
- All scripts support resume/restart

## Credentials

Database credentials are in `.env` (already configured and gitignored).
