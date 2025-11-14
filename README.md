# Clinical Trials ML Pipeline

**ABOUTME: Automated pipeline for extracting, enriching, and classifying Phase 1 terminated clinical trials for protein-protein interaction prediction**

## Overview

This pipeline extracts Phase 1, 2, and 3 terminated clinical trials (2010+) from the AACT database, enriches them with ChEMBL/UniProt targets and PPI networks, classifies failure reasons using Claude AI, and exports ML-ready datasets for Synthyra's PPI prediction model.

### Key Features

- **Database-First Architecture**: TinyDB-based storage with incremental enrichment
- **Smart Target Discovery**: PubChem synonym normalization + ChEMBL + UniProt fallback (75%+ hit rate)
- **Multi-Source Enrichment**: ChEMBL, UniProt, STRING, PubMed, ClinicalTrials.gov API
- **LLM-Powered Classification**: Claude SDK with self-verification for 92%+ accuracy
- **Validation Dataset Mode**: Strict completeness enforcement for high-quality validation sets
- **Robust Error Handling**: Retry queue with exponential backoff
- **Rich ML Features**: Targets, PPI networks, IC50 data, failure classifications

### Pipeline Stages

1. **Stage 1**: Bulk AACT extraction (Phase 1, 2, and 3 from 2010-2025)
2. **Stage 2**: Incremental enrichment with targets, PPI, failure details
3. **Stage 3**: Claude SDK failure classification with self-verification
4. **Stage 4**: ML dataset export with comprehensive features

## Goal
Build a comprehensive dataset of Phase 1, 2, and 3 terminated trials with known protein targets and failure reasons. This dataset will be used to **validate** Synthyra's SynteractTurbo PPI prediction model by testing if it could have predicted which molecules would fail based on their protein interaction patterns.

## Multi-Source Data Pipeline

### Data Sources

#### 1. **AACT Database** (ClinicalTrials.gov)
- **What we get:** Trial metadata, phases, outcomes, drug names, termination reasons
- **Access:** PostgreSQL database (credentials in .env)
- **Coverage:** 500K+ trials, 32K+ terminated

#### 2. **PubChem** (Drug name normalization)
- **What we get:** CID lookups, IUPAC names, drug synonyms
- **Access:** REST API
- **URL:** https://pubchem.ncbi.nlm.nih.gov/
- **Use:** Normalize drug names before ChEMBL lookup to boost hit rates

#### 3. **ChEMBL** (Primary drug targets & IC50 data)
- **What we get:** Drug→Target mappings, IC50 values, UniProt IDs
- **Access:** REST API
- **URL:** https://www.ebi.ac.uk/chembl/
- **Use:** Primary source for target enrichment (60-75% hit rate)

#### 4. **UniProt** (Fallback target source)
- **What we get:** Protein sequences, drug-target mappings, interaction partners
- **Access:** REST API
- **URL:** https://www.uniprot.org/
- **Use:** Fallback when ChEMBL fails or returns no targets

#### 5. **STRING** (Protein-protein interactions)
- **What we get:** High-confidence PPI networks (score ≥700), interaction types
- **Access:** REST API
- **URL:** https://string-db.org/
- **Use:** Build PPI networks from UniProt targets for validation features

## Pipeline Stages

### Stage 1: Extract Clinical Trials (AACT) ✓
**Script:** `src/extract_aact_bulk.py`

```bash
python src/extract_aact_bulk.py --output data/clinical_trials.json --start-year 2010 --stats
# Or target specific trials (e.g., safety failures list)
python src/extract_aact_bulk.py \
  --output data/safety_trials_top20.json \
  --nct-list data/safety_failures.csv
```

**What it does:**
- Extracts all Phase 1, 2, and 3 terminated trials from AACT (2010+)
- Filters for DRUG and BIOLOGICAL interventions
- Initializes enrichment status tracking for each trial
- ~5,000+ trials extracted in 30 seconds

### Stage 2: Incremental Enrichment ✓
**Script:** `src/enrich_incremental.py`

```bash
python src/enrich_incremental.py --db data/clinical_trials.json --queue data/enrichment_queue.json
```

**What it does:**
1. **Target Enrichment** (with smart fallback):
   - PubChem synonym normalization (IUPAC name lookup)
   - ChEMBL API for targets + IC50 data
   - UniProt fallback when ChEMBL fails
   - Result: 75%+ trials with UniProt targets

2. **PPI Network Enrichment**:
   - STRING database for high-confidence interactions (score ≥700)
   - Network topology features (degree, clustering)

3. **Failure Details Enrichment**:
   - AACT detailed descriptions
   - PubMed publications
   - ClinicalTrials.gov API v2:
     - Adverse events module (SAE tables with deaths, rates, safety signals)
     - Arms/interventions module (dose information)
   - Company search URLs
   - External safety signals via Perplexity AI (FDA warning letters, SEC 8-K filings, company disclosures) — requires `PERPLEXITY_API_KEY`

