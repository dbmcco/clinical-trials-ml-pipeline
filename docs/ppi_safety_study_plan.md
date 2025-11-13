# PPI Safety Study Data Needs & Process Plan

## Context
- Study objective (README.md:24-26): Validate SynteractTurbo by replaying terminated Phase 1–3 trials and checking whether PPI features would have predicted adverse outcomes.
- Current pipeline (`src/` executables + TinyDB store) already handles base extraction (AACT), enrichment (ChEMBL/STRING), LLM classification, and ML export, but it depends heavily on AACT fields and exposes only limited failure/dosing/assay information.
- AACT alone rarely states specific toxicity causes and never contains UniProt/IC50/dose metrics; these must be sourced elsewhere and consistently merged.

## Data Gaps to Close
1. **Failure Evidence**
   - `why_stopped` text is sparse; serious adverse events tables, publications, regulatory filings, and sponsor communications hold the real toxicology signal.
   - No structured storage for SAE counts, toxicity keywords, or supporting documents beyond raw JSON blobs in `failure_enrichment`.
2. **Target Coverage & Assay Detail**
   - Pipeline only queries ChEMBL via a naive text lookup; misses synonyms, biologics, and lacks fallback to DrugBank/PubChem.
   - UniProt IDs and IC50/Ki values are absent whenever ChEMBL fails, contradicting README guarantees.
3. **Dose & Exposure**
   - Dose descriptions in CT.gov (`armsInterventionsModule`) and publications are not parsed; exported datasets omit mg/kg or µg info needed to correlate exposure with toxicity.
4. **Traceability for PPI Replay**
   - No guarantee that exported “FAILURE_SAFETY” trials include all three pillars (targets, PPI network, dosing). Missing pieces silently pass through or require manual filtering.

## Process Update Plan
### 1. Multi-Source Enrichment
- **Synonym normalization**: Map intervention names to PubChem CIDs before calling ChEMBL to boost hit rates.
- **DrugBank/PubChem ingestion**: Parse DrugBank XML for target ↔ UniProt links, mechanisms, and assay values; fall back to PubChem/UniProt search when ChEMBL misses.
- **Provenance tracking**: Store per-target source, assay type, and units to keep downstream analytics trustworthy.

### 2. Safety Evidence Module
- Extend Stage 2 to harvest:
  - CT.gov v2 `adverseEventsModule` (SAE counts per arm, toxicity grades).
  - PubMed abstracts/full text via EFetch with an extractor tuned for toxicity phrases.
  - External signals (FDA letters, investor filings) via sponsor/company search URLs scraped into structured summaries.
- Persist normalized fields (e.g., `safety_signal.type`, `evidence_level`, `supporting_refs`) for the LLM to consume and for auditors to inspect.

### 3. Classification & Cohort Definition
- Update Stage 3 prompts to reference structured SAE data first, falling back to text only if needed.
- Introduce deterministic heuristics (e.g., SAE rate > control) to cross-check the LLM label and force `FAILURE_SAFETY` when quantitative evidence exists.
- Add a CLI filter to emit the “safety failure” cohort for replay without manual database queries.

### 4. Dose & Exposure Parsing
- Parse CT.gov dose descriptions into canonical units; when absent, look for dosing info in PubMed or documents.
- Attach dose metadata to each target-exposure pair so PPI model inputs include approximate systemic exposure.

### 5. Export & Evaluation Glue
- Require (configurable) presence of:
  1. Safety failure label (LLM or heuristic),
  2. UniProt targets with assay data,
  3. Dose info.
- Emit explicit reasons when a trial is dropped (e.g., `missing_target_mapping`) so analysts can remediate.
- Provide a scripted hand-off that reads the Synthyra export and submits each molecule to the PPI scoring service, capturing predictions for retrospective analysis.

## Implementation Milestones
1. **Data Ingestion**
   - Build synonym normalization + DrugBank parser.
   - Add CT.gov SAE + PubMed EFetch collectors with structured storage.
2. **Classification Enhancements**
   - Update LLM prompts/templates, add heuristic overrides, and extend tests to cover safety labeling.
3. **Feature Extraction**
   - Implement dose parser and augment IC50/Ki aggregation with assay context.
4. **Export/Automation**
   - Enforce inclusion criteria, produce safety cohort export, and add replay script skeleton.
5. **Documentation & Validation**
   - Refresh README/runbooks to reflect the multi-source process.
   - Add deterministic tests using fixtures for new modules; document any dependencies (DrugBank dumps, API keys).

## Next Actions
1. Socialize this plan with data/ML stakeholders to confirm requirements and prioritize milestones.
2. Create tickets for each milestone with owners/due dates.
3. Begin with ingestion workstreams (highest dependency) while defining schemas for safety evidence and assay metadata.
