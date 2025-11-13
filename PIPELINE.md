# Clinical Trials Analysis Pipeline - Complete Documentation

## Overview

A complete 6-stage pipeline to create ML datasets for predicting clinical trial outcomes using Synthyra's PPI prediction technology.

## Architecture

```
┌─────────────┐
│   AACT DB   │ ClinicalTrials.gov PostgreSQL database
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Extract Trials (query_trials.py)                  │
│ - Query all trials for specified phase                      │
│ - Label SUCCESS (progressed) vs FAILURE (terminated)        │
│ - Output: phase_trials.json                                 │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Enrich Targets (enrich_targets.py)                │
│ - Query ChEMBL API for drug→target mappings                │
│ - Get IC50 values                                           │
│ - Get UniProt IDs                                           │
│ - **Filter to only trials with known UniProt targets**     │
│ - Output: phase_enriched.json                              │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Classify Failures (classify_failures.py)          │
│ - Rule-based NLP on termination reasons                    │
│ - Categories: EFFICACY, SAFETY, OTHER                      │
│ - Output: phase_classified.json                            │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Search Details (search_failure_details.py)        │
│ - Search PubMed for trial publications                     │
│ - Get detailed results from ClinicalTrials.gov             │
│ - Generate Google News search URLs for manual review       │
│ - Output: phase_detailed.json                              │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: Enrich PPI (enrich_ppi.py)                        │
│ - Get protein info from UniProt                            │
│ - Get PPI partners from UniProt                            │
│ - Get high-confidence interactions from STRING             │
│ - Output: phase_ppi.json                                   │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 6: Prepare ML Dataset (prepare_ml_dataset.py)        │
│ - Extract all features into flat format                    │
│ - Create standardized outcome labels                       │
│ - Output: phase_ml_dataset.csv + .json                     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Setup
```bash
cd cttrials
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Full Pipeline
```bash
# Test with 10 trials
./run_pipeline.sh --phase PHASE1 --test

# Full Phase 1 extraction
./run_pipeline.sh --phase PHASE1

# Specific limit
./run_pipeline.sh --phase PHASE2 --limit 100
```

### Run Individual Stages
```bash
source venv/bin/activate

# Stage 1: Extract trials
python query_trials.py --phase PHASE1 --output data/phase1_trials.json

# Stage 2: Enrich with targets (auto-filters to UniProt targets)
python enrich_targets.py \
  --input data/phase1_trials.json \
  --output data/phase1_enriched.json

# Stage 3: Classify failures
python classify_failures.py \
  --input data/phase1_enriched.json \
  --output data/phase1_classified.json

# Stage 4: Search for detailed failure info
python search_failure_details.py \
  --input data/phase1_classified.json \
  --output data/phase1_detailed.json \
  --limit 50  # Optional: limit for testing

# Stage 5: Enrich with PPI data
python enrich_ppi.py \
  --input data/phase1_detailed.json \
  --output data/phase1_ppi.json \
  --limit 50  # Optional: limit for testing

# Stage 6: Prepare ML dataset
python prepare_ml_dataset.py \
  --input data/phase1_ppi.json \
  --output-csv data/phase1_ml_dataset.csv \
  --output-json data/phase1_ml_dataset.json
```

## Data Sources

### 1. AACT Database (ClinicalTrials.gov)
- **What:** 500K+ clinical trials, 32K+ terminated
- **Access:** PostgreSQL (credentials in .env)
- **Data:** Trial metadata, phases, outcomes, drug names, termination reasons