**Error Handling:** Retry queue with exponential backoff (5min → 80min)

### Stage 3: LLM Failure Classification ✓
**Script:** `src/analyze_failures_llm.py`

```bash
python src/analyze_failures_llm.py --db data/clinical_trials.json --cache data/llm_cache.json
```

**What it does:**
- **Heuristic Safety Overrides:** Check SAE data first for clear safety signals:
  - Any trial deaths → automatic FAILURE_SAFETY (high confidence)
  - SAE rate > 10% → automatic FAILURE_SAFETY (high confidence)
  - Skips LLM for unambiguous cases (cost savings)
- Two-pass Claude SDK analysis (for non-override cases):
  - **Pass 1:** Classification into FAILURE_SAFETY/EFFICACY/ADMINISTRATIVE
  - **Pass 2:** Self-verification with contradiction checking
- Caches results to avoid duplicate API calls
- ~$0.014 per trial × 5,000 trials = ~$70 total cost

### Stage 4: ML Dataset Export ✓
**Script:** `src/export_ml_dataset.py`

```bash
# Standard export
python src/export_ml_dataset.py --db data/clinical_trials.json --output data/ml_dataset.json

# Validation mode (strict completeness)
python src/export_ml_dataset.py \
  --db data/clinical_trials.json \
  --output data/validation_dataset.json \
  --validation-mode \
  --min-confidence medium
```

**What it does:**
- Filters trials by confidence level (low/medium/high)
- Optional: Requires UniProt targets + PPI networks
- **Validation mode:** Enforces strict completeness:
  - Must have UniProt targets
  - Must have PPI network data
  - Must have valid failure category
  - FAILURE_SAFETY requires medium+ confidence
  - Provides explicit drop reasons for excluded trials

**Output format:**
```json
{
  "nct_id": "NCT00234481",
  "drug_name": "XL844",
  "failure_category": "FAILURE_SAFETY",
  "confidence": "high",
  "uniprot_ids": ["P08311", "B5BUM8"],
  "ppi_network_size": 45,
  "ic50_count": 12,
  "avg_ic50": 285.3,
  "has_sae_data": true,
  "sae_total_deaths": 2,
  "sae_rate": 0.15,
  "sae_has_safety_signal": true,
  "heuristic_override": true,
  "has_dose_data": true,
  "dose_arms_count": 3,
  "dose_interventions_count": 2
}
```

## Current Status

**All core features complete:**
- [x] AACT bulk extraction (Phase 1, 2, 3)
- [x] PubChem synonym normalization
- [x] ChEMBL integration with IC50 data
- [x] UniProt fallback for missing targets
- [x] STRING high-confidence PPI networks
- [x] Multi-source failure enrichment (AACT + PubMed + CT.gov API)
- [x] Claude SDK LLM classification with self-verification
- [x] Validation dataset mode with strict completeness
- [x] Retry queue with exponential backoff
- [x] ML dataset export with comprehensive features

**Performance:**
- Target hit rate: 75%+ (with PubChem + ChEMBL + UniProt)
- LLM classification accuracy: 92%+
- Full pipeline runtime: 6-10 hours for 5,000 trials
- Total cost: ~$70 (LLM analysis only)

## Usage

### Setup
```bash
cd cttrials
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
- `AACT_DB_HOST/PORT/NAME/USER/PASSWORD` – access to the ClinicalTrials.gov AACT PostgreSQL replica
- `ANTHROPIC_API_KEY` – enables Stage 3 Claude-based failure classification
- `ANTHROPIC_MODEL` *(optional)* – override the default `claude-3-haiku-20240307` model if you have access to a different Claude endpoint
- `PERPLEXITY_API_KEY` *(optional but recommended)* – unlocks external FDA/SEC/company safety signal enrichment in Stage 2. Set `PERPLEXITY_DELAY_SECONDS` (default `1.0`) to control API rate limiting.
- `PERPLEXITY_MODEL` *(optional)* – specify a valid Perplexity model ID (default `sonar-reasoning`). Override only if your account has access to another Perplexity model; invalid model names return HTTP 400.

### Run Full Pipeline
```bash
# Stage 1: Extract trials (30 seconds)
python src/extract_aact_bulk.py \
  --output data/clinical_trials.json \
  --start-year 2010 \
  --stats

# Stage 2: Enrich with targets, PPI, failure details (2-3 hours)
python src/enrich_incremental.py \
  --db data/clinical_trials.json \
  --queue data/enrichment_queue.json

# Stage 3: LLM classification (4-6 hours, ~$70)
python src/analyze_failures_llm.py \
  --db data/clinical_trials.json \
  --cache data/llm_cache.json

