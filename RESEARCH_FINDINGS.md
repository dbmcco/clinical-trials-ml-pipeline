# Clinical Trials Analysis - Research Findings & Implementation

## The Problem We Had

**Symptom:** 5.3 million rows from ~4,900 unique trials
**Root Cause:** Cartesian product from improper JOIN structure
**File Size:** 3.1 GB (unusable)

## What the Research Revealed

### 1. Unit of Analysis (Critical Decision)

**Academic Standards:**
- **MIT Study (2019):** Drug-indication pairs → 406K entries from 186K trials (2x expansion)
- **TrialBench (2025):** Trial-level → 420K trials with nested drug info

**For Synthyra PPI Analysis:**
✅ **Use PER-TRIAL with drug aggregation**

**Why:**
1. PPI analysis operates on protein targets at trial level
2. Avoids artificial dataset inflation (same trial ≠ 3 independent samples)
3. Phase progression is trial-level (FDA doesn't approve drugs separately in combos)
4. Simpler ML pipeline: 1 trial = 1 training example

### 2. The SQL Fix (Research-Backed Pattern)

**Problem Pattern (Your Original Code):**
```sql
-- Creates cartesian product
SELECT * FROM studies s
JOIN interventions i ON s.nct_id = i.nct_id  -- Multiple rows per trial
-- Then checks progression for EACH row
```

**Correct Pattern (Aggregation-First):**
```sql
WITH terminated_trials AS (
    SELECT
        s.nct_id,
        s.brief_title,
        -- KEY: Aggregate drugs into array FIRST
        ARRAY_AGG(DISTINCT i.name) FILTER (...) as drug_names,
        STRING_AGG(DISTINCT i.name, '; ') as drug_list
    FROM ctgov.studies s
    JOIN ctgov.interventions i ON s.nct_id = i.nct_id
    WHERE s.phase = 'PHASE1'
      AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
    GROUP BY s.nct_id, s.brief_title, ...  -- ONE ROW PER TRIAL
),
next_phase_drugs AS (
    SELECT DISTINCT LOWER(i.name) as drug_name_lower
    FROM ctgov.studies s
    JOIN ctgov.interventions i ON s.nct_id = i.nct_id
    WHERE s.phase = 'PHASE2'
)
SELECT
    t.*,
    -- Check if ANY drug progressed
    EXISTS(
        SELECT 1
        FROM UNNEST(t.drug_names) as drug
        WHERE LOWER(drug) IN (SELECT drug_name_lower FROM next_phase_drugs)
    ) as any_drug_progressed
FROM terminated_trials t;
```

**Result:** ~4,900 rows (ONE per trial) instead of 5.3M

### 3. Trial Success Definition

**Standard Approach (from research):**
- **SUCCESS:** If ANY drug from the trial progressed to next phase
- **FAILURE_EFFICACY:** Terminated due to lack of efficacy
- **FAILURE_SAFETY:** Terminated due to adverse events
- **FAILURE_OTHER:** Business/enrollment/administrative

**Why "ANY drug":**
- Trial-level analysis means trial "succeeded" if it advanced drug development
- Aligns with TrialBench methodology
- Matches real-world regulatory progression

### 4. Combination Therapy Handling

**Best Practice:**
- Store all drugs as array: `['Drug A', 'Drug B', 'Drug C']`
- Feature: `drug_count = 3`
- Feature: `is_combination_therapy = true`
- Feature: `primary_drug = 'Drug A'` (first listed)

**Don't:**
- Create separate rows for each drug
- Only analyze first drug (loses information)

## What We Built (Corrected)

### File: `query_trials_correct.py`

**Features:**
1. ✅ Per-trial aggregation using `ARRAY_AGG`
2. ✅ Progression check using `EXISTS` + `UNNEST`
3. ✅ Drug count and combination therapy flags
4. ✅ Research-backed methodology (documented in code)

**Expected Output:**
```json
{
  "nct_id": "NCT01909414",
  "drug_names": ["Drug A", "Drug B", "Placebo"],
  "drug_list": "Drug A; Drug B; Placebo",
  "drug_count": 3,
  "primary_drug": "Drug A",
  "is_combination_therapy": true,
  "label": "FAILURE",
  "label_reason": "Lack of efficacy",
  "progressed_to_next_phase": false
}
```

**Size:** ~5-10 MB for 4,900 trials (vs 3.1 GB before)

## Academic Sources Referenced

1. **MIT Clinical Trial Success Rates (2019)**
   - Wong, Siah, Lo
   - Biostatistics, Volume 20, Issue 2
   - Drug-indication pair methodology

2. **TrialBench Multi-Modal Datasets (2025)**
   - Nature Scientific Data
   - 23 AI-ready datasets
   - Trial-level analysis standard

3. **InClinico AI Platform (2023)**
   - Clinical Pharmacology & Therapeutics
   - Phase II→III prediction (0.88 AUC)
   - Multi-modal transformer approach

4. **AACT Database Documentation**
   - CTTI Clinical Trials
   - PostgreSQL schema and best practices

## Implementation Status

### ✅ Completed
- Research on clinical trials ML best practices
- Corrected SQL query with aggregation-first pattern
- New script: `query_trials_correct.py`
- Research findings documentation

### 🔄 Running Now
- Testing corrected query on Phase 1 data
- Expected: ~4,900 rows in <2 minutes

### ⏳ Next Steps
1. Verify corrected output (4,900 trials, not 5.3M rows)
2. Update `run_pipeline.sh` to use correct script
3. Test full enrichment pipeline (stages 2-6)
4. Run on all phases (PHASE1, PHASE2, PHASE3)

## Key Takeaways for Synthyra

**Unit of Analysis:** Per-trial with drug aggregation
**Success Definition:** ANY drug progressed = trial success
**Methodology:** Aligns with TrialBench (Nature 2025)
**Dataset Size:** ~4,900 Phase 1 terminated trials
**Expected ML Features:** Drug count, combination therapy, PPI scores per target

**This approach is optimal for PPI prediction because:**
- Protein interactions operate at target level (not per-drug)
- Statistical independence maintained (each trial is unique)
- Matches academic standards
- Simplifies enrichment pipeline (1 trial → 1 ChEMBL query → N targets)

## Files Created

- `query_trials_correct.py` - Corrected query implementation
- `RESEARCH_FINDINGS.md` - This document
- `API_ACCESS.md` - API registration requirements (none needed)
- `PIPELINE.md` - Complete technical documentation
- `SUMMARY.md` - Project overview

**All enrichment stages (2-6) remain unchanged** - they work at trial level already.
