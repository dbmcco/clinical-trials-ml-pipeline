# API Access Guide - Do You Need to Register?

## Quick Answer

**Most APIs used are FREE and PUBLIC - no registration needed!** ✅

Only one requires registration (PubMed, but only for high volume).

---

## Data Sources & Access

### 1. AACT Database (ClinicalTrials.gov) ✅ REGISTERED
**Status:** You already have access - credentials in `.env`
- **Cost:** FREE for academic/research use
- **Registration:** Already done (you have credentials)
- **Rate Limits:** None for database queries
- **URL:** https://aact.ctti-clinicaltrials.org/

**What we access:**
- Trial metadata, phases, outcomes, termination reasons
- 500K+ trials, 32K+ terminated

---

### 2. ChEMBL API ✅ NO REGISTRATION NEEDED
**Status:** Completely open, no API key required
- **Cost:** FREE
- **Registration:** None required
- **Rate Limits:** ~10 requests/second (soft limit)
- **URL:** https://www.ebi.ac.uk/chembl/api/data

**What we access:**
- Drug→target mappings
- IC50 values (binding affinity)
- ChEMBL IDs → UniProt IDs

**API Example:**
```bash
# Works immediately, no auth
curl "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q=aspirin"
```

---

### 3. UniProt API ✅ NO REGISTRATION NEEDED
**Status:** Completely open, no API key required
- **Cost:** FREE
- **Registration:** None required
- **Rate Limits:** Reasonable use policy (~5 requests/second)
- **URL:** https://rest.uniprot.org

**What we access:**
- Protein information (name, gene, sequence)
- Known protein-protein interactions
- Functional annotations

**API Example:**
```bash
# Works immediately, no auth
curl "https://rest.uniprot.org/uniprotkb/P12345.json"
```

---

### 4. STRING Database API ✅ NO REGISTRATION NEEDED
**Status:** Completely open, no API key required
- **Cost:** FREE
- **Registration:** None required
- **Rate Limits:** No strict limits for reasonable use
- **URL:** https://string-db.org/api

**What we access:**
- High-confidence protein-protein interactions
- Interaction scores (0-1000)
- Evidence types (experimental, database, text mining)

**API Example:**
```bash
# Works immediately, no auth
curl "https://string-db.org/api/json/interaction_partners?identifiers=P12345&species=9606"
```

---

### 5. PubMed E-utilities API ⚠️ OPTIONAL REGISTRATION
**Status:** Open for low volume, registration recommended for high volume
- **Cost:** FREE
- **Registration:** Optional (recommended for >3 requests/second)
- **Rate Limits:**
  - **Without API key:** 3 requests/second
  - **With API key:** 10 requests/second
- **URL:** https://eutils.ncbi.nlm.nih.gov

**What we access:**
- Trial publication citations
- Detailed trial results from literature

**Current Status:**
- **Pipeline works without API key** (uses 3 req/sec limit with delays)
- For large datasets, register here: https://www.ncbi.nlm.nih.gov/account/

**To add API key (optional):**
```python
# In search_failure_details.py, add to PubMed requests:
params['api_key'] = 'YOUR_API_KEY'
```

---

## Summary Table

| Data Source | Registration | Cost | Rate Limit | Status |
|-------------|--------------|------|------------|--------|
| AACT (ClinicalTrials.gov) | ✅ Done | FREE | None | Working |
| ChEMBL | ❌ Not needed | FREE | ~10/sec | Working |
| UniProt | ❌ Not needed | FREE | ~5/sec | Working |
| STRING | ❌ Not needed | FREE | Reasonable | Working |
| PubMed | ⚠️ Optional | FREE | 3/sec (10/sec with key) | Working |

---

## Performance Impact

**Without any additional registration:**
- Pipeline works fine for 100s of trials
- Rate limits handled by built-in delays in scripts

**If you want faster processing:**
- Register for PubMed API key (5 min process, free)
- Can process ~3x faster on Stage 4

**Bottom line:** You're good to go right now! No additional registration needed for testing or moderate use.

---

## If You Want to Scale to 10,000+ Trials

Consider these optimizations:

1. **PubMed API Key** (free, 5 min)
   - Register: https://www.ncbi.nlm.nih.gov/account/
   - Get key: https://www.ncbi.nlm.nih.gov/account/settings/

2. **Run on Server** (not necessary, but faster)
   - More stable connection
   - Can run overnight without laptop sleep

3. **Batch Processing**
   - Process phases separately
   - Use `--limit` to break into chunks

But for now: **Everything works without any additional setup!**
