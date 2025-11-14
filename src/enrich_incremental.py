# ABOUTME: Stage 2 - Incremental enrichment of trials with ChEMBL, UniProt, PPI, and failure details

import os
import sys
import requests
import psycopg2
from datetime import datetime
from typing import List, Dict, Optional, Any
from tinydb import TinyDB, Query
import argparse
from dotenv import load_dotenv
from utils import safe_sleep, calculate_exponential_backoff, format_timestamp

# Load environment variables
load_dotenv()

class IncrementalEnricher:
    """Incremental enrichment with retry logic"""

    def __init__(self, db_path: str = "data/clinical_trials.json",
                 queue_path: str = "data/enrichment_queue.json"):
        """
        Initialize enricher with database connections

        Args:
            db_path: Path to main TinyDB database
            queue_path: Path to retry queue database
        """
        self.db = TinyDB(db_path)
        self.queue_db = TinyDB(queue_path)
        self.trials_table = self.db.table('trials')
        self.retry_table = self.queue_db.table('retry_queue')

        # AACT database connection
        self.aact_conn = psycopg2.connect(
            host=os.getenv('AACT_DB_HOST', 'aact-db.ctti-clinicaltrials.org'),
            port=os.getenv('AACT_DB_PORT', '5432'),
            database=os.getenv('AACT_DB_NAME', 'aact'),
            user=os.getenv('AACT_DB_USER'),
            password=os.getenv('AACT_DB_PASSWORD')
        )

        # Rate limiting delays
        self.chembl_delay = float(os.getenv('CHEMBL_DELAY_SECONDS', '0.05'))
        self.pubmed_delay = float(os.getenv('PUBMED_DELAY_SECONDS', '0.1'))

    def enrich_all_pending(self):
        """Enrich all trials with pending stages"""
        Trial = Query()

        print("="*50)
        print("STAGE 2: INCREMENTAL ENRICHMENT")
        print("="*50)

        # Target enrichment
        pending_targets = self.trials_table.search(
            Trial.enrichment_status.stage2_targets == 'pending'
        )
        print(f"\n[1/3] Target Enrichment: {len(pending_targets)} trials pending")
        for i, trial in enumerate(pending_targets, 1):
            print(f"  Processing {i}/{len(pending_targets)}: {trial['nct_id']} ({trial['drug_name']})")
            self.enrich_targets(trial)

        # PPI enrichment (depends on targets)
        pending_ppi = self.trials_table.search(
            (Trial.enrichment_status.stage2_targets == 'completed') &
            (Trial.enrichment_status.stage2_ppi == 'pending')
        )
        print(f"\n[2/3] PPI Enrichment: {len(pending_ppi)} trials pending")
        for i, trial in enumerate(pending_ppi, 1):
            print(f"  Processing {i}/{len(pending_ppi)}: {trial['nct_id']}")
            self.enrich_ppi(trial)

        # Failure details enrichment (independent)
        pending_failures = self.trials_table.search(
            Trial.enrichment_status.stage2_failure_details == 'pending'
        )
        print(f"\n[3/3] Failure Details Enrichment: {len(pending_failures)} trials pending")
        for i, trial in enumerate(pending_failures, 1):
            print(f"  Processing {i}/{len(pending_failures)}: {trial['nct_id']}")
            self.enrich_failure_details(trial)

        print("\n✅ Stage 2 enrichment complete")

    # -------------------------------------------------------------------------
    # Target Enrichment (ChEMBL + UniProt)
    # -------------------------------------------------------------------------

    def enrich_targets(self, trial: Dict):
        """
        ChEMBL + UniProt enrichment with DrugBank fallback

        Args:
            trial: Trial document from TinyDB
        """
        try:
            # Try ChEMBL first
            chembl_data = self.query_chembl(trial['drug_name'])

            # If ChEMBL fails, try DrugBank fallback
            if not chembl_data.get('found') or not chembl_data.get('has_uniprot_targets'):
                drugbank_data = self.query_drugbank_fallback(trial['drug_name'])
                if drugbank_data.get('found'):
                    # Merge DrugBank data into chembl_data structure
                    chembl_data = {
                        **chembl_data,
                        'found': True,
                        'drugbank_fallback': True,
                        'targets': drugbank_data.get('targets', []),
                        'has_uniprot_targets': drugbank_data.get('has_uniprot_targets', False)
                    }

            self.trials_table.update(
                {'chembl_enrichment': chembl_data,
                 'enrichment_status': {
                     **trial['enrichment_status'],
                     'stage2_targets': 'completed',
                     'last_updated': format_timestamp()
                 }},
                doc_ids=[trial.doc_id]
            )
        except Exception as e:
            print(f"    ❌ ERROR: {str(e)}")
            self.add_to_retry_queue(trial['nct_id'], 'stage2_targets', str(e))

    def query_chembl(self, drug_name: str) -> Dict:
        """
        Query ChEMBL API for drug targets and IC50 data

        Args:
            drug_name: Drug name to search

        Returns:
            ChEMBL enrichment data
        """
        # Try synonym normalization via PubChem first
        normalized_name = self.normalize_drug_name(drug_name)
        search_name = normalized_name if normalized_name else drug_name

        # Search for molecule
        search_url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/search?q={search_name}&format=json"
        safe_sleep(self.chembl_delay)

        response = requests.get(search_url, timeout=10)
        if response.status_code != 200:
            return {"found": False, "chembl_id": None, "targets": [], "search_name": search_name}

        data = response.json()
        if not data.get('molecules'):
            return {"found": False, "chembl_id": None, "targets": [], "search_name": search_name}

        molecule = data['molecules'][0]
        chembl_id = molecule['molecule_chembl_id']
        pref_name = molecule.get('pref_name', drug_name)

        # Get targets and IC50 data
        targets = self.get_chembl_targets(chembl_id)

        return {
            "found": True,
            "chembl_id": chembl_id,
            "pref_name": pref_name,
            "targets": targets,
            "has_uniprot_targets": any(t.get('uniprot_id') for t in targets),
            "search_name": search_name
        }

    def get_chembl_targets(self, chembl_id: str) -> List[Dict]:
        """
        Get targets and IC50 data for a ChEMBL molecule

        Args:
            chembl_id: ChEMBL molecule ID

        Returns:
            List of target dictionaries with IC50 data
        """
        activities_url = f"https://www.ebi.ac.uk/chembl/api/data/activity?molecule_chembl_id={chembl_id}&standard_type=IC50&format=json&limit=1000"
        safe_sleep(self.chembl_delay)

        response = requests.get(activities_url, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        activities = data.get('activities', [])

        # Aggregate by target
        targets_dict = {}
        for activity in activities:
            target_chembl_id = activity.get('target_chembl_id')
            if not target_chembl_id:
                continue

            if target_chembl_id not in targets_dict:
                targets_dict[target_chembl_id] = {
                    'chembl_id': target_chembl_id,
                    'ic50_values': [],
                    'uniprot_id': None
                }

            # Add IC50 value
            value = activity.get('standard_value')
            units = activity.get('standard_units')
            if value and units:
                targets_dict[target_chembl_id]['ic50_values'].append({
                    'value': float(value),
                    'units': units
                })

        # Get UniProt IDs for each target
        targets = list(targets_dict.values())
        for target in targets:
            target['uniprot_id'] = self.get_uniprot_id(target['chembl_id'])

        return targets

    def normalize_drug_name(self, drug_name: str) -> Optional[str]:
        """
        Normalize drug name using PubChem synonym lookup

        Args:
            drug_name: Original drug name

        Returns:
            Normalized name or None if not found
        """
        try:
            # Search PubChem for compound
            search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{drug_name}/cids/JSON"
            safe_sleep(0.1)

            response = requests.get(search_url, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()
            cids = data.get('IdentifierList', {}).get('CID', [])
            if not cids:
                return None

            cid = cids[0]

            # Get preferred name
            props_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/IUPACName/JSON"
            safe_sleep(0.1)

            props_response = requests.get(props_url, timeout=10)
            if props_response.status_code != 200:
                return None

            props_data = props_response.json()
            properties = props_data.get('PropertyTable', {}).get('Properties', [])
            if properties and 'IUPACName' in properties[0]:
                return properties[0]['IUPACName']

            return None
        except:
            return None

    def query_drugbank_fallback(self, drug_name: str) -> Dict:
        """
        Fallback to DrugBank Open Data API when ChEMBL fails

        Args:
            drug_name: Drug name to search

        Returns:
            DrugBank enrichment data in ChEMBL-compatible format
        """
        try:
            # DrugBank Open Data API (no auth required for basic search)
            search_url = f"https://go.drugbank.com/unearth/q?utf8=✓&query={drug_name}&searcher=drugs"
            safe_sleep(0.2)

            # Note: This is a simplified fallback using UniProt direct search
            # Full DrugBank requires XML download or paid API
            # For now, we'll use UniProt's drug mapping as a lightweight fallback

            # Search UniProt for drug-target mappings
            uniprot_url = f"https://rest.uniprot.org/uniprotkb/search?query=({drug_name})+AND+(reviewed:true)&fields=accession,protein_name&format=json&size=10"
            safe_sleep(0.1)

            response = requests.get(uniprot_url, timeout=10)
            if response.status_code != 200:
                return {"found": False, "targets": [], "has_uniprot_targets": False}

            data = response.json()
            results = data.get('results', [])

            if not results:
                return {"found": False, "targets": [], "has_uniprot_targets": False}

            # Build targets from UniProt results
            targets = []
            for result in results[:5]:  # Limit to top 5
                targets.append({
                    'chembl_id': None,
                    'uniprot_id': result.get('primaryAccession'),
                    'ic50_values': [],
                    'source': 'uniprot_fallback'
                })

            return {
                "found": True,
                "targets": targets,
                "has_uniprot_targets": len(targets) > 0
            }
        except:
            return {"found": False, "targets": [], "has_uniprot_targets": False}

    def get_uniprot_id(self, target_chembl_id: str) -> Optional[str]:
        """
        Get UniProt ID for a ChEMBL target

        Args:
            target_chembl_id: ChEMBL target ID

        Returns:
            UniProt ID or None
        """
        target_url = f"https://www.ebi.ac.uk/chembl/api/data/target/{target_chembl_id}?format=json"
        safe_sleep(self.chembl_delay)

        try:
            response = requests.get(target_url, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()
            components = data.get('target_components', [])
            if components:
                accessions = components[0].get('target_component_xrefs', [])
                for xref in accessions:
                    if xref.get('xref_src_db') == 'UniProt':
                        return xref.get('xref_id')
        except:
            pass

        return None

    # -------------------------------------------------------------------------
    # PPI Enrichment (STRING database)
    # -------------------------------------------------------------------------

    def enrich_ppi(self, trial: Dict):
        """
        PPI network enrichment from STRING database

        Args:
            trial: Trial document from TinyDB
        """
        try:
            # Extract UniProt IDs from ChEMBL enrichment
            uniprot_ids = []
            chembl_enrichment = trial.get('chembl_enrichment', {})
            if chembl_enrichment.get('has_uniprot_targets'):
                for target in chembl_enrichment.get('targets', []):
                    uid = target.get('uniprot_id')
                    if uid and uid not in uniprot_ids:
                        uniprot_ids.append(uid)

            if not uniprot_ids:
                # No UniProt targets, mark as completed but empty
                self.trials_table.update(
                    {'ppi_enrichment': {'uniprot_count': 0, 'interactions': []},
                     'enrichment_status': {
                         **trial['enrichment_status'],
                         'stage2_ppi': 'completed',
                         'last_updated': format_timestamp()
                     }},
                    doc_ids=[trial.doc_id]
                )
                return

            # Query STRING for each UniProt ID
            interactions = []
            for uniprot_id in uniprot_ids:
                ppi_data = self.query_string(uniprot_id)
                interactions.extend(ppi_data)

            # Calculate network features
            network_features = self.calculate_network_features(interactions)

            self.trials_table.update(
                {'ppi_enrichment': {
                    'uniprot_count': len(uniprot_ids),
                    'interactions': interactions,
                    'network_features': network_features
                 },
                 'enrichment_status': {
                     **trial['enrichment_status'],
                     'stage2_ppi': 'completed',
                     'last_updated': format_timestamp()
                 }},
                doc_ids=[trial.doc_id]
            )
        except Exception as e:
            print(f"    ❌ ERROR: {str(e)}")
            self.add_to_retry_queue(trial['nct_id'], 'stage2_ppi', str(e))

    def query_string(self, uniprot_id: str) -> List[Dict]:
        """
        Query STRING database for protein interactions

        Args:
            uniprot_id: UniProt ID

        Returns:
            List of protein-protein interactions
        """
        string_url = f"https://string-db.org/api/json/network?identifiers={uniprot_id}&species=9606&required_score=700"
        safe_sleep(0.1)

        try:
            response = requests.get(string_url, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            interactions = []
            for edge in data:
                interactions.append({
                    'protein_a': edge.get('preferredName_A'),
                    'protein_b': edge.get('preferredName_B'),
                    'combined_score': edge.get('score'),
                    'interaction_type': 'physical'
                })

            return interactions
        except:
            return []

    def calculate_network_features(self, interactions: List[Dict]) -> Dict:
        """
        Calculate PPI network topology features

        Args:
            interactions: List of PPI interactions

        Returns:
            Network features dictionary
        """
        if not interactions:
            return {'avg_degree': 0, 'clustering_coefficient': 0}

        # Build adjacency list
        adjacency = {}
        for interaction in interactions:
            a = interaction['protein_a']
            b = interaction['protein_b']

            if a not in adjacency:
                adjacency[a] = []
            if b not in adjacency:
                adjacency[b] = []

            adjacency[a].append(b)
            adjacency[b].append(a)

        # Calculate average degree
        degrees = [len(neighbors) for neighbors in adjacency.values()]
        avg_degree = sum(degrees) / len(degrees) if degrees else 0

        # Simple clustering coefficient approximation
        clustering = 0.0
        if len(adjacency) > 0:
            clustering = len(interactions) / len(adjacency)

        return {
            'avg_degree': round(avg_degree, 2),
            'clustering_coefficient': round(clustering, 2)
        }

    # -------------------------------------------------------------------------
    # Failure Details Enrichment (AACT + PubMed + CT.gov API)
    # -------------------------------------------------------------------------

    def enrich_failure_details(self, trial: Dict):
        """
        Enrich with comprehensive failure reason data

        Args:
            trial: Trial document from TinyDB
        """
        try:
            nct_id = trial['nct_id']
            drug_name = trial['drug_name']

            # Source 1: AACT Detailed Description
            description = self.get_aact_detailed_description(nct_id)

            # Source 2: AACT Documents
            documents = self.get_aact_documents(nct_id)

            # Source 3: PubMed Enhanced
            pubmed = self.search_pubmed(nct_id, drug_name)

            # Source 4: ClinicalTrials.gov API
            ct_data = self.search_clinicaltrials_api(nct_id)

            # Source 5: Company Website Search URLs
            sponsor = trial.get('sponsor', '')
            company_search = self.generate_company_search_urls(sponsor, nct_id, drug_name)

            self.trials_table.update(
                {'failure_enrichment': {
                    'aact_description': description,
                    'aact_documents': documents,
                    'pubmed_results': pubmed,
                    'clinicaltrials_api': ct_data,
                    'company_search_urls': company_search
                 },
                 'enrichment_status': {
                     **trial['enrichment_status'],
                     'stage2_failure_details': 'completed',
                     'last_updated': format_timestamp()
                 }},
                doc_ids=[trial.doc_id]
            )
        except Exception as e:
            print(f"    ❌ ERROR: {str(e)}")
            self.add_to_retry_queue(trial['nct_id'], 'stage2_failure_details', str(e))

    def get_aact_detailed_description(self, nct_id: str) -> Optional[str]:
        """Get detailed description from AACT"""
        cursor = self.aact_conn.cursor()
        cursor.execute(
            "SELECT description FROM ctgov.detailed_descriptions WHERE nct_id = %s",
            (nct_id,)
        )
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else None

    def get_aact_documents(self, nct_id: str) -> List[Dict]:
        """Get documents from AACT"""
        cursor = self.aact_conn.cursor()
        cursor.execute(
            "SELECT document_type, url FROM ctgov.documents WHERE nct_id = %s",
            (nct_id,)
        )
        docs = []
        for row in cursor.fetchall():
            docs.append({'type': row[0], 'url': row[1]})
        cursor.close()
        return docs

    def search_pubmed(self, nct_id: str, drug_name: str) -> List[Dict]:
        """Search PubMed for trial publications"""
        search_term = f"{nct_id} OR ({drug_name} AND clinical trial)"
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={search_term}&retmode=json&retmax=5"

        safe_sleep(self.pubmed_delay)

        try:
            response = requests.get(search_url, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            pmids = data.get('esearchresult', {}).get('idlist', [])

            # Fetch summaries
            results = []
            if pmids:
                summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
                safe_sleep(self.pubmed_delay)

                summary_response = requests.get(summary_url, timeout=10)
                if summary_response.status_code == 200:
                    summaries = summary_response.json().get('result', {})
                    for pmid in pmids:
                        if pmid in summaries:
                            results.append({
                                'pmid': pmid,
                                'title': summaries[pmid].get('title'),
                                'authors': summaries[pmid].get('authors', [])[:3]
                            })

            return results
        except:
            return []

    def search_clinicaltrials_api(self, nct_id: str) -> Dict:
        """Search ClinicalTrials.gov API for additional data including SAE tables"""
        api_url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
        safe_sleep(0.1)

        try:
            response = requests.get(api_url, timeout=10)
            if response.status_code != 200:
                return {}

            data = response.json()
            study = data.get('protocolSection', {})
            results = data.get('resultsSection', {})

            # Parse adverse events module
            adverse_events = self._parse_adverse_events(results.get('adverseEventsModule', {}))

            # Parse dose information from arms/interventions
            dose_info = self._parse_dose_info(study.get('armsInterventionsModule', {}))

            return {
                'has_results': 'resultsSection' in data,
                'brief_summary': study.get('descriptionModule', {}).get('briefSummary'),
                'detailed_description': study.get('descriptionModule', {}).get('detailedDescription'),
                'adverse_events': adverse_events,
                'dose_info': dose_info
            }
        except:
            return {}

    def _parse_adverse_events(self, ae_module: Dict) -> Dict:
        """
        Parse adverse events module from CT.gov API

        Args:
            ae_module: adverseEventsModule from CT.gov API v2

        Returns:
            Structured SAE data
        """
        if not ae_module:
            return {'found': False}

        sae_data = {
            'found': True,
            'frequency_threshold': ae_module.get('frequencyThreshold'),
            'time_frame': ae_module.get('timeFrame'),
            'description': ae_module.get('description'),
            'serious_events': [],
            'other_events': []
        }

        # Parse serious adverse events
        serious_events = ae_module.get('seriousEvents', {}).get('eventGroups', [])
        for event_group in serious_events:
            group_data = {
                'title': event_group.get('title'),
                'deaths': event_group.get('deathsNumAffected', 0),
                'serious_affected': event_group.get('seriousNumAffected', 0),
                'serious_at_risk': event_group.get('seriousNumAtRisk', 0),
                'events': []
            }

            # Parse individual serious events
            for event in event_group.get('seriousEvents', []):
                group_data['events'].append({
                    'term': event.get('term'),
                    'organ_system': event.get('assessmentType'),
                    'affected': event.get('stats', [{}])[0].get('numAffected', 0),
                    'at_risk': event.get('stats', [{}])[0].get('numAtRisk', 0)
                })

            sae_data['serious_events'].append(group_data)

        # Parse other adverse events (non-serious)
        other_events = ae_module.get('otherEvents', {}).get('eventGroups', [])
        for event_group in other_events:
            group_data = {
                'title': event_group.get('title'),
                'affected': event_group.get('otherNumAffected', 0),
                'at_risk': event_group.get('otherNumAtRisk', 0),
                'events': []
            }

            for event in event_group.get('otherEvents', []):
                group_data['events'].append({
                    'term': event.get('term'),
                    'organ_system': event.get('assessmentType'),
                    'affected': event.get('stats', [{}])[0].get('numAffected', 0),
                    'at_risk': event.get('stats', [{}])[0].get('numAtRisk', 0)
                })

            sae_data['other_events'].append(group_data)

        # Calculate summary metrics
        sae_data['summary'] = self._calculate_sae_summary(sae_data)

        return sae_data

    def _calculate_sae_summary(self, sae_data: Dict) -> Dict:
        """Calculate summary metrics from SAE data"""
        summary = {
            'total_deaths': 0,
            'total_serious_affected': 0,
            'total_serious_at_risk': 0,
            'sae_rate': 0.0,
            'death_rate': 0.0,
            'has_safety_signal': False
        }

        # Sum across all serious event groups
        for group in sae_data.get('serious_events', []):
            summary['total_deaths'] += group.get('deaths', 0)
            summary['total_serious_affected'] += group.get('serious_affected', 0)
            summary['total_serious_at_risk'] = max(
                summary['total_serious_at_risk'],
                group.get('serious_at_risk', 0)
            )

        # Calculate rates
        if summary['total_serious_at_risk'] > 0:
            summary['sae_rate'] = summary['total_serious_affected'] / summary['total_serious_at_risk']
            summary['death_rate'] = summary['total_deaths'] / summary['total_serious_at_risk']

        # Safety signal heuristic: SAE rate > 10% or any deaths
        summary['has_safety_signal'] = (
            summary['sae_rate'] > 0.1 or
            summary['total_deaths'] > 0
        )

        return summary

    def _parse_dose_info(self, arms_module: Dict) -> Dict:
        """
        Parse dosing information from arms/interventions module

        Args:
            arms_module: armsInterventionsModule from CT.gov API v2

        Returns:
            Structured dose data
        """
        if not arms_module:
            return {'found': False}

        dose_data = {
            'found': True,
            'arms': [],
            'interventions': []
        }

        # Parse arm descriptions for dose information
        for arm in arms_module.get('armGroups', []):
            arm_info = {
                'label': arm.get('label'),
                'type': arm.get('type'),
                'description': arm.get('description'),
                'intervention_names': arm.get('interventionNames', [])
            }
            dose_data['arms'].append(arm_info)

        # Parse intervention descriptions for dose details
        for intervention in arms_module.get('interventions', []):
            intervention_info = {
                'type': intervention.get('type'),
                'name': intervention.get('name'),
                'description': intervention.get('description'),
                'arm_group_labels': intervention.get('armGroupLabels', [])
            }
            dose_data['interventions'].append(intervention_info)

        return dose_data

    def query_perplexity(self, query: str) -> Dict:
        """
        Query Perplexity AI for web research with citations

        Args:
            query: Search query

        Returns:
            Dict with answer and citations
        """
        try:
            import os
            perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')

            if not perplexity_api_key:
                return {'found': False, 'error': 'PERPLEXITY_API_KEY not set'}

            safe_sleep(1.0)  # Rate limiting

            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers={
                    'Authorization': f'Bearer {perplexity_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'llama-3.1-sonar-small-128k-online',
                    'messages': [
                        {'role': 'system', 'content': 'You are a research assistant searching for clinical trial safety information. Provide specific facts with citations.'},
                        {'role': 'user', 'content': query}
                    ],
                    'temperature': 0.2,
                    'max_tokens': 500
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'found': True,
                    'answer': data['choices'][0]['message']['content'],
                    'citations': data.get('citations', []),
                    'model': data['model']
                }
            else:
                return {'found': False, 'error': f'API error: {response.status_code}'}

        except Exception as e:
            return {'found': False, 'error': str(e)}

    def search_fda_warnings(self, drug_name: str, sponsor: str) -> Dict:
        """
        Search FDA warning letters and clinical holds via Perplexity

        Args:
            drug_name: Drug name to search
            sponsor: Sponsor/company name

        Returns:
            Dict with FDA warning findings
        """
        try:
            query = f"FDA warning letters or clinical holds for {drug_name} by {sponsor}. Include specific dates, reasons, and safety issues cited."

            result = self.query_perplexity(query)

            if result.get('found'):
                return {
                    'found': True,
                    'search_query': query,
                    'findings': result['answer'],
                    'citations': result.get('citations', []),
                    'source': 'perplexity_ai'
                }
            else:
                return {
                    'found': False,
                    'search_query': query,
                    'error': result.get('error', 'No results')
                }

        except Exception as e:
            return {'found': False, 'error': str(e)}

    def search_sec_filings(self, sponsor: str, nct_id: str, start_date: str) -> Dict:
        """
        Search SEC EDGAR for 8-K filings mentioning trial or safety issues

        Args:
            sponsor: Company name
            nct_id: Trial NCT ID
            start_date: Trial start date for filtering filings

        Returns:
            Dict with SEC filing findings
        """
        try:
            # SEC EDGAR has a public API
            # We'd search for 8-K filings (material events) around trial dates
            # that mention the NCT ID or safety-related keywords

            sec_signals = {
                'found': False,
                'filings_8k': [],
                'filings_10k': [],
                'search_params': {
                    'company': sponsor,
                    'nct_id': nct_id,
                    'start_date': start_date
                },
                'note': 'SEC EDGAR scraping not yet implemented - requires CIK lookup and filing parsing'
            }

            # Future implementation:
            # 1. Look up company CIK (Central Index Key) from sponsor name
            # 2. Query SEC EDGAR API for 8-K filings after trial start date
            # 3. Download and parse filings for NCT ID or safety keywords
            # 4. Extract relevant safety disclosures

            return sec_signals

        except Exception as e:
            return {'found': False, 'error': str(e)}

    def scrape_company_disclosures(self, search_urls: List[str], drug_name: str) -> Dict:
        """
        Scrape company websites/press releases for safety disclosures

        Args:
            search_urls: List of Google search URLs for company + trial
            drug_name: Drug name to look for in content

        Returns:
            Dict with scraped safety disclosure findings
        """
        try:
            # This would use web scraping to:
            # 1. Follow search URLs to find company press releases
            # 2. Parse press releases for safety-related keywords
            # 3. Extract structured SAE information where possible

            company_signals = {
                'found': False,
                'press_releases': [],
                'investor_presentations': [],
                'safety_keywords_found': [],
                'search_urls': search_urls,
                'note': 'Company website scraping not yet implemented - requires robust web scraping with rate limiting'
            }

            # Future implementation:
            # 1. Use requests + BeautifulSoup to fetch search results
            # 2. Follow links to company IR pages
            # 3. Parse press releases for safety keywords (deaths, SAE, toxicity, adverse events)
            # 4. Extract structured data where format allows
            # 5. Store raw HTML and extracted text for LLM analysis

            return company_signals

        except Exception as e:
            return {'found': False, 'error': str(e)}

    def generate_company_search_urls(self, sponsor: str, nct_id: str, drug_name: str) -> List[str]:
        """Generate company website search URLs"""
        if not sponsor:
            return []

        urls = [
            f"https://www.google.com/search?q={sponsor}+{nct_id}+terminated",
            f"https://www.google.com/search?q={sponsor}+{drug_name}+clinical+trial+terminated"
        ]

        return urls

    # -------------------------------------------------------------------------
    # Retry Queue Management
    # -------------------------------------------------------------------------

    def add_to_retry_queue(self, nct_id: str, stage: str, error: str):
        """
        Add failed enrichment to retry queue

        Args:
            nct_id: Trial NCT ID
            stage: Enrichment stage that failed
            error: Error message
        """
        retry_entry = {
            'nct_id': nct_id,
            'stage': stage,
            'error': error,
            'retry_count': 0,
            'next_retry': calculate_exponential_backoff(0).isoformat(),
            'created': format_timestamp()
        }
        self.retry_table.insert(retry_entry)

    def process_retry_queue(self):
        """Process retry queue with exponential backoff"""
        Retry = Query()
        now = datetime.utcnow()

        ready_retries = self.retry_table.search(
            Retry.next_retry <= now.isoformat()
        )

        print(f"\nProcessing retry queue: {len(ready_retries)} entries ready")

        for retry in ready_retries:
            if retry['retry_count'] >= 5:
                # Max retries reached
                print(f"  ❌ Max retries reached for {retry['nct_id']} ({retry['stage']})")
                self.mark_enrichment_failed(retry['nct_id'], retry['stage'])
                self.retry_table.remove(doc_ids=[retry.doc_id])
            else:
                # Retry enrichment
                print(f"  🔄 Retrying {retry['nct_id']} ({retry['stage']}) - Attempt {retry['retry_count'] + 1}")
                Trial = Query()
                trial_docs = self.trials_table.search(Trial.nct_id == retry['nct_id'])

                if trial_docs:
                    trial = trial_docs[0]

                    if retry['stage'] == 'stage2_targets':
                        self.enrich_targets(trial)
                    elif retry['stage'] == 'stage2_ppi':
                        self.enrich_ppi(trial)
                    elif retry['stage'] == 'stage2_failure_details':
                        self.enrich_failure_details(trial)

                # Update retry count
                self.retry_table.update(
                    {'retry_count': retry['retry_count'] + 1,
                     'next_retry': calculate_exponential_backoff(retry['retry_count'] + 1).isoformat()},
                    doc_ids=[retry.doc_id]
                )

    def mark_enrichment_failed(self, nct_id: str, stage: str):
        """Mark enrichment stage as permanently failed"""
        Trial = Query()
        trial_docs = self.trials_table.search(Trial.nct_id == nct_id)

        if trial_docs:
            trial = trial_docs[0]
            self.trials_table.update(
                {'enrichment_status': {
                    **trial['enrichment_status'],
                    stage: 'failed',
                    'last_updated': format_timestamp()
                }},
                doc_ids=[trial.doc_id]
            )

    def close(self):
        """Close database connections"""
        self.aact_conn.close()
        self.db.close()
        self.queue_db.close()


def main():
    """Main entry point for incremental enrichment"""
    parser = argparse.ArgumentParser(
        description="Incremental enrichment of clinical trials"
    )
    parser.add_argument(
        '--db',
        default='data/clinical_trials.json',
        help='Path to TinyDB database'
    )
    parser.add_argument(
        '--queue',
        default='data/enrichment_queue.json',
        help='Path to retry queue database'
    )
    parser.add_argument(
        '--retry',
        action='store_true',
        help='Process retry queue only'
    )

    args = parser.parse_args()

    enricher = IncrementalEnricher(db_path=args.db, queue_path=args.queue)

    try:
        if args.retry:
            enricher.process_retry_queue()
        else:
            enricher.enrich_all_pending()
            enricher.process_retry_queue()

    finally:
        enricher.close()


if __name__ == "__main__":
    main()