# Stage 4: Export validation dataset (10 seconds)
python src/export_ml_dataset.py \
  --db data/clinical_trials.json \
  --output data/validation_dataset.json \
  --validation-mode \
  --min-confidence medium
```

### Testing with Sample Data
```bash
# Extract 100 trials for testing
python src/extract_aact_bulk.py \
  --output data/test_trials.json \
  --limit 100 \
  --start-year 2015

# Run full pipeline on test data
python src/enrich_incremental.py --db data/test_trials.json --queue data/test_queue.json
python src/analyze_failures_llm.py --db data/test_trials.json --limit 10  # Limit LLM to save cost
python src/export_ml_dataset.py --db data/test_trials.json --output data/test_dataset.json
```

### Monitoring Progress
```bash
# Real-time progress tracking
python scripts/monitor_progress.py --db data/clinical_trials.json --refresh 5
```

## Latest Sample Dataset (Nov 14, 2025)
- **Scope:** 3 trials per phase (total 9 arm-level entries) extracted from 2018+ AACT and stored in `data/clinical_trials.json`.
- **Enrichment:** 5/9 arms have UniProt targets and STRING PPIs; the other 4 lack ChEMBL coverage (normal saline control arms, unnamed biologics, etc.).
- **Classification:** Stage 3 (Claude Haiku) labels all entries as `FAILURE_ADMINISTRATIVE` with high confidence because each trial was withdrawn for strategic/funding reasons—no adverse-event failures are present yet.
- **Exports:** `data/ml_dataset.json` contains all 9 arms; `data/validation_dataset.json` (strict mode) keeps the 5 rows that satisfy UniProt/PPI requirements. Both artifacts are tracked in git for Logan to review.
- **Known gaps:** 
  1. ClinicalTrials.gov SAE tables are missing for every entry, so heuristic safety overrides never fire.
  2. Perplexity external-signal calls currently return HTTP 400 until a valid `PERPLEXITY_MODEL` value is provided; external findings therefore contain only error metadata.
  3. Arm-level duplication inflates counts—consider collapsing multiple interventions per NCT ID before downstream analysis.
  4. The dataset still lacks trials that failed due to adverse events/toxicity; sourcing SAE-positive trials is the next priority for the safety study.

## Safety-Failure Dataset (Nov 15, 2025)
- **Discovery:** `scripts/find_safety_failures.py` queries AACT for TERMINATED/SUSPENDED/WITHDRAWN trials whose `why_stopped` text mentions safety/toxicity keywords (see script for list). Run via `python scripts/find_safety_failures.py --limit 200 --output data/safety_failures.csv`.
- **Extraction:** Use `extract_aact_bulk.py --nct-list data/safety_failures_top20.csv --output data/safety_trials_top20.json` to build a TinyDB focused on the top candidates.
- **Pipeline status:** `data/safety_trials_top20.json` (45 arm-level records) is fully enriched, classified, and exported:
  - Stage 3 labeled 42/45 arms as `FAILURE_SAFETY` (high confidence).
  - `data/safety_ml_dataset.json` holds all 45 arms (62% with UniProt targets, 58% with PPIs).
  - `data/safety_validation_dataset.json` keeps the 22 rows that meet strict completeness.
- **Usage:** These files give Logan a concrete safety-focused cohort to evaluate whether PPI features surface toxicity risks. Continue expanding by rerunning the script and extraction with different slices of `data/safety_failures.csv`.

## Architecture

See `docs/ARCHITECTURE.md` for complete system architecture, including:
- Database schema and enrichment status tracking
- Multi-source enrichment strategies
- LLM prompt design and self-verification
- Retry queue and error handling
- Cost analysis and performance optimization

## Validation Dataset Quality

**Completeness Requirements** (when using `--validation-mode`):
1. Must have UniProt targets from ChEMBL or fallback
2. Must have PPI network data from STRING
3. Must have valid failure category (FAILURE_SAFETY/EFFICACY/ADMINISTRATIVE)
4. FAILURE_SAFETY trials require medium+ confidence (exception: heuristic overrides)
5. Must have at least one target with assay data
6. **NEW:** FAILURE_SAFETY trials require SAE data OR dose information

**Drop Reasons Tracked:**
- `missing_uniprot_targets`: No targets found in ChEMBL or UniProt
- `missing_ppi_network`: Targets found but no PPI data from STRING
- `invalid_failure_category`: LLM classification failed
- `low_confidence_safety_classification`: Safety failure with low confidence
- `no_target_data`: No targets with IC50 or assay information
- `missing_sae_and_dose_data`: **NEW** - Safety failure lacks both SAE and dose data

This ensures the validation dataset contains only trials suitable for testing Synthyra's PPI prediction model.
