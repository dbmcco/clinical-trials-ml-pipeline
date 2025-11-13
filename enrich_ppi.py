#!/usr/bin/env python3
# ABOUTME: Enrich trials with protein-protein interaction data from UniProt

import json
import argparse
import time
from typing import Dict, List, Optional
import requests


class PPIEnricher:
    """Enrich target proteins with PPI data from UniProt."""

    def __init__(self):
        self.session = requests.Session()
        self.uniprot_base = "https://rest.uniprot.org"

    def get_protein_info(self, uniprot_id: str) -> Optional[Dict]:
        """Get basic protein information from UniProt."""
        try:
            url = f"{self.uniprot_base}/uniprotkb/{uniprot_id}.json"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Extract key information
                protein_info = {
                    'uniprot_id': uniprot_id,
                    'protein_name': data.get('proteinDescription', {}).get('recommendedName', {}).get('fullName', {}).get('value'),
                    'gene_name': data.get('genes', [{}])[0].get('geneName', {}).get('value') if data.get('genes') else None,
                    'organism': data.get('organism', {}).get('scientificName'),
                    'sequence_length': data.get('sequence', {}).get('length'),
                    'sequence': data.get('sequence', {}).get('value')
                }

                return protein_info

            return None

        except Exception as e:
            print(f"    Error fetching protein info for {uniprot_id}: {e}")
            return None

    def get_protein_interactions(self, uniprot_id: str) -> List[Dict]:
        """
        Get protein-protein interactions from UniProt.
        UniProt aggregates data from multiple sources (IntAct, STRING, etc.)
        """
        try:
            # Use UniProt's interaction endpoint
            url = f"{self.uniprot_base}/uniprotkb/search"
            params = {
                'query': f'accession:{uniprot_id}',
                'fields': 'cc_interaction',
                'format': 'json'
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])

                if results and len(results) > 0:
                    # Extract interaction comments
                    comments = results[0].get('comments', [])
                    interactions = []

                    for comment in comments:
                        if comment.get('commentType') == 'INTERACTION':
                            interactions_data = comment.get('interactions', [])

                            for interaction in interactions_data:
                                interactant = interaction.get('interactantTwo', {})

                                interactions.append({
                                    'partner_uniprot_id': interactant.get('uniProtKBAccession'),
                                    'partner_gene': interactant.get('geneName'),
                                    'num_experiments': interaction.get('numberOfExperiments'),
                                    'organism': interaction.get('organismDiffer', False)
                                })

                    return interactions

            return []

        except Exception as e:
            print(f"    Error fetching interactions for {uniprot_id}: {e}")
            return []

    def get_string_interactions(self, uniprot_id: str) -> Optional[Dict]:
        """
        Get high-confidence interactions from STRING database.
        STRING has more comprehensive PPI data.
        """
        try:
            # STRING API
            string_url = "https://string-db.org/api/json/interaction_partners"

            params = {
                'identifiers': uniprot_id,
                'species': 9606,  # Human
                'required_score': 700  # High confidence (0-1000)
            }

            response = self.session.get(string_url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data:
                    interactions = []
                    for item in data[:20]:  # Top 20 interactions
                        interactions.append({
                            'partner_string_id': item.get('stringId_B'),
                            'partner_name': item.get('preferredName_B'),
                            'score': item.get('score'),
                            'nscore': item.get('nscore'),  # Neighborhood score
                            'fscore': item.get('fscore'),  # Fusion score
                            'pscore': item.get('pscore'),  # Co-occurrence score
                            'ascore': item.get('ascore'),  # Coexpression score
                            'escore': item.get('escore'),  # Experimental score
                            'dscore': item.get('dscore'),  # Database score
                            'tscore': item.get('tscore')   # Textmining score
                        })

                    return {
                        'found': True,
                        'interaction_count': len(interactions),
                        'interactions': interactions
                    }

            return None

        except Exception as e:
            print(f"    Error fetching STRING interactions for {uniprot_id}: {e}")
            return None

    def enrich_protein(self, uniprot_id: str) -> Dict:
        """Get comprehensive PPI data for a protein."""
        print(f"    Enriching {uniprot_id}...")

        enrichment = {
            'uniprot_id': uniprot_id,
            'protein_info': None,
            'uniprot_interactions': [],
            'string_interactions': None
        }

        # Get basic protein info
        protein_info = self.get_protein_info(uniprot_id)
        if protein_info:
            enrichment['protein_info'] = protein_info
            print(f"      ✓ Protein: {protein_info.get('protein_name')} ({protein_info.get('gene_name')})")

        # Get UniProt interactions
        uniprot_interactions = self.get_protein_interactions(uniprot_id)
        if uniprot_interactions:
            enrichment['uniprot_interactions'] = uniprot_interactions
            print(f"      ✓ UniProt interactions: {len(uniprot_interactions)}")

        # Get STRING interactions (more comprehensive)
        string_interactions = self.get_string_interactions(uniprot_id)
        if string_interactions:
            enrichment['string_interactions'] = string_interactions
            print(f"      ✓ STRING interactions: {string_interactions['interaction_count']}")

        # Rate limiting (reduced from 0.3s to 0.1s for faster processing)
        time.sleep(0.1)

        return enrichment

    def enrich_trials(self, input_file: str, output_file: str, limit: Optional[int] = None):
        """Enrich all trials with PPI data for their targets."""
        print(f"Loading trials from {input_file}...")

        with open(input_file, 'r') as f:
            trials = json.load(f)

        print(f"Found {len(trials)} trials")

        # Filter to trials with UniProt targets
        trials_with_targets = [
            t for t in trials
            if t.get('chembl_enrichment', {}).get('has_uniprot_targets')
        ]

        print(f"Trials with UniProt targets: {len(trials_with_targets)}")

        if limit:
            print(f"Limiting to first {limit} trials for testing")
            trials_with_targets = trials_with_targets[:limit]

        enriched = []
        unique_proteins = set()

        for i, trial in enumerate(trials_with_targets):
            print(f"\n[{i+1}/{len(trials_with_targets)}] {trial['nct_id']} - {trial['drug_name']}")

            # Get all UniProt IDs for this trial
            targets = trial.get('chembl_enrichment', {}).get('targets', [])

            ppi_enrichment = []

            for target in targets:
                uniprot_id = target.get('uniprot_id')

                if uniprot_id and uniprot_id not in unique_proteins:
                    unique_proteins.add(uniprot_id)

                    # Enrich this protein
                    protein_ppi = self.enrich_protein(uniprot_id)
                    ppi_enrichment.append(protein_ppi)

            trial['ppi_enrichment'] = ppi_enrichment
            enriched.append(trial)

            # Save progress every 10 trials
            if (i + 1) % 10 == 0:
                with open(output_file, 'w') as f:
                    json.dump(enriched, f, indent=2)
                print(f"\n  💾 Progress saved ({len(unique_proteins)} unique proteins enriched)")

        # Final save
        with open(output_file, 'w') as f:
            json.dump(enriched, f, indent=2)

        # Summary
        print(f"\n\n=== Summary ===")
        print(f"Trials enriched: {len(enriched)}")
        print(f"Unique proteins enriched: {len(unique_proteins)}")

        with_string = sum(
            1 for t in enriched
            if any(p.get('string_interactions') for p in t.get('ppi_enrichment', []))
        )

        print(f"Trials with STRING PPI data: {with_string}")
        print(f"\nOutput saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich trials with protein-protein interaction data'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSON file (from enrich_targets.py)'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output JSON file with PPI enrichment'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of trials to process (for testing)'
    )

    args = parser.parse_args()

    enricher = PPIEnricher()
    enricher.enrich_trials(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
