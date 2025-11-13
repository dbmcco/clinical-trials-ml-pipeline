#!/usr/bin/env python3
# ABOUTME: Prepare final ML dataset from enriched trial data for Synthyra PPI prediction

import json
import argparse
import csv
from typing import Dict, List, Optional
import pandas as pd


class MLDatasetBuilder:
    """Build ML-ready dataset from enriched trial data."""

    def __init__(self):
        pass

    def extract_trial_features(self, trial: Dict) -> Optional[Dict]:
        """Extract ML features from enriched trial data."""

        # Skip if no UniProt targets
        if not trial.get('chembl_enrichment', {}).get('has_uniprot_targets'):
            return None

        # Basic trial info
        features = {
            'nct_id': trial.get('nct_id'),
            'drug_name': trial.get('drug_name'),
            'intervention_type': trial.get('intervention_type'),
            'phase': trial.get('phase'),
            'overall_status': trial.get('overall_status'),

            # Target outcome label
            'outcome': self._get_outcome_label(trial),

            # ChEMBL features
            'chembl_id': trial.get('chembl_enrichment', {}).get('chembl_id'),
            'num_targets': len(trial.get('chembl_enrichment', {}).get('targets', [])),
        }

        # Extract target information
        targets = trial.get('chembl_enrichment', {}).get('targets', [])

        # Get IC50 statistics
        all_ic50_values = []
        for target in targets:
            for ic50 in target.get('ic50_values', []):
                if ic50.get('units') == 'nM':  # Standardize to nM
                    all_ic50_values.append(ic50.get('value'))

        if all_ic50_values:
            features['ic50_min_nm'] = min(all_ic50_values)
            features['ic50_max_nm'] = max(all_ic50_values)
            features['ic50_mean_nm'] = sum(all_ic50_values) / len(all_ic50_values)
            features['has_ic50_data'] = True
        else:
            features['ic50_min_nm'] = None
            features['ic50_max_nm'] = None
            features['ic50_mean_nm'] = None
            features['has_ic50_data'] = False

        # Extract UniProt IDs
        uniprot_ids = [
            t.get('uniprot_id')
            for t in targets
            if t.get('uniprot_id')
        ]
        features['uniprot_ids'] = ','.join(uniprot_ids) if uniprot_ids else None
        features['num_uniprot_targets'] = len(uniprot_ids)

        # PPI features
        ppi_data = trial.get('ppi_enrichment', [])
        if ppi_data:
            features['has_ppi_data'] = True

            # Count total interactions
            total_uniprot_interactions = sum(
                len(p.get('uniprot_interactions', []))
                for p in ppi_data
            )

            total_string_interactions = sum(
                p.get('string_interactions', {}).get('interaction_count', 0)
                for p in ppi_data
            )

            features['total_uniprot_interactions'] = total_uniprot_interactions
            features['total_string_interactions'] = total_string_interactions

            # Get average STRING scores
            all_scores = []
            for p in ppi_data:
                string_data = p.get('string_interactions', {})
                if string_data:
                    interactions = string_data.get('interactions', [])
                    scores = [i.get('score', 0) for i in interactions]
                    all_scores.extend(scores)

            if all_scores:
                features['avg_string_score'] = sum(all_scores) / len(all_scores)
                features['max_string_score'] = max(all_scores)
            else:
                features['avg_string_score'] = None
                features['max_string_score'] = None

            # Extract protein names for reference
            protein_names = [
                p.get('protein_info', {}).get('protein_name')
                for p in ppi_data
                if p.get('protein_info')
            ]
            features['target_proteins'] = '; '.join(filter(None, protein_names))

        else:
            features['has_ppi_data'] = False
            features['total_uniprot_interactions'] = 0
            features['total_string_interactions'] = 0
            features['avg_string_score'] = None
            features['max_string_score'] = None
            features['target_proteins'] = None

        # Failure detail features
        failure_details = trial.get('failure_detail_enrichment', {})
        if failure_details:
            features['has_pubmed_data'] = failure_details.get('pubmed', {}).get('found', False)
            features['num_pubmed_articles'] = failure_details.get('pubmed', {}).get('count', 0)
            features['has_posted_results'] = failure_details.get('clinicaltrials_details', {}).get('has_posted_results', False)
        else:
            features['has_pubmed_data'] = False
            features['num_pubmed_articles'] = 0
            features['has_posted_results'] = False

        return features

    def _get_outcome_label(self, trial: Dict) -> str:
        """
        Get standardized outcome label for ML.

        Returns:
        - SUCCESS: Trial progressed to next phase
        - FAILURE_EFFICACY: Terminated due to lack of efficacy
        - FAILURE_SAFETY: Terminated due to adverse effects
        - FAILURE_OTHER: Terminated for other reasons
        - UNKNOWN: Ongoing or unclear status
        """
        base_label = trial.get('label', 'UNKNOWN')

        if base_label == 'SUCCESS':
            return 'SUCCESS'

        if base_label == 'FAILURE':
            classification = trial.get('failure_classification', {})
            category = classification.get('category', 'UNKNOWN')

            if category == 'EFFICACY':
                return 'FAILURE_EFFICACY'
            elif category == 'SAFETY':
                return 'FAILURE_SAFETY'
            elif category == 'OTHER':
                return 'FAILURE_OTHER'
            else:
                return 'FAILURE_UNKNOWN'

        return 'UNKNOWN'

    def build_dataset(self, input_file: str, output_csv: str, output_json: str = None):
        """Build final ML dataset from enriched trials."""
        print(f"Loading enriched trials from {input_file}...")

        with open(input_file, 'r') as f:
            trials = json.load(f)

        print(f"Found {len(trials)} trials")

        # Extract features for each trial
        dataset = []
        skipped = 0

        for trial in trials:
            features = self.extract_trial_features(trial)
            if features:
                dataset.append(features)
            else:
                skipped += 1

        print(f"\nExtracted features for {len(dataset)} trials")
        print(f"Skipped {skipped} trials (no UniProt targets)")

        # Convert to DataFrame
        df = pd.DataFrame(dataset)

        # Print summary
        print(f"\n=== Dataset Summary ===")
        print(f"Total samples: {len(df)}")
        print(f"\nOutcome distribution:")
        print(df['outcome'].value_counts())

        print(f"\nPhase distribution:")
        print(df['phase'].value_counts())

        print(f"\nFeatures with PPI data: {df['has_ppi_data'].sum()}")
        print(f"Features with IC50 data: {df['has_ic50_data'].sum()}")

        # Save to CSV
        df.to_csv(output_csv, index=False)
        print(f"\n✓ Saved CSV to: {output_csv}")

        # Optionally save as JSON for detailed records
        if output_json:
            df.to_json(output_json, orient='records', indent=2)
            print(f"✓ Saved JSON to: {output_json}")

        return df


def main():
    parser = argparse.ArgumentParser(
        description='Prepare final ML dataset from enriched trial data'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSON file (fully enriched from all previous steps)'
    )
    parser.add_argument(
        '--output-csv',
        type=str,
        required=True,
        help='Output CSV file for ML training'
    )
    parser.add_argument(
        '--output-json',
        type=str,
        help='Optional: Output JSON file with detailed records'
    )

    args = parser.parse_args()

    builder = MLDatasetBuilder()
    builder.build_dataset(args.input, args.output_csv, args.output_json)


if __name__ == "__main__":
    main()