### 2. ChEMBL
- **What:** 2.3M+ compounds, 15K+ targets
- **Access:** REST API (https://www.ebi.ac.uk/chembl/api/data)
- **Data:** Drug→target mappings, IC50 values, UniProt IDs

### 3. UniProt
- **What:** 220M+ protein sequences
- **Access:** REST API (https://rest.uniprot.org)
- **Data:** Protein info, sequences, PPI partners

### 4. STRING
- **What:** 24.6M+ proteins, 4.5B+ interactions
- **Access:** REST API (https://string-db.org/api)
- **Data:** High-confidence PPI scores, interaction evidence

### 5. PubMed
- **What:** 37M+ biomedical literature citations
- **Access:** E-utilities API (https://eutils.ncbi.nlm.nih.gov)
- **Data:** Trial publications, detailed results

## Output Schema

### Final ML Dataset (CSV/JSON)

**Core Fields:**
- `nct_id`: ClinicalTrials.gov identifier
- `drug_name`: Drug/intervention name
- `phase`: PHASE1, PHASE2, or PHASE3
- `outcome`: SUCCESS | FAILURE_EFFICACY | FAILURE_SAFETY | FAILURE_OTHER

**Target Features:**
- `chembl_id`: ChEMBL identifier
- `num_targets`: Number of targets
- `uniprot_ids`: Comma-separated UniProt IDs
- `num_uniprot_targets`: Count of UniProt targets

**IC50 Features:**
- `has_ic50_data`: Boolean
- `ic50_min_nm`: Minimum IC50 (nM)
- `ic50_max_nm`: Maximum IC50 (nM)
- `ic50_mean_nm`: Mean IC50 (nM)

**PPI Features:**
- `has_ppi_data`: Boolean
- `total_uniprot_interactions`: Count from UniProt
- `total_string_interactions`: Count from STRING
- `avg_string_score`: Average interaction confidence
- `max_string_score`: Max interaction confidence
- `target_proteins`: Protein names (semicolon-separated)

**Detail Features:**
- `has_pubmed_data`: Boolean
- `num_pubmed_articles`: Count of publications
- `has_posted_results`: Detailed results on ClinicalTrials.gov

## Logan/David Requirements

✅ **Filter by UniProt target availability** - Stage 2 auto-filters
✅ **3-category outcome model:**
   - SUCCESS (progressed to next phase)
   - FAILURE_EFFICACY (lack of efficacy)
   - FAILURE_SAFETY (adverse effects)
✅ **PPI enrichment** - STRING high-confidence interactions
✅ **IC50 data** - From ChEMBL where available

## Performance & Scale

**Stage 1 (AACT):** ~30 seconds for full phase extraction
**Stage 2 (ChEMBL):** ~1 min per 10 drugs (rate limited)
**Stage 3 (Classify):** Instant (rule-based)
**Stage 4 (Details):** ~30 sec per 10 trials (rate limited)
**Stage 5 (PPI):** ~30 sec per 10 proteins (rate limited)
**Stage 6 (ML Prep):** Instant

**Total for 100 trials:** ~20-30 minutes
**Total for 1000 trials:** ~3-5 hours

**Pro tip:** Use `--limit` for testing, then run full pipeline overnight

## Tips & Tricks

### Resume After Interruption
All scripts save progress periodically. If interrupted:
- Stage 2: Saves every 50 trials
- Stage 4: Saves every 20 trials
- Stage 5: Saves every 10 trials

Just rerun with same output file - it will skip completed work.

### Test Before Full Run
```bash
# Test with 10 trials
./run_pipeline.sh --phase PHASE1 --test

# Review output
head -20 data/phase1_ml_dataset.csv
```

### Parallel Processing
Run different phases in parallel:
```bash
# Terminal 1
./run_pipeline.sh --phase PHASE1 &

# Terminal 2
./run_pipeline.sh --phase PHASE2 &

# Terminal 3
./run_pipeline.sh --phase PHASE3 &
```

### Manual Review of Failures
Stage 4 provides Google News search URLs for each trial. For high-priority failures, use these URLs to find company press releases with detailed reasons.

## Next Steps for Synthyra Integration

1. **Run pipeline on all phases** to get full dataset
2. **Share sample data** with Logan/David for feature validation
3. **Clarify PPI features** needed from Synthyra's model
4. **Integrate Synthyra predictions** as additional features
5. **Train success/failure classifier** using PPI + trial features

## Troubleshooting

**"Connection refused" error:**
- Check .env credentials
- Test: `source venv/bin/activate && python test_connection.py`

**"Rate limit exceeded":**
- APIs have rate limits
- Scripts include delays, but if you hit limits, wait 1 hour

**"No UniProt targets found":**
- Many drugs in ClinicalTrials.gov are not in ChEMBL
- This is expected - pipeline filters these out

**Memory issues with large datasets:**
- Process phases separately
- Use `--limit` to process in batches
- Combine results manually if needed
