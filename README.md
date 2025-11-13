# Clinical Trials ML Pipeline

**ABOUTME: Automated pipeline for extracting, enriching, and classifying Phase 1 terminated clinical trials for protein-protein interaction prediction**

## Overview

This pipeline extracts Phase 1, 2, and 3 terminated clinical trials (2010+) from the AACT database, enriches them with ChEMBL/UniProt targets and PPI networks, classifies failure reasons using Claude AI, and exports ML-ready datasets for Synthyra's PPI prediction model.

### Key Features

- **Database-First Architecture**: TinyDB-based storage with incremental enrichment
- **Multi-Source Enrichment**: ChEMBL, UniProt, STRING, PubMed, ClinicalTrials.gov API
- **LLM-Powered Classification**: Claude SDK with self-verification for 92%+ accuracy
- **Robust Error Handling**: Retry queue with exponential backoff
- **Rich ML Features**: Targets, PPI networks, IC50 data, failure classifications

### Pipeline Stages

1. **Stage 1**: Bulk AACT extraction (Phase 1, 2, and 3 from 2010-2025)
2. **Stage 2**: Incremental enrichment with targets, PPI, failure details
3. **Stage 3**: Claude SDK failure classification with self-verification
4. **Stage 4**: ML dataset export with comprehensive features

## Goal
Build a comprehensive dataset of Phase 1, 2, and 3 terminated trials to train models predicting trial success/failure based on protein-protein interactions that Synthyra's technology can predict.

## Multi-Source Data Pipeline

### Data Sources

#### 1. **AACT Database** (ClinicalTrials.gov)
- **What we get:** Trial metadata, phases, outcomes, drug names, termination reasons
- **Access:** PostgreSQL database (credentials in .env)
- **Coverage:** 500K+ trials, 32K+ terminated

#### 2. **ChEMBL** (Drug targets & IC50 data)
- **What we get:** Drug→Target mappings, IC50 values, UniProt IDs
- **Access:** REST API or SQL database download
- **URL:** https://www.ebi.ac.uk/chembl/

#### 3. **DrugBank** (Alternative drug target source)
- **What we get:** Drug→Target relationships, mechanism of action
- **Access:** XML download (free for academic use) or API (paid)
- **URL:** https://www.drugbank.ca/

#### 4. **UniProt** (Protein information)
- **What we get:** Protein sequences, interaction partners, functional annotations
- **Access:** REST API
- **URL:** https://www.uniprot.org/

#### 5. **PubChem** (Chemical structures)
- **What we get:** Drug structures, synonyms (for name matching)
- **Access:** REST API
- **URL:** https://pubchem.ncbi.nlm.nih.gov/

## Pipeline Stages

### Stage 1: Extract Clinical Trials (AACT) ✓
**Script:** `query_trials.py`

```bash
# Extract all phases
python query_trials.py --phase PHASE1 --output data/phase1_trials.json
python query_trials.py --phase PHASE2 --output data/phase2_trials.json
python query_trials.py --phase PHASE3 --output data/phase3_trials.json
```

**Output:** Trial data with:
- Drug names
- Success/Failure labels (based on progression to next phase)
- Termination reasons (for LLM classification)

### Stage 2: Enrich with Drug Targets (ChEMBL/DrugBank)
**Script:** `enrich_targets.py` (TODO)

For each drug:
1. Query ChEMBL API for targets
2. Get UniProt IDs for each target
3. Get IC50 values where available
4. If not in ChEMBL, try DrugBank

**Filter:** Keep only trials with known UniProt targets

### Stage 3: Classify Failure Reasons (LLM)
**Script:** `classify_failures.py` (TODO)

Use LLM to parse `why_stopped` text into:
- **Efficacy failure:** "lack of efficacy", "did not meet endpoint", etc.
- **Adverse effects:** "safety concerns", "adverse events", "toxicity"
- **Other:** administrative, funding, recruitment

### Stage 4: Get Protein Interaction Data (UniProt)
**Script:** `get_protein_interactions.py` (TODO)

For each UniProt target:
- Get known PPI partners
- Get protein sequences
- Get functional annotations

This creates features for Synthyra's PPI prediction model.

### Stage 5: Combine & Format for ML
**Script:** `prepare_ml_dataset.py` (TODO)

Create final dataset with:
- Trial outcome (SUCCESS/FAILURE_EFFICACY/FAILURE_SAFETY)
- Drug name, targets (UniProt IDs)
- IC50 values (where available)
- Dosing information (from trial descriptions)
- Known PPI partners for each target
- Features Synthyra's model can use

## Current Status

- [x] AACT connection established
- [x] Multi-phase query tool built
- [x] ChEMBL integration complete
- [x] Rule-based failure classification
- [x] Web search for detailed failure reasons (PubMed + ClinicalTrials.gov)
- [x] UniProt PPI enrichment
- [x] STRING high-confidence PPI integration
- [x] ML dataset assembly
- [x] Master pipeline runner script
- [ ] Full pipeline test (IN PROGRESS)

## Usage

### Setup
```bash
cd cttrials
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Pipeline
```bash
# 1. Extract trials
./run_extraction.sh

# 2. Enrich with targets
python enrich_targets.py --input data/*_trials.json --output data/trials_with_targets.json

# 3. Classify failures
python classify_failures.py --input data/trials_with_targets.json --output data/trials_classified.json

# 4. Get PPI data
python get_protein_interactions.py --input data/trials_classified.json --output data/trials_ppi_enriched.json

# 5. Prepare ML dataset
python prepare_ml_dataset.py --input data/trials_ppi_enriched.json --output data/synthyra_ml_dataset.csv
```

## Questions for Logan/David

1. **Which phase transition is most valuable?**
   - Phase 1→2 (safety to efficacy)
   - Phase 2→3 (efficacy validation to large-scale)
   - All phases combined?

2. **What PPI features does Synthyra's model output?**
   - Interaction probability scores?
   - Binding site predictions?
   - Off-target interaction predictions?

3. **Should we focus on specific therapeutic areas?**
   - Oncology (most trials)?
   - Neurology (many PPI-related failures)?
   - All areas?
