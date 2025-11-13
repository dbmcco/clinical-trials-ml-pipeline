#!/usr/bin/env python3
# ABOUTME: Enrich trial data with drug targets from ChEMBL and UniProt IDs

import json
import argparse
import time
from typing import List, Dict, Optional
import requests


class TargetEnricher:
    """Enrich drug data with target information from ChEMBL."""

    def __init__(self):
        self.chembl_base = "https://www.ebi.ac.uk/chembl/api/data"
        self.session = requests.Session()

    def search_drug_in_chembl(self, drug_name: str) -> Optional[Dict]:
        """Search for a drug in ChEMBL by name."""
        try:
            # Clean drug name
            clean_name = drug_name.strip().lower()

            # Search for molecule
            url = f"{self.chembl_base}/molecule/search.json"
            params = {'q': clean_name, 'limit': 5}

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                molecules = data.get('molecules', [])

                if molecules:
                    # Return first match
                    return molecules[0]

            return None

        except Exception as e:
            print(f"  Error searching ChEMBL for {drug_name}: {e}")
            return None

    def get_drug_targets(self, chembl_id: str) -> List[Dict]:
        """Get target information for a ChEMBL molecule."""
        try:
            url = f"{self.chembl_base}/activity.json"
            params = {
                'molecule_chembl_id': chembl_id,
                'limit': 100
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                activities = data.get('activities', [])

                # Extract unique targets with IC50 data
                targets = {}
                for activity in activities:
                    target_chembl_id = activity.get('target_chembl_id')
                    if not target_chembl_id:
                        continue

                    # Get IC50 value if available
                    standard_type = activity.get('standard_type', '').upper()
                    if standard_type == 'IC50':
                        ic50_value = activity.get('standard_value')
                        ic50_units = activity.get('standard_units')

                        if target_chembl_id not in targets:
                            targets[target_chembl_id] = {
                                'chembl_id': target_chembl_id,
                                'ic50_values': []
                            }

                        if ic50_value and ic50_units:
                            targets[target_chembl_id]['ic50_values'].append({
                                'value': float(ic50_value),
                                'units': ic50_units
                            })

                return list(targets.values())

            return []

        except Exception as e:
            print(f"  Error getting targets for {chembl_id}: {e}")
            return []

    def get_target_uniprot(self, target_chembl_id: str) -> Optional[str]:
        """Get UniProt ID for a ChEMBL target."""
        try:
            url = f"{self.chembl_base}/target/{target_chembl_id}.json"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                target = data.get('target_components', [])

                if target and len(target) > 0:
                    # Get first component's accession
                    accessions = target[0].get('target_component_xrefs', [])
                    for xref in accessions:
                        if xref.get('xref_src_db') == 'UniProt':
                            return xref.get('xref_id')

            return None

        except Exception as e:
            print(f"  Error getting UniProt for {target_chembl_id}: {e}")
            return None

    def enrich_trial(self, trial: Dict) -> Dict:
        """Enrich a single trial with target information."""
        drug_name = trial.get('drug_name', '')

        print(f"\nProcessing: {drug_name} (NCT: {trial.get('nct_id')})")

        # Search ChEMBL
        molecule = self.search_drug_in_chembl(drug_name)

        if not molecule:
            print(f"  ❌ Not found in ChEMBL")
            trial['chembl_enrichment'] = {
                'found': False,
                'chembl_id': None,
                'targets': []
            }
            return trial

        chembl_id = molecule.get('molecule_chembl_id')
        print(f"  ✓ Found in ChEMBL: {chembl_id}")

        # Get targets
        targets = self.get_drug_targets(chembl_id)
        print(f"  ✓ Found {len(targets)} targets with IC50 data")

        # Get UniProt IDs
        for target in targets:
            uniprot_id = self.get_target_uniprot(target['chembl_id'])
            target['uniprot_id'] = uniprot_id
            if uniprot_id:
                print(f"    - {target['chembl_id']} → {uniprot_id}")

            # Rate limiting (reduced from 0.2s to 0.05s for faster processing)
            time.sleep(0.05)

        trial['chembl_enrichment'] = {
            'found': True,
            'chembl_id': chembl_id,
            'pref_name': molecule.get('pref_name'),
            'targets': targets,
            'has_uniprot_targets': any(t.get('uniprot_id') for t in targets)
        }

        return trial

    def enrich_trials(self, input_file: str, output_file: str, limit: Optional[int] = None):
        """Enrich all trials in a JSON file."""
        print(f"Loading trials from {input_file}...")

        with open(input_file, 'r') as f:
            trials = json.load(f)

        if limit:
            trials = trials[:limit]
            print(f"Limited to {len(trials)} trials for testing")
        else:
            print(f"Found {len(trials)} trials to enrich")

        enriched = []
        with_targets = 0

        for i, trial in enumerate(trials):
            print(f"\n[{i+1}/{len(trials)}]", end=' ')

            enriched_trial = self.enrich_trial(trial)
            enriched.append(enriched_trial)

            if enriched_trial.get('chembl_enrichment', {}).get('has_uniprot_targets'):
                with_targets += 1

            # Save progress every 50 trials
            if (i + 1) % 50 == 0:
                with open(output_file, 'w') as f:
                    json.dump(enriched, f, indent=2)
                print(f"\n  💾 Progress saved ({with_targets} with UniProt targets so far)")

            # Rate limiting (reduced from 0.5s to 0.1s for faster processing)
            time.sleep(0.1)

        # Final save
        with open(output_file, 'w') as f:
            json.dump(enriched, f, indent=2)

        print(f"\n\n=== Summary ===")
        print(f"Total trials processed: {len(enriched)}")
        print(f"Trials with UniProt targets: {with_targets}")
        print(f"Output saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich trial data with drug targets from ChEMBL'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSON file from query_trials.py'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output JSON file with enriched data'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of trials to process (for testing)'
    )

    args = parser.parse_args()

    enricher = TargetEnricher()
    enricher.enrich_trials(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
